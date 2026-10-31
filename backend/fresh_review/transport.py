"""Bounded one-attempt Meta Responses transport. No retries, redirects, tools or logging."""
import json,urllib.request
from pathlib import Path
from .pipeline import FreshPipeline
class MetaTransport:
    ENDPOINT='https://api.meta.ai/v1/responses'
    def __init__(self,key_file,*,timeout=90,opener=None):
        self.key_file=Path(key_file);self.timeout=timeout
        self.read_key() #Fail closed during explicit startup, before any journal/reservation.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a,**kw):raise ValueError('Provider redirect refused; no retry')
        self.opener=opener or urllib.request.build_opener(NoRedirect())
    def read_key(self):
        raw=FreshPipeline.private_bytes(self.key_file)
        key=raw.decode().strip()
        if not key or any(ord(c)<33 or ord(c)>126 for c in key):raise ValueError('Private ASCII API key file required')
        return key
    def __call__(self,body):
        if not isinstance(body,dict)or body.get('model')not in ('sam-3.1','muse-spark-1.3')or body.get('store')is not False or body.get('tools')or body.get('background'):raise ValueError('Only bounded private SAM/PPE requests supported')
        key=self.read_key()
        request=urllib.request.Request(self.ENDPOINT,data=json.dumps(body,separators=(',',':'),allow_nan=False).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
        limit=4_000_000 if body['model']=='sam-3.1'else 256_000
        with self.opener.open(request,timeout=self.timeout)as response:
            if response.status!=200:raise ValueError('Provider non-success; no retry')
            result=response.read(limit+1)
            if len(result)>limit:raise ValueError('Provider response exceeds private quota; no retry')
            return result
