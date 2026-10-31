const http = require('http')
const WebSocket = require('C:/Users/admin/Documents/Vigilens/frontend/node_modules/ws')
const HOST='127.0.0.1', PORT=9222
function httpJson(method,path){return new Promise((res,rej)=>{const r=http.request({host:HOST,port:PORT,method,path},x=>{let d='';x.on('data',c=>d+=c);x.on('end',()=>{try{res(d?JSON.parse(d):null)}catch(e){rej(new Error(d))}})});r.on('error',rej);r.end()})}
const sleep=ms=>new Promise(r=>setTimeout(r,ms))
async function main(){
  const t=await httpJson('PUT','/json/new?about:blank')
  const ws=new WebSocket(t.webSocketDebuggerUrl)
  let id=1;const p=new Map();const logs=[]
  ws.on('message',raw=>{const m=JSON.parse(raw);if(m.id&&p.has(m.id)){const {res,rej}=p.get(m.id);p.delete(m.id);m.error?rej(new Error(JSON.stringify(m.error))):res(m.result)}else if(m.method==='Runtime.consoleAPICalled'||m.method==='Runtime.exceptionThrown'){logs.push(m)}})
  await new Promise((r,j)=>{ws.on('open',r);ws.on('error',j)})
  const send=(method,params={})=>new Promise((res,rej)=>{const i=id++;p.set(i,{res,rej});ws.send(JSON.stringify({id:i,method,params}))})
  const ev=async e=>{const r=await send('Runtime.evaluate',{expression:e,returnByValue:true,awaitPromise:true,userGesture:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text+' '+(r.exceptionDetails.exception&&r.exceptionDetails.exception.description));return r.result.value}
  await send('Page.enable');await send('Runtime.enable')
  await send('Page.navigate',{url:'http://127.0.0.1:5176/'})
  await sleep(2000)
  console.log('URL',await ev('location.href'))
  console.log('TEXT',(await ev('document.body.innerText')).slice(0,1000))
  console.log('BUTTONS',await ev(`JSON.stringify([...document.querySelectorAll('.sample-btn')].map(b=>b.textContent))`))
  await ev(`(() => { const b=[...document.querySelectorAll('.sample-btn')].find(x=>x.textContent.trim()==='sample-1'); if(b) b.click(); return !!b })()`)
  await sleep(2000)
  console.log('TEXT2',(await ev('document.body.innerText')).slice(0,1200))
  console.log('IMG',await ev(`JSON.stringify((()=>{const i=document.querySelector('.zone-canvas-wrapper img'); return i?{src:i.src,nw:i.naturalWidth,complete:i.complete}:null})())`))
  console.log('LOGS',JSON.stringify(logs).slice(0,2000))
  await httpJson('GET',`/json/close/${t.id}`);ws.close()
}
main().catch(e=>{console.error(e);process.exit(1)})
