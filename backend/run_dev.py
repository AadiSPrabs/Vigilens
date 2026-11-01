"""Loopback developer server for the OFFLINE synthetic integration mode.

Serves the real backend routes (fixture /audit, governed fresh upload, stored review/report
views) on 127.0.0.1 with the deterministic SyntheticTransport: the full request/response
contract works end to end with zero network, zero provider cost and no owner data. The
per-install API key (created by dev_install.py) gates every route except /health and the
fixture /audit skeleton, exactly like the private runtime. This is not a deployment entry
point: the bind is loopback-only by design, the synthetic mode cannot make real provider
calls, and live analysis still needs owner source approvals, accounting authority and a
real transport, none of which this mode provides.
"""
import argparse
import sys
import uvicorn

from app import create_app
from dev_install import load_service


def main():
    p = argparse.ArgumentParser(description='Vigilens OFFLINE developer server (synthetic transport, loopback only)')
    p.add_argument('--config', required=True, help='dev-config.json written by dev_install.py')
    p.add_argument('--port', type=int, default=8001)
    p.add_argument('--transport', choices=('synthetic', 'meta'), default='synthetic',
                   help='synthetic (default, offline) or meta (real provider via --key-file; governed controls and the install cap still decide every call)')
    p.add_argument('--key-file', help='meta transport only: absolute 0600 file holding the developer-owned provider key (given by the account owner directly; never committed or shared)')
    a = p.parse_args()
    if not 1024 <= a.port <= 65535:
        p.error('Use an unprivileged local port 1024..65535')
    if a.transport == 'synthetic' and a.key_file:
        p.error('--key-file only with --transport meta')
    service, token, origins = load_service(a.config, transport=a.transport, key_file=a.key_file)
    app = create_app(fresh_service=service, fresh_token=token, cors_origins=origins)
    print('Vigilens developer server (%s mode).' % ('OFFLINE synthetic' if a.transport == 'synthetic' else 'LIVE provider - real calls spend the configured key budget under the install cap and approvals'))
    print('  base URL:    http://127.0.0.1:%d' % a.port)
    print('  OpenAPI:     http://127.0.0.1:%d/openapi.json (send X-Vigilens-Local-Access key)' % a.port)
    print('  CORS origins:', ', '.join(origins))
    print('  Send headers: X-Vigilens-Local-Access: <key from access-token.txt> and')
    print('                X-Vigilens-Display-Session: <any 32-128 char session value your frontend generates>')
    uvicorn.run(app, host='127.0.0.1', port=a.port, access_log=False)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError) as e:
        print('error: %s' % e, file=sys.stderr)
        sys.exit(2)
