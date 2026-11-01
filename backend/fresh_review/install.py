"""Mount private fresh routes on the actual backend. No default provider execution."""
import os,secrets
from pathlib import Path
from fastapi.responses import JSONResponse
from .pipeline import FreshPipeline
from .api import create_router
from .display import create_display

# Default deny: every path needs the local access token except these (health probe, and the fixture-skeleton /audit that serves no private data).
OPEN_PATHS=frozenset({'/health','/audit'})

def install(app,service,*,token=None):
    #Explicit opt-in factory/service; capture per-app token once,not per-request env state.
    token=os.environ.get('VIGILENS_LOCAL_ACCESS_TOKEN','')if token is None else token
    app.state.fresh_pipeline=service
    display=create_display();app.state.fresh_display=display
    app.include_router(create_router(service,display));app.include_router(display.router)
    @app.middleware('http')
    async def private_gate(request,call_next):
        if request.method!='OPTIONS'and request.url.path not in OPEN_PATHS:
            expected=token
            supplied=request.headers.get('X-Vigilens-Local-Access','')
            if len(expected)<32 or not secrets.compare_digest(expected,supplied):
                return JSONResponse({'detail':'Private local access required'},status_code=403,headers={'Cache-Control':'no-store'})
        response=await call_next(request)
        response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer'
        return response
    return app
