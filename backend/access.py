"""Opt-in local bearer gate only, NOT deployed identity/authentication.
No tokens generated or stored here. Configured scope still isn't a user principal.
"""
import secrets
from limits import LocalAdmissionLimits

class LocalBearerGate:
    def __init__(self,app,token):
        if not isinstance(token,str) or not 32<=len(token)<=256 or not all(33<=ord(c)<=126 for c in token):raise ValueError('Use an explicit strong local secret token from outside source/chat')
        self.app=app;self._token=token.encode('ascii')
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        headers=[v for k,v in scope.get('headers',[]) if k.lower()==b'authorization']
        if len(headers)!=1 or not headers[0].startswith(b'Bearer ') or not secrets.compare_digest(headers[0][7:],self._token):
            return await LocalAdmissionLimits.error(self,send,401,'LOCAL_ACCESS_REQUIRED','Configured local access token required.')
        return await self.app(scope,receive,send)
