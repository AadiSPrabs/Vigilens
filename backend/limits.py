"""Local ASGI admission bounds, before multipart parsing.
Whole bodies are buffered only for admitted requests. A timeout at an ingress
proxy is still required against slow senders in any non-loopback deployment.
"""
import json
import asyncio
import math
import threading

class LocalAdmissionLimits:
    def __init__(self,app,max_body_bytes=16_000_000,max_concurrent=2,body_timeout_seconds=15):
        if type(max_body_bytes) is not int or max_body_bytes<=0 or type(max_concurrent) is not int or max_concurrent<=0:raise ValueError('Positive integer local limits required')
        if type(body_timeout_seconds) not in (int,float) or not math.isfinite(body_timeout_seconds) or body_timeout_seconds<=0:raise ValueError('Positive finite receive timeout required')
        self.body_timeout=body_timeout_seconds
        self.app=app;self.max_body=max_body_bytes;self.slots=threading.BoundedSemaphore(max_concurrent)
    async def error(self,send,status,code,message):
        body=json.dumps({'error':{'code':code,'message':message}}).encode()
        await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]})
        await send({'type':'http.response.body','body':body})
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        if not self.slots.acquire(blocking=False):return await self.error(send,503,'LOCAL_CAPACITY_REACHED','Local request capacity reached; no execution started.')
        try:
            lengths=[v for k,v in scope.get('headers',[]) if k.lower()==b'content-length']
            if lengths:
                try:
                    if len(lengths)!=1 or not lengths[0].isdigit():raise ValueError()
                    length=int(lengths[0])
                except ValueError:return await self.error(send,400,'INVALID_CONTENT_LENGTH','Invalid request length.')
                if length>self.max_body:return await self.error(send,413,'REQUEST_TOO_LARGE','Whole request exceeds local body limit.')
            body=bytearray();deadline=asyncio.get_running_loop().time()+self.body_timeout
            while True:
                remaining=deadline-asyncio.get_running_loop().time()
                if remaining<=0:return await self.error(send,408,'REQUEST_BODY_TIMEOUT','Local request body timeout; no execution started.')
                try:message=await asyncio.wait_for(receive(),remaining)
                except asyncio.TimeoutError:return await self.error(send,408,'REQUEST_BODY_TIMEOUT','Local request body timeout; no execution started.')
                if message['type']=='http.disconnect':return
                if message['type']!='http.request':continue
                chunk=message.get('body',b'')
                if len(chunk)>self.max_body-len(body):return await self.error(send,413,'REQUEST_TOO_LARGE','Whole request exceeds local body limit.')
                body.extend(chunk)
                if len(body)>self.max_body:return await self.error(send,413,'REQUEST_TOO_LARGE','Whole request exceeds local body limit.')
                if not message.get('more_body',False):break
            if lengths and len(body)!=length:return await self.error(send,400,'CONTENT_LENGTH_MISMATCH','Request body does not match declared length.')
            payload=bytes(body);del body
            delivered=False
            async def replay():
                nonlocal delivered
                if not delivered:delivered=True;return {'type':'http.request','body':payload,'more_body':False}
                return await receive()
            await self.app(scope,replay,send)
        finally:self.slots.release()
