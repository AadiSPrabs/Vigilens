"""No-model audit primitives. All policy is draft and explicitly versioned."""
import hashlib
import io
import json
import math
import warnings
from dataclasses import dataclass
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 15_000_000
MAX_DIM = 4096
MAX_PIXELS = 16_000_000
MAX_ZONES = 20
MAX_POINTS = 100
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

class AuditError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)

def fail(code, message, status=400):
    raise AuditError(status, code, message)

def cross(a, b, c):
    return (b['x']-a['x'])*(c['y']-a['y'])-(b['y']-a['y'])*(c['x']-a['x'])

def on_segment(a,b,p):
    return abs(cross(a,b,p)) <= 1e-12 and min(a['x'],b['x'])-1e-12 <= p['x'] <= max(a['x'],b['x'])+1e-12 and min(a['y'],b['y'])-1e-12 <= p['y'] <= max(a['y'],b['y'])+1e-12

def intersects(a,b,c,d):
    x,y,z,w = cross(a,b,c), cross(a,b,d), cross(c,d,a), cross(c,d,b)
    return ((x>0) != (y>0) and (z>0) != (w>0)) or any((abs(v)<=1e-12 and on_segment(u,t,p)) for v,u,t,p in [(x,a,b,c),(y,a,b,d),(z,c,d,a),(w,c,d,b)])

def area(points):
    return abs(sum(p['x']*q['y']-q['x']*p['y'] for p,q in zip(points,points[1:]+points[:1])))/2

def polygon(points):
    if not isinstance(points,list) or not 3 <= len(points) <= MAX_POINTS:
        fail('INVALID_POLYGON','A polygon needs 3 to 100 distinct points.')
    out=[]
    for p in points:
        if not isinstance(p,dict) or set(p) != {'x','y'}:
            fail('INVALID_POLYGON','Points must contain x and y only.')
        if any(type(p[k]) not in (float,int) or not math.isfinite(p[k]) or not 0<=p[k]<=1 for k in ('x','y')):
            fail('INVALID_COORDINATE','Coordinates must be finite numbers between 0 and 1, not booleans.')
        out.append({'x':float(p['x']),'y':float(p['y'])})
    if len({(p['x'],p['y']) for p in out}) != len(out):
        fail('INVALID_POLYGON','Do not repeat vertices or close a polygon by repeating its first point.')
    if area(out) <= 1e-12:
        fail('INVALID_POLYGON','Polygon has zero or negligible area.')
    n=len(out)
    for i in range(n):
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1): continue
            if intersects(out[i],out[(i+1)%n],out[j],out[(j+1)%n]):
                fail('INVALID_POLYGON','Polygon must not self-intersect or touch itself.')
    return out

def validate_zones(raw):
    try:
        zones=json.loads(raw,parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) if isinstance(raw,str) else raw
    except (ValueError,TypeError):
        fail('INVALID_ZONES','Zones must be valid JSON without NaN or Infinity.')
    if not isinstance(zones,list) or len(zones)>MAX_ZONES:
        fail('INVALID_ZONES','Zones must be an array with at most 20 entries.')
    seen=set(); result=[]
    for z in zones:
        if not isinstance(z,dict) or set(z) != {'id','name','hazard','points'}:
            fail('INVALID_ZONE','Each zone needs id, name, hazard and points only.')
        zid=z['id']; name=z['name']
        if not isinstance(zid,str) or not 1<=len(zid)<=128 or zid in seen:
            fail('INVALID_ZONE_ID','Zone IDs must be unique nonempty strings of at most 128 characters.')
        if not isinstance(name,str) or not 1<=len(name)<=200 or type(z['hazard']) is not bool:
            fail('INVALID_ZONE','Zone name and hazard have invalid types or lengths.')
        seen.add(zid); result.append(dict(id=zid,name=name,hazard=z['hazard'],points=polygon(z['points'])))
    return result

@dataclass(frozen=True)
class DecodedImage:
    width: int
    height: int
    digest: str
    orientation: int
    mime: str

def decode_image(data, declared_mime):
    if len(data)>MAX_BYTES: fail('IMAGE_TOO_LARGE','File exceeds 15,000,000 bytes.',413)
    if declared_mime not in FORMATS.values(): fail('UNSUPPORTED_MEDIA_TYPE','Use JPEG, PNG or WebP.',415)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as im:
                actual=FORMATS.get(im.format)
                if not actual or actual != declared_mime:
                    fail('UNSUPPORTED_MEDIA_TYPE','Decoded image format must match the declared type.',415)
                w,h=im.size
                if w<=0 or h<=0 or max(w,h)>MAX_DIM or w*h>MAX_PIXELS:
                    fail('IMAGE_DIMENSIONS_TOO_LARGE','Image exceeds dimension or decoded pixel limits.',422)
                if getattr(im,'n_frames',1)!=1: fail('ANIMATED_IMAGE_UNSUPPORTED','Only still images are supported.',415)
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                orientation=im.getexif().get(274,1)
                im.load()
                oriented=ImageOps.exif_transpose(im)
                # Digest includes oriented pixel content and dimensions, no EXIF/private metadata.
                rgb=oriented.convert('RGB'); w,h=rgb.size
                digest=hashlib.sha256(f'{w}x{h}:RGB:'.encode()+rgb.tobytes()).hexdigest()
        return DecodedImage(w,h,digest,orientation,actual)
    except AuditError: raise
    except (Exception,) as exc:
        raise AuditError(422,'IMAGE_UNREADABLE','Image could not be fully decoded.') from exc

def contains(p, points):
    inside=False
    for a,b in zip(points,points[1:]+points[:1]):
        if on_segment(a,b,p): return True
        if (a['y']>p['y']) != (b['y']>p['y']):
            x=(b['x']-a['x'])*(p['y']-a['y'])/(b['y']-a['y'])+a['x']
            if p['x'] < x: inside=not inside
    return inside

def memberships(points,zones,contact_known=True):
    if not contact_known: return {'status':'unknown','display_zone_id':None,'zone_ids':[]}
    points=polygon(points)
    p={'x':(min(q['x'] for q in points)+max(q['x'] for q in points))/2,'y':max(q['y'] for q in points)}
    matches=[z for z in zones if contains(p,z['points'])]
    matches.sort(key=lambda z:(not z['hazard'],area(z['points']),z['id']))
    return {'status':'known','display_zone_id':matches[0]['id'] if matches else None,'zone_ids':[z['id'] for z in matches]}

def request_digest(image,zones):
    return hashlib.sha256((image.digest+json.dumps(zones,sort_keys=True,separators=(',',':'))).encode()).hexdigest()
