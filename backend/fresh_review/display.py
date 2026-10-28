"""Local manual redaction display only. No provider, inference, evidence or disk store."""
import hashlib, json, secrets, time, threading, sqlite3
from dataclasses import dataclass
from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import Response
from core import decode_image, AuditError
from .redaction import probe

TTL_SECONDS = 900
MAX_SESSIONS = 8
MAX_TOTAL_BYTES = 32_000_000
MAX_DERIVATIVE_BYTES = 15_000_000
@dataclass
class Session:
    owner: str
    png: bytes
    meta: dict
    expires: float
    reviewed: bool = False
    review_ack: dict = None
    verify: object = None

def create_display():
    router=APIRouter()
    LOCK=threading.RLock()
    SESSIONS={}
    def owner_check(owner):
        if not isinstance(owner, str) or not 32 <= len(owner) <= 128 or not all(c.isalnum() or c in '-_' for c in owner):
            raise HTTPException(403, 'Private browser session required')

    def prune():
        now = time.monotonic()
        for sid in list(SESSIONS):
            if SESSIONS[sid].expires <= now:
                del SESSIONS[sid]

    def lookup(sid, owner):
        owner_check(owner)
        prune()
        s = SESSIONS.get(sid)
        if s is None or not secrets.compare_digest(s.owner, owner):
            raise HTTPException(404, 'Display session missing or expired')
        if s.verify is not None:
            try:s.verify(s.meta)
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):
                del SESSIONS[sid]
                raise HTTPException(409,'Fresh source changed; preview invalidated')
        if hashlib.sha256(s.png).hexdigest() != s.meta['output_sha256']:
            del SESSIONS[sid]
            raise HTTPException(409, 'Derivative identity changed')
        return s

    def report(sid, s):
        return {**s.meta, 'source': 'local_manual_private_display', 'session_id': sid,
                'preview_url': '/private-display/' + sid + '/image',
                'visual_review_status': 'operator_checked' if s.reviewed else 'pending',
                'viewing_assurance': 'operator_claim_only_not_server_observed',
                'privacy_review_status': 'not_validated', 'coverage': 'operator_claim_only' if s.reviewed else 'not_verified',
                'evidence_export_allowed': False, 'provider_calls_this_request': 0,
                'expires_in_seconds': max(0, int(s.expires - time.monotonic())),
                'notice': 'Manual region display treatment only. Blur may retain identity. Not a face detector or anonymity guarantee. Original stays separate for inference. Export disabled.'}

    def verify_derivative(png, meta):
        """After encode, require pixels-only RGB PNG; opaque method additionally verifies black region pixels."""
        import io, struct
        from PIL import Image
        pos = 8
        if png[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('PNG required')
        chunks = []
        while pos < len(png):
            n = struct.unpack('>I', png[pos:pos+4])[0]
            chunks.append(png[pos+4:pos+8])
            pos += n + 12
        if pos != len(png) or not chunks or chunks[0] != b'IHDR' or chunks[-1] != b'IEND' or any(c not in (b'IHDR', b'IDAT', b'IEND') for c in chunks):
            raise ValueError('Only pixel PNG chunks permitted')
        im = Image.open(io.BytesIO(png));im.load()
        if im.mode != 'RGB' or im.size != (meta['width'], meta['height']) or im.info:
            raise ValueError('Pixels-only unchanged-size RGB required')
        for region in meta['regions'] if meta.get('redaction_method','opaque') == 'opaque' else []:
            pixels = im.crop(tuple(region['box'])).convert('RGBA')
            if any(p != (0, 0, 0, 255) for p in pixels.getdata()):
                raise ValueError('Opaque region did not survive encoding')

    def blur_regions(data, mime, regions):
        """Separate display-only Gaussian treatment after probe has validated source and regions.
        Radius is a development visual setting, not a privacy threshold or certified anonymity.
        """
        import io
        from PIL import Image, ImageFilter
        from core import pixel_only_png
        original = Image.open(io.BytesIO(pixel_only_png(data, mime))).convert('RGB')
        out = original.copy(); radii = []
        for region in regions:
            l,t,r,b = region['box']
            radius = max(12, min(r-l, b-t) / 3)
            source_region = original.crop((l,t,r,b))
            blurred = source_region.filter(ImageFilter.GaussianBlur(radius))
            if blurred.tobytes() == source_region.tobytes():
                raise ValueError('A declared blur region did not change; manual review required')
            out.paste(blurred, (l,t));radii.append(radius)
        clean = Image.frombytes('RGB', out.size, out.tobytes());buf=io.BytesIO();clean.save(buf, 'PNG')
        return buf.getvalue(), radii

    def reject_display_input(pixel_digest):
        # Layer on top of live inference's exact original-source allowlist. No DB or provider access.
        with LOCK:
            prune()
            for s in SESSIONS.values():
                from core import decode_image
                if decode_image(s.png, 'image/png').digest == pixel_digest:
                    raise HTTPException(403, 'Display derivative cannot be an inference source')

    @router.post('/private-display')
    async def create(image: UploadFile = File(...), review: str = Form(...),
                     x_vigilens_display_session: str = Header('')):
        owner_check(x_vigilens_display_session)
        data = await image.read(15_000_001)
        if len(data) > 15_000_000:
            raise HTTPException(413, 'Upload exceeds 15,000,000 bytes')
        try:
            r = json.loads(review)
            allowed=set(r)if isinstance(r,dict)else set()
            if not isinstance(r,dict)or allowed not in ({'source_digest','frame_size','regions','reviewer_label'},{'source_digest','frame_size','regions','reviewer_label','redaction_method'}):raise ValueError('Exact source/frame/region review required')
            frame = decode_image(data, image.content_type)
            if frame.orientation != 1:
                raise ValueError('Only upright sources accepted; region coordinates use canonical upright pixels')
            method = r.pop('redaction_method', 'opaque')
            if method not in ('opaque', 'blur'):
                raise ValueError('Unknown display method')
            png, meta = probe(data, image.content_type, **r)
            meta['redaction_method'] = method
            if method == 'blur':
                png, blur_radii = blur_regions(data, image.content_type, r['regions'])
                meta['blur_radii_pixels'] = blur_radii
                meta['output_sha256'] = hashlib.sha256(png).hexdigest()
                meta['warning'] = 'Gaussian region blur is a display treatment, not verified de-identification. Faces, shape, clothes and context may remain recognizable.'
            if len(png) > MAX_DERIVATIVE_BYTES:
                raise ValueError('Derivative too large')
            verify_derivative(png, meta)
            if decode_image(png, 'image/png').digest == frame.digest:
                raise ValueError('Regions must change source pixels')
            meta['regions_digest'] = hashlib.sha256(json.dumps(meta['regions'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            meta['reviewer_label'] = r['reviewer_label'].strip()
        except (AuditError, ValueError, TypeError, KeyError, AttributeError, OSError, sqlite3.Error):
            raise HTTPException(422, 'Invalid source, regions or source/frame binding')
        # No source bytes survive this request; only the pixels-only derivative is retained.
        with LOCK:
            prune()
            # Atomic replacement per browser owner: failed frontend DELETE cannot leave an older active preview after new preparation.
            for prior in list(SESSIONS):
                if secrets.compare_digest(SESSIONS[prior].owner, x_vigilens_display_session):
                    del SESSIONS[prior]
            if len(SESSIONS) >= MAX_SESSIONS or sum(len(s.png) for s in SESSIONS.values()) + len(png) > MAX_TOTAL_BYTES:
                raise HTTPException(429, 'Private display capacity reached; clear an old session')
            sid = secrets.token_urlsafe(24)
            s = Session(x_vigilens_display_session, png, meta, time.monotonic() + TTL_SECONDS)
            SESSIONS[sid] = s
            return report(sid, s)

    @router.get('/private-display/{sid}/image')
    async def image(sid: str, x_vigilens_display_session: str = Header('')):
        with LOCK:
            s = lookup(sid, x_vigilens_display_session)
            return Response(s.png, media_type='image/png', headers={'Cache-Control': 'no-store', 'Content-Disposition': 'inline'})

    @router.post('/private-display/{sid}/review')
    async def confirm(sid: str, payload: dict, x_vigilens_display_session: str = Header('')):
        with LOCK:
            s = lookup(sid, x_vigilens_display_session)
            expected = {'source_digest': s.meta['source_digest'], 'output_sha256': s.meta['output_sha256'],
                        'regions_digest': s.meta['regions_digest'], 'frame_size': [s.meta['width'], s.meta['height']],
                        'foreground_checked': True, 'background_checked': True, 'reflections_checked': True,
                        'derivative_checked': True}
            # Equality alone would accept 1 for True. Strict type checks preserve explicit acknowledgments.
            if set(payload) != set(expected) or any(type(payload[k]) is not type(v) or payload[k] != v for k, v in expected.items()):
                raise HTTPException(409, 'Review must match this exact derivative and include every visual check')
            s.review_ack = dict(payload)
            s.reviewed = True
            return report(sid, s)

    @router.delete('/private-display/{sid}')
    async def clear(sid: str, x_vigilens_display_session: str = Header('')):
        with LOCK:
            lookup(sid, x_vigilens_display_session)
            del SESSIONS[sid]
        return {'cleared': True, 'evidence_export_allowed': False}
    from types import SimpleNamespace
    return SimpleNamespace(router=router,LOCK=LOCK,SESSIONS=SESSIONS,owner_check=owner_check,prune=prune,lookup=lookup,report=report,create=create,reject_display_input=reject_display_input)
