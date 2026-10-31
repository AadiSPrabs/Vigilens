"""Loopback launcher: serves the built UI bundle plus POST /audit on 127.0.0.1:<port>. Reads the backend access token from a private file
(mode 0600, absolute path); never prints it. Prints/open a ONE-TIME launch URL (nonce) to the launching user only. Starts no provider transport."""
import argparse,os,secrets,httpx,uvicorn,webbrowser
from pathlib import Path
from local_ui_proxy import create_proxy

def main():
    p=argparse.ArgumentParser(description='Local UI host + proxy for the unchanged Vigilens client')
    p.add_argument('--token-file',required=True);p.add_argument('--ui-dist',required=True);p.add_argument('--backend',default='http://127.0.0.1:8001');p.add_argument('--port',type=int,default=8000);p.add_argument('--no-open',action='store_true');p.add_argument('--governed-new-image',action='store_true',help='route POST /audit to the governed new-image handler. Does not enable dispatch: approvals, ledger and transport still decide, and refuse by default');p.add_argument('--accept-unverified-windows-token-file',action='store_true');a=p.parse_args()
    f=Path(a.token_file)
    if not f.is_absolute()or not f.is_file()or f.is_symlink()or (os.name!='nt'and f.stat().st_mode&0o077):p.error('Absolute private (0600) regular token file required')
    if not (Path(a.ui_dist)/'index.html').is_file():p.error('--ui-dist must contain a built index.html (built with VITE_AUDIT_MODE=backend VITE_API_BASE_URL=http://localhost:%d)'%a.port)
    if os.name=='nt'and not a.accept_unverified_windows_token_file:p.error('Windows: token-file permissions cannot be verified by this launcher. Keep the file in your private profile folder and pass --accept-unverified-windows-token-file to proceed.')
    if not a.backend.startswith(('http://127.0.0.1:','http://localhost:')):p.error('Backend must be loopback')
    if not 1024<=a.port<=65535:p.error('Use unprivileged loopback port')
    import re,glob
    js=''.join(open(g,encoding='utf-8',errors='ignore').read()for g in glob.glob(str(Path(a.ui_dist)/'**'/'*.js'),recursive=True))
    if ('http://localhost:%d'%a.port)not in js:p.error('The built bundle does not contain http://localhost:%d as its API base (found: %s). Rebuild with VITE_API_BASE_URL=http://localhost:%d or use the matching --port.'%(a.port,sorted(set(re.findall(r'http://localhost:\d+',js))),a.port))
    nonce=secrets.token_urlsafe(40);url='http://localhost:%d/launch#n=%s'%(a.port,nonce)
    import threading
    if not a.no_open:threading.Timer(1.5,lambda:webbrowser.open(url)).start()
    else:print('One-time launch URL (do not share):',url,flush=True)
    uvicorn.run(create_proxy(httpx.AsyncClient(base_url=a.backend,timeout=70),f.read_text().strip(),launch_nonce=nonce,ui_dir=a.ui_dist,port=a.port,governed_new_image=a.governed_new_image),host='127.0.0.1',port=a.port,access_log=False)
if __name__=='__main__':main()
