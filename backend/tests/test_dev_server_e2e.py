"""Developer server end-to-end verification: browser-style preflight/headers, the real
governed route over a fake-HTTP MetaTransport boundary (no provider network), strict
approval-scope refusal in both directions, and the run_dev launcher on real loopback."""
import io
import json
import subprocess
import sys
import time

import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient

import dev_install
from app import create_app
from fresh_review.synthetic_transport import SyntheticTransport
from fresh_review.transport import MetaTransport

SESSION = 'd5' * 32


def png(color, size=(80, 80)):
    im = Image.new('RGB', size, color)
    out = io.BytesIO()
    im.save(out, 'PNG')
    return out.getvalue()


def auth(token, session=SESSION):
    return {'X-Vigilens-Local-Access': token, 'X-Vigilens-Display-Session': session}


def key_file(tmp_path):
    path = tmp_path / 'developer-key.txt'
    path.write_bytes(b'developer-owned-test-key-not-real-0123456789')
    path.chmod(0o600)
    return path


class FakeResponse:
    def __init__(self, status, payload):
        self.status, self.payload = status, payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        return self.payload


class RecordingOpener:
    """urllib-boundary fake: records the exact request, replies via the deterministic
    synthetic payload generator so the official parser path still runs. No network."""
    def __init__(self):
        self.requests = []
        self.synthetic = SyntheticTransport()

    def open(self, request, timeout=None):
        body = json.loads(request.data)
        self.requests.append({'url': request.full_url, 'method': request.get_method(),
                              'authorization': request.get_header('Authorization'),
                              'content_type': request.get_header('Content-type'),
                              'model': body.get('model'), 'timeout': timeout})
        return FakeResponse(200, self.synthetic(body))


def make_state(tmp_path, raw, scope):
    (tmp_path / 'seed.png').write_bytes(raw)
    dev_install.create_state(tmp_path / 'state', images=[tmp_path / 'seed.png'],
                             cors_origins=['http://localhost:5173'])
    if scope != 'synthetic_local_qualification':
        dev_install.approve_image(tmp_path / 'state', tmp_path / 'seed.png', scope=scope)
    return str(tmp_path / 'state' / 'dev-config.json')


def test_preflight_allows_the_custom_contract_headers(tmp_path):
    config = make_state(tmp_path, png('navy'), 'synthetic_local_qualification')
    service, token, origins = dev_install.load_service(config)
    client = TestClient(create_app(fresh_service=service, fresh_token=token, cors_origins=origins))
    preflight = client.options('/fresh-review-audit-governed', headers={
        'Origin': 'http://localhost:5173',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'x-vigilens-local-access,x-vigilens-display-session,content-type'})
    assert preflight.status_code == 200
    assert preflight.headers.get('access-control-allow-origin') == 'http://localhost:5173'
    allowed = {h.strip().lower() for h in preflight.headers.get('access-control-allow-headers', '').split(',')}
    assert {'x-vigilens-local-access', 'x-vigilens-display-session', 'content-type'} <= allowed
    refused = client.options('/fresh-review-audit-governed', headers={
        'Origin': 'http://evil.example', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'x-vigilens-local-access'})
    assert refused.status_code == 400


