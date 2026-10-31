"""Local UI proxy + static host for the UNCHANGED frontend client. The proxy serves the already built client bundle (built outside the
frontend repo with VITE_AUDIT_MODE=backend VITE_API_BASE_URL=http://localhost:<port>; no source edit) and its POST /audit, so the client's
fetch is SAME-ORIGIN and the browser sends an HttpOnly SameSite=Strict session cookie by itself. Nothing in the bundle holds a credential.
Authentication: the launcher opens http://localhost:<port>/launch#n=<one-time nonce>. The nonce sits in the URL FRAGMENT, so it is not sent to the server, logs or Referer; the page POSTs it, then clears it from the URL. It is single use and expires after 300 s, and is exchanged for the
session cookie. Without that cookie /audit and the UI are refused (401). Other websites cannot read or send the cookie (SameSite=Strict,
Origin must be the proxy's own). A local process that can read the launcher's nonce (launcher process memory/arguments, or the
browser profile) can still obtain a session: this is loopback, single-user-machine protection, not user authentication.
The backend access token is held server side only and is forwarded to /fresh-review-audit, which is stored-only (no dispatch code).
Sessions: idle 30 min, absolute 4 h, max 8, revoked by POST /logout (same-origin, cookie) or by stopping the launcher; no logout button exists in the unchanged client. Idempotency-Key is enforced here per session (same key + different body = 409; same key + body replays a stored 200 without a second backend call). Session scope: POST /audit sends an HMAC-derived value of the cookie session id (not the cookie id) as the backend display session, a bearer value that the backend only format-checks and compares for equality. Stored results are still looked up by pixel digest, so this does NOT bind a result to an owner or account."""
import asyncio,hashlib,hmac,re,secrets,time
from pathlib import Path
import httpx
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,Response,RedirectResponse
MAX_BODY=16_000_000
NONCE_TTL=300;IDLE_TTL=1800;ABS_TTL=14400;MAX_SESSIONS=8;IDEM_TTL=900;MAX_IDEM=64
LAUNCH_PAGE='<!doctype html><meta charset=utf-8><meta name=referrer content=no-referrer><title>Vigilens launch</title><p id=m>Opening Vigilens...</p><script>(async()=>{const n=new URLSearchParams(location.hash.slice(1)).get("n")||"";history.replaceState(null,"","/launch");const r=await fetch("/launch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({n})});if(r.ok){location.replace("/")}else{document.getElementById("m").textContent="Launch link is invalid, expired or already used. Start the launcher again."}})()</script>'
COOKIE='vigilens_session'
BRIDGE_ALLOWLIST=()  # default OFF in code (not a hard lock: a code edit enables it). bridge_allowed is not used by any route. display_session_for IS used, by POST /audit.
BRIDGE_SHAPES={('GET','zone-review'):re.compile(r'^/fresh-review/[0-9a-f]{64}/zone-review$')}  # the only shape that could be enabled by name
def display_session_for(secret,sid):
    """Used by POST /audit. Derives the backend X-Vigilens-Display-Session value for a proxy cookie session with HMAC, so the cookie value itself is never the backend value and the browser cannot compute it. The backend only checks its FORMAT (32-128 chars) and compares for equality: it is a bearer value, not an identity."""
    return hmac.new(secret,b'vigilens-display-session\0'+sid.encode(),'sha256').hexdigest()
def bridge_allowed(method,path,allowlist=None):
    """True only when the operator enabled this exact (method, name) AND the path matches that name's strict shape. Empty by default, so nothing is allowed."""
    al=BRIDGE_ALLOWLIST if allowlist is None else allowlist
    return any((method,name)in al and rx.match(path)is not None for(m,name),rx in BRIDGE_SHAPES.items()if m==method)
def content_digest(ctype,body):
    """Digest of the multipart FIELDS (names, filenames, content), independent of the per-request boundary, so a browser retry with the same key and same content is recognised."""
    import re
    m=re.search(r'boundary="?([^";]+)"?',ctype)
    if not m:return hashlib.sha256(body).hexdigest()
    parts=[]
    for chunk in body.split(b'--'+m.group(1).encode()):
        if b'\r\n\r\n' not in chunk:continue
        head,_,data=chunk.partition(b'\r\n\r\n')
        if data.endswith(b'\r\n'):data=data[:-2]
        name=re.search(rb'name="([^"]*)"',head);fn=re.search(rb'filename="([^"]*)"',head)
        parts.append((name.group(1)if name else b'',fn.group(1)if fn else b'',hashlib.sha256(data).hexdigest()))
    return hashlib.sha256(repr(sorted(parts)).encode()).hexdigest()
