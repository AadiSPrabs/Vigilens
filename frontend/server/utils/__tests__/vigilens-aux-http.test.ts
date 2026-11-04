// Actual handler + proxy HTTP wiring, synthetic local servers only.
import { describe, it, expect, vi } from "vitest";
import http from "node:http";
import { createApp, createRouter, toNodeListener, defineEventHandler } from "h3";
vi.mock("@agent-native/core/server", () => ({ getSession: async () => ({ email: "test@local.invalid", token: "synthetic-session-token" }) }));
import { setVisitorKey, _resetVisitorKeys } from "../vigilens-keys";
import explain from "../../routes/api/vigilens/private-report/[sid]/explanation/[attempt].post";
import reserve from "../../routes/api/vigilens/private-report/[sid]/explanation-reservation.post";
import recheck from "../../routes/api/vigilens/fresh-review/[source]/recheck/[attempt].post";
import recheckReserve from "../../routes/api/vigilens/fresh-review/[source]/recheck-reservation.post";
import status from "../../routes/api/vigilens/fresh-review-job-status.post";
import clip from "../../routes/api/vigilens/fresh-review-clip-upload.post";
import loop from "../../routes/api/vigilens/fresh-review/[source]/bounded-review-loop.post";
const listen = async (s: http.Server) => { await new Promise<void>(r => s.listen(0,"127.0.0.1",r)); return `http://127.0.0.1:${(s.address() as {port:number}).port}`; };
const close = async (s:http.Server) => { s.closeAllConnections(); await new Promise<void>(r=>s.close(()=>r())); };
it("forwards server-held key through every actual auxiliary route once, ignores spoof, preserves refusal", async () => {
 const received:{path:string;key:string|undefined;body:string}[]=[];
 const upstream=http.createServer(async(req,res)=>{let body="";for await(const c of req)body+=c;received.push({path:req.url!,key:req.headers['x-vigilens-visitor-key'] as string,body});res.writeHead(503,{'content-type':'application/json'});res.end('{"detail":"synthetic refusal"}');});
 const app=createApp(),router=createRouter(); const source="a".repeat(64),attempt="b".repeat(64),sid="synthetic-session";
 const rows:[string,any,string][]=[
 [`/fresh-review-job-status`,status,`/fresh-review-job-status`],
 [`/fresh-review-clip-upload`,clip,`/fresh-review-clip-upload`],
 [`/private-report/:sid/explanation/:attempt`,explain,`/fresh-private-report/${sid}/explanation/${attempt}`],
 [`/private-report/:sid/explanation-reservation`,reserve,`/fresh-private-report/${sid}/explanation-reservation`],
 [`/fresh-review/:source/recheck/:attempt`,recheck,`/fresh-review/${source}/recheck/${attempt}`],
 [`/fresh-review/:source/recheck-reservation`,recheckReserve,`/fresh-review/${source}/recheck-reservation`],
 [`/fresh-review/:source/bounded-review-loop`,loop,`/fresh-review/${source}/bounded-review-loop`]];
 for(const [path,h] of rows)router.post('/api/vigilens'+path,h);
 router.get('/_agent-native/auth/session',defineEventHandler(()=>({email:'test@local.invalid'})));app.use(router);const frontend=http.createServer(toNodeListener(app));
 process.env.VIGILENS_BACKEND_URL=await listen(upstream);process.env.VIGILENS_LOCAL_ACCESS_TOKEN='synthetic-backend-token';const base=await listen(frontend);
 try{
 setVisitorKey({email:'test@local.invalid',token:'synthetic-session-token'},'synthetic-held-key');
 for(const [path,,expected] of rows){const route=path.replace(':source',source).replace(':sid',sid).replace(':attempt',attempt);const response=await fetch(base+'/api/vigilens'+route,{method:'POST',headers:{cookie:'an_session=synthetic-session-token','content-type':'application/json','x-vigilens-visitor-key':'spoofed-client-key'},body:'{"synthetic":true}'});expect(response.status).toBe(503);expect(await response.json()).toEqual({detail:'synthetic refusal'});expect(received[received.length-1]).toEqual({path:expected,key:'synthetic-held-key',body:'{"synthetic":true}'});}
 expect(received).toHaveLength(7);
 _resetVisitorKeys();await fetch(base+'/api/vigilens'+rows[0]![0].replace(':sid',sid).replace(':attempt',attempt),{method:'POST',headers:{cookie:'an_session=synthetic-session-token','x-vigilens-visitor-key':'spoofed-client-key'},body:'{}'});expect(received[received.length-1]?.key).toBeUndefined();expect(received).toHaveLength(8);
 }finally{_resetVisitorKeys();delete process.env.VIGILENS_BACKEND_URL;delete process.env.VIGILENS_LOCAL_ACCESS_TOKEN;await close(frontend);await close(upstream);}
});