def test_meta_transport_governed_route_fake_boundary(tmp_path):
    raw = png('teal')
    config = make_state(tmp_path, raw, 'private_provider_processing')
    service, token, origins = dev_install.load_service(config, transport='meta',
                                                       key_file=str(key_file(tmp_path)))
    assert isinstance(service.transport, MetaTransport)
    opener = RecordingOpener()
    service.transport.opener = opener  # test-only boundary swap; request building and key handling stay real
    client = TestClient(create_app(fresh_service=service, fresh_token=token, cors_origins=origins))
    response = client.post('/fresh-review-audit-governed',
                           files={'image': ('t.png', raw, 'image/png')}, data={'zones': '[]'},
                           headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['schema_version'] == '0.2-local-draft' and body['audit_id'].startswith('fresh:')
    assert 1 <= len(body['persons']) <= 2 and body['evidence_export_allowed'] is False
    assert body['provider_calls_this_request'] is None and body['provider_calls_note']
    models = [r['model'] for r in opener.requests]
    assert models and models[0] == 'sam-3.1' and 'muse-spark-1.3' in models
    for request in opener.requests:
        assert request['url'] == 'https://api.meta.ai/v1/responses' and request['method'] == 'POST'
        assert request['authorization'] == 'Bearer developer-owned-test-key-not-real-0123456789'
        assert request['content_type'] == 'application/json'
    repeat = client.post('/fresh-review-audit-governed',
                         files={'image': ('t.png', raw, 'image/png')}, data={'zones': '[]'},
                         headers=auth(token))
    assert repeat.status_code == 200
    assert len(opener.requests) == len(models)  # stored repeat makes no further calls


def test_cross_scope_approvals_refused_at_route_no_call(tmp_path):
    raw = png('maroon')
    # Synthetic-scope approval under a live (meta) execution scope: refuse, no provider request.
    config = make_state(tmp_path, raw, 'synthetic_local_qualification')
    service, token, origins = dev_install.load_service(config, transport='meta',
                                                       key_file=str(key_file(tmp_path)))
    opener = RecordingOpener()
    service.transport.opener = opener
    client = TestClient(create_app(fresh_service=service, fresh_token=token, cors_origins=origins))
    refused = client.post('/fresh-review-audit-governed',
                          files={'image': ('t.png', raw, 'image/png')}, data={'zones': '[]'},
                          headers=auth(token))
    assert refused.status_code == 409 and opener.requests == []
    # Live-scope approval under a synthetic execution scope: refuse, no synthetic call.
    (tmp_path / 'second').mkdir()
    config2 = make_state(tmp_path / 'second', raw, 'private_provider_processing')
    service2, token2, origins2 = dev_install.load_service(config2)
    calls = []
    service2.transport = SyntheticTransport(calls=calls)
    client2 = TestClient(create_app(fresh_service=service2, fresh_token=token2, cors_origins=origins2))
    refused2 = client2.post('/fresh-review-audit-governed',
                            files={'image': ('t.png', raw, 'image/png')}, data={'zones': '[]'},
                            headers=auth(token2))
    assert refused2.status_code == 409 and calls == []


def test_run_dev_launcher_real_loopback(tmp_path):
    raw = png('olive')
    config = make_state(tmp_path, raw, 'synthetic_local_qualification')
    port = 8931
    process = subprocess.Popen([sys.executable, 'run_dev.py', '--config', config, '--port', str(port)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    token = open(tmp_path / 'state' / 'access-token.txt').read().strip()
    try:
        base = 'http://127.0.0.1:%d' % port
        deadline = time.time() + 20
        up = False
        with httpx.Client(timeout=2.0) as http:
            while time.time() < deadline and not up:
                try:
                    up = http.get(base + '/health').status_code == 200
                except Exception:
                    time.sleep(0.3)
            assert up, 'run_dev server did not come up on loopback'
            denied = http.post(base + '/fresh-review-audit-governed',
                               files={'image': ('t.png', raw, 'image/png')}, data={'zones': '[]'},
                               headers={'X-Vigilens-Local-Access': 'wrong', 'X-Vigilens-Display-Session': SESSION,
                                        'Origin': 'http://localhost:5173'})
            assert denied.status_code == 403
            ran = http.post(base + '/fresh-review-audit-governed',
                            files={'image': ('t.png', raw, 'image/png')}, data={'zones': '[]'},
                            headers=auth(token) | {'Origin': 'http://localhost:5173'})
            assert ran.status_code == 200, ran.text
            assert ran.json()['audit_id'].startswith('fresh:') and 1 <= len(ran.json()['persons']) <= 2
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
