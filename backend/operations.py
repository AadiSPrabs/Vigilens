"""Opt-in bounded in-process operational guard for local loopback review.
Safe counters contain no raw URLs, image data, identities, headers or exceptions.
Not a public per-user rate/billing policy or distributed limiter.
"""
import threading
import time
import math
from collections import deque
from limits import LocalAdmissionLimits

class LocalOperations:
    def __init__(self,app,max_requests=120,period_seconds=60,clock=time.monotonic):
        if type(max_requests) is not int or not 1<=max_requests<=10000 or type(period_seconds) not in (int,float) or not math.isfinite(period_seconds) or period_seconds<=0:raise ValueError('Explicit finite local operational limits required')
        self.app=app;self.max_requests=max_requests;self.period=period_seconds;self.clock=clock;self.lock=threading.Lock();self.window=deque();self.counters={};self.duration_count=0;self.duration_total=0.;self.duration_max=0.
    def increment(self,key):self.counters[key]=self.counters.get(key,0)+1
    def snapshot(self):
        with self.lock:return {'counters':dict(self.counters),'duration_count':self.duration_count,'duration_total_seconds':self.duration_total,'duration_max_seconds':self.duration_max,'scope':'local_process_only_no_user_dimensions'}
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        start=self.clock();limited=False
        with self.lock:
            while self.window and self.window[0]<=start-self.period:self.window.popleft()
            if len(self.window)>=self.max_requests:self.increment('rate_limited');limited=True
            else:self.window.append(start);self.increment('admitted')
        if limited:return await LocalAdmissionLimits.error(self,send,429,'LOCAL_RATE_LIMIT','Local process request rate reached; no execution started.')
        status=None
        async def observe(message):
            nonlocal status
            if message['type']=='http.response.start':status=message['status']
            await send(message)
        try:await self.app(scope,receive,observe)
        except Exception:
            with self.lock:self.increment('unhandled_exception')
            raise
        finally:
            elapsed=max(0.,self.clock()-start)
            with self.lock:
                self.increment('status_'+str(status//100)+'xx' if type(status) is int and 100<=status<=599 else 'no_response_started')
                self.duration_count+=1;self.duration_total+=elapsed;self.duration_max=max(self.duration_max,elapsed)