MIME={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.json':'application/json','.ico':'image/x-icon','.woff2':'font/woff2'}

def create_proxy(backend,token,*,launch_nonce,ui_dir=None,port=8000,governed_new_image=False,clock=time.monotonic,display_secret=None):
    """backend: httpx.AsyncClient bound to the authenticated backend. token: backend access token (server side only)."""
    if not isinstance(token,str)or not 32<=len(token)<=256:raise ValueError('Strong access token required')
    if not isinstance(launch_nonce,str)or not 32<=len(launch_nonce)<=256:raise ValueError('Strong launch nonce required')
    AUDIT_PATH='/fresh-review-audit-governed'if governed_new_image is True else'/fresh-review-audit'   # default stored-only; the flag only SELECTS the governed handler, it does not grant dispatch
    # Per-process random secret for deriving the backend display-session value. Never persisted, printed or sent; it dies with the proxy, as do the cookie sessions it derives from.
    if display_secret is None:display_secret=secrets.token_bytes(32)
    if not isinstance(display_secret,bytes)or len(display_secret)<32:raise ValueError('Strong display secret required')
    origins=('http://localhost:%d'%port,'http://127.0.0.1:%d'%port)
    state={'nonce':launch_nonce,'nonce_deadline':clock()+NONCE_TTL,'sessions':{},'idem':{},'locks':{}}
    root=Path(ui_dir).resolve()if ui_dir else None
    app=FastAPI(title='Vigilens local UI proxy',docs_url=None,redoc_url=None,openapi_url=None)
    def err(status,code,message,extra=None):return JSONResponse({'error':{'code':code,'message':message}},status_code=status,headers={'Cache-Control':'no-store',**(extra or{})})
    def purge():
        now=clock()
        for sid,v in list(state['sessions'].items()):
            if now-v['seen']>IDLE_TTL or now-v['born']>ABS_TTL:del state['sessions'][sid]
        for k in [k for k in state['locks']if k not in state['idem']and not state['locks'][k].locked()]:del state['locks'][k]
        for k,v in list(state['idem'].items()):
            if k[0]not in state['sessions']or now-v['at']>IDEM_TTL:del state['idem'][k]
    def session(request):
        purge();sid=request.cookies.get(COOKIE,'');v=state['sessions'].get(sid)
        if v is None:return None
        v['seen']=clock();return sid
    def same_origin(request):
        return request.headers.get('origin','')in origins and request.headers.get('sec-fetch-site','same-origin')=='same-origin'   # 'none' (user navigation) and cross/same-site are refused
    @app.get('/health')
    def health():return {'status':'ok','mode':'private_review_proxy'}
    @app.get('/launch')
    def launch_page():return Response(LAUNCH_PAGE,media_type='text/html; charset=utf-8',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    @app.post('/launch')
    async def launch(request:Request):
        if not same_origin(request):return err(403,'ORIGIN_NOT_ALLOWED','Local UI origin required.')
        try:n=(await request.json()).get('n','')
        except Exception:n=''
        nonce=state['nonce']
        if not nonce or not isinstance(n,str)or clock()>state['nonce_deadline']or not hmac.compare_digest(n.encode(),nonce.encode()):return err(403,'LAUNCH_REFUSED','Launch link is invalid, expired or already used.')
        state['nonce']=None   # single use
        purge()
        if len(state['sessions'])>=MAX_SESSIONS:return err(429,'TOO_MANY_SESSIONS','Too many sessions; restart the launcher.')
        sid=secrets.token_urlsafe(40);now=clock();state['sessions'][sid]={'born':now,'seen':now}
        r=JSONResponse({'ok':True},headers={'Cache-Control':'no-store'})
        r.set_cookie(COOKIE,sid,httponly=True,samesite='strict',path='/',max_age=ABS_TTL)
        return r
    @app.post('/logout')
    async def logout(request:Request):
        sid=session(request)
        if sid is None or not same_origin(request):return err(401,'LAUNCH_REQUIRED','No active session.')
        state['sessions'].pop(sid,None);r=JSONResponse({'ok':True},headers={'Cache-Control':'no-store'});r.delete_cookie(COOKIE,path='/');return r
    @app.post('/audit')
    async def audit(request:Request):
        sid=session(request)
        if sid is None:return err(401,'LAUNCH_REQUIRED','Open the UI through the Vigilens launch link; this session is not authorised or has expired.')
        if not same_origin(request):return err(403,'ORIGIN_NOT_ALLOWED','Local UI origin required.')
        key=request.headers.get('idempotency-key','')
        if not 8<=len(key)<=128:return err(400,'INVALID_IDEMPOTENCY_KEY','Idempotency-Key required.')
        try:length=int(request.headers.get('content-length','0')or 0)
        except ValueError:return err(400,'INVALID_CONTENT_LENGTH','Invalid Content-Length.')
        if length<0:return err(400,'INVALID_CONTENT_LENGTH','Invalid Content-Length.')
        if length>MAX_BODY:return err(413,'IMAGE_TOO_LARGE','Request too large.')
        body=await request.body()
        if len(body)>MAX_BODY:return err(413,'IMAGE_TOO_LARGE','Request too large.')
        ctype=request.headers.get('content-type','')
        if not ctype.startswith('multipart/form-data'):return err(415,'UNSUPPORTED_MEDIA','multipart/form-data required.')
        # Idempotency (proxy level, per session): the same key with a different body is a conflict; the same key and body replays a stored 200 and is not forwarded again.
        ik=(sid,key);bh=content_digest(ctype,body)
        lock=state['locks'].setdefault(ik,asyncio.Lock())
        async with lock:
            hit=state['idem'].get(ik)
            if hit is not None:
                if hit['body']!=bh:return err(409,'IDEMPOTENCY_CONFLICT','Idempotency-Key was already used for a different request.')
                return Response(hit['content'],media_type='application/json',headers={'Cache-Control':'no-store','X-Vigilens-Idempotent-Replay':'true'})
            try:r=await backend.post(AUDIT_PATH,content=body,headers={'content-type':ctype,'X-Vigilens-Local-Access':token,'X-Vigilens-Display-Session':display_session_for(display_secret,sid)})
            except httpx.HTTPError:return err(502,'BACKEND_UNAVAILABLE','Backend unavailable or did not answer; the outcome is unknown. Nothing is retried automatically.')
            # Statuses 501/502 are chosen because the unchanged client shows error.message verbatim only for these (see FRONTEND-CONTRACT.md).
            # Messages never infer "no call was made" from a status; only the stored-only route states what its handler structurally cannot do.
            if r.status_code==200 and r.headers.get('content-type','').startswith('application/json'):
                if len(state['idem'])<MAX_IDEM:state['idem'][ik]={'body':bh,'content':r.content,'at':clock()}
                return Response(r.content,media_type='application/json',headers={'Cache-Control':'no-store'})
        if r.status_code==503:return err(501,'LIVE_ANALYSIS_UNAVAILABLE','Live analysis is not enabled on the backend.')
        if r.status_code==409:
            if governed_new_image is True and b'ATTEMPT_UNCERTAIN' in r.content:return err(501,'ATTEMPT_UNCERTAIN','A provider attempt for this image was started and did not finish. Calls may have been made; the count is unknown and nothing is retried or reconciled here. Check the backend ledger. This is not a clearance.')
            if governed_new_image is True:return err(501,'ANALYSIS_REFUSED','The backend refused this image: no source approval, accounting or configuration block, or a result that is not safe to present. It is not retried automatically, and nothing here counts as a clearance.')
            return err(501,'ANALYSIS_UNAVAILABLE','No presentable stored result exists for this exact image (none stored, or not safe to present). This route only reads stored results and never starts analysis.')
        if r.status_code==403:return err(502,'BACKEND_AUTH_FAILED','Backend refused the proxy credential.')
        return err(502,'BACKEND_ERROR','Backend error; the outcome is unknown.')
    @app.get('/{path:path}')
    def static(path:str,request:Request):
        if root is None or session(request)is None:return err(401,'LAUNCH_REQUIRED','Open the UI through the Vigilens launch link.')
        f=(root/(path or 'index.html')).resolve()
        if root not in f.parents and f!=root or not f.is_file():f=root/'index.html'
        if not f.is_file():return err(404,'NOT_FOUND','Not found.')
        return Response(f.read_bytes(),media_type=MIME.get(f.suffix,'application/octet-stream'),headers={'Cache-Control':'no-store'})
    return app
