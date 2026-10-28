"""Explicit loopback-only private provider entry. Never deploy this as public auth."""
import argparse,uvicorn
from fresh_review.runtime import from_config

def main():
    p=argparse.ArgumentParser(description='Explicit private Meta-backed manual review server; real calls require source approval and retained budget')
    p.add_argument('--config',required=True);p.add_argument('--port',type=int,default=8001);a=p.parse_args()
    if not 1024<=a.port<=65535:p.error('Use unprivileged loopback port')
    uvicorn.run(from_config(a.config),host='127.0.0.1',port=a.port,access_log=False)
if __name__=='__main__':main()
