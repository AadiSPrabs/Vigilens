"""Developer synthetic integration mode: wired end-to-end, offline, per-install only."""
import asyncio
import json

import pytest
from PIL import Image
import io
from fastapi.testclient import TestClient

import dev_install
from app import create_app
from core import decode_image
from fresh_review.synthetic_transport import SyntheticTransport, _sam_segmentation_text
from pipeline import Frame
from sam_parser import parse_sam_image_text

SESSION = 'd5' * 32  # 64-hex stand-in for the proxy displaySessionFor value


def png(color, size=(80, 80)):
    im = Image.new('RGB', size, color)
    out = io.BytesIO()
    im.save(out, 'PNG')
    return out.getvalue()


def make_install(tmp_path, raws=(), origins=('http://localhost:5173',)):
    files = []
    for i, raw in enumerate(raws):
        path = tmp_path / ('seed-%d.png' % i)
        path.write_bytes(raw)
        files.append(path)
    dev_install.create_state(tmp_path / 'state', images=files, cors_origins=list(origins))
    service, token, cors = dev_install.load_service(tmp_path / 'state' / 'dev-config.json')
    calls = []
    service.transport = SyntheticTransport(calls=calls)
    client = TestClient(create_app(fresh_service=service, fresh_token=token, cors_origins=cors))
    return service, token, cors, client, calls


def auth(token, session=SESSION):
    return {'X-Vigilens-Local-Access': token, 'X-Vigilens-Display-Session': session}


def governed(client, token, raw):
    return client.post('/fresh-review-audit-governed', files={'image': ('t.png', raw, 'image/png')},
                       data={'zones': '[]'}, headers=auth(token))


def test_setup_creates_private_per_install_state(tmp_path):
    service, token, cors, client, calls = make_install(tmp_path)
    state = tmp_path / 'state'
    for name in ('carry.json', 'approvals.json', 'access-token.txt', 'dev-config.json'):
        assert (state / name).stat().st_mode & 0o777 == 0o600
    assert json.loads((state / 'approvals.json').read_bytes()) == {'version': 1, 'approvals': {}}
    carry = json.loads((state / 'carry.json').read_bytes())
    assert carry['aggregate_cap_usd'] == '5' and carry['provider_calls_total'] == 0
    config = json.loads((state / 'dev-config.json').read_bytes())
    assert config['mode'] == 'developer_synthetic_offline'
    assert len(token) == 48 and all(33 <= ord(c) <= 126 for c in token)
    with pytest.raises(ValueError):
        dev_install.create_state(state)  # non-empty state dir is refused


def test_gate_open_paths_and_key_enforcement(tmp_path):
    service, token, cors, client, calls = make_install(tmp_path)
    assert client.get('/health').status_code == 200
    assert client.get('/fresh-review/' + 'a' * 64).status_code == 403  # gated without key
    assert client.get('/openapi.json').status_code == 403  # docs gated too
    with_key = client.get('/openapi.json', headers={'X-Vigilens-Local-Access': token})
    assert with_key.status_code == 200
    paths = with_key.json()['paths']
    assert '/fresh-review-audit-governed' in paths and '/fresh-review/{source}/frontend-audit' in paths


def test_unapproved_image_refused_no_call(tmp_path):
    service, token, cors, client, calls = make_install(tmp_path)
    r = governed(client, token, png('blue'))
    assert r.status_code == 409 and calls == []
    assert not (tmp_path / 'state' / 'dev.sqlite').exists()


def test_governed_new_image_end_to_end_and_stored_repeat(tmp_path):
    raw = png('blue')
    service, token, cors, client, calls = make_install(tmp_path, raws=(raw,))
    r = governed(client, token, raw)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['schema_version'] == '0.2-local-draft' and body['audit_id'].startswith('fresh:')
    assert 1 <= len(body['persons']) <= 2 and body['evidence_export_allowed'] is False
    assert body['zones_applied'] is False and body['provider_calls_this_request'] is None
    assert 'provider_calls_note' in body  # a governed run happened; the count lives only in the ledger
    first_calls = len(calls)
    assert first_calls == 1 + len(body['persons'])  # 1 SAM + 1 PPE per person
    again = governed(client, token, raw)
    assert again.status_code == 200 and len(calls) == first_calls  # stored result, no new calls
    assert 'provider_calls_note' not in again.json()
    assert again.json()['audit_id'] == body['audit_id']


def test_frontend_audit_session_binding(tmp_path):
    raw = png('green')
    service, token, cors, client, calls = make_install(tmp_path, raws=(raw,))
    source = decode_image(raw, 'image/png').digest
    assert governed(client, token, raw).status_code == 200
    ok = client.get('/fresh-review/' + source + '/frontend-audit', headers=auth(token))
    assert ok.status_code == 200 and ok.json()['audit_id'].startswith('fresh:' + source)
    other = client.get('/fresh-review/' + source + '/frontend-audit',
                       headers=auth(token, session='c9' * 32))
    assert other.status_code == 409
    job = client.get('/fresh-review/' + source, headers=auth(token))
    assert job.status_code == 200 and job.json()['state'] == 'completed'
    assert job.json()['provider_call_count_status'] == 'attempts_recorded_debit_unchecked'


def test_many_completed_runs_stay_under_cap(tmp_path):
    raws = [png(c) for c in ('red', 'green', 'blue', 'yellow')]
    service, token, cors, client, calls = make_install(tmp_path, raws=raws)
    for raw in raws:
        r = governed(client, token, raw)
        assert r.status_code == 200, r.text  # completed runs book only small actual listed costs


def test_approve_tool_then_fresh_load(tmp_path):
    service, token, cors, client, calls = make_install(tmp_path)
    raw = png('purple')
    image = tmp_path / 'later.png'
    image.write_bytes(raw)
    digest = dev_install.approve_image(tmp_path / 'state', image)
    assert digest == decode_image(raw, 'image/png').digest
    service2, token2, cors2 = dev_install.load_service(tmp_path / 'state' / 'dev-config.json')
    service2.transport = SyntheticTransport(calls=calls)
    client2 = TestClient(create_app(fresh_service=service2, fresh_token=token2, cors_origins=cors2))
    assert governed(client2, token2, raw).status_code == 200  # approve while stopped, then restart


def test_synthetic_transport_rules_and_determinism():
    from adapters import build_sam_image_request
    t = SyntheticTransport()
    body = build_sam_image_request(png('blue'), 'image/png', 'person')
    body['store'] = False
    with pytest.raises(ValueError):
        t({'model': 'sam-3.1', 'store': True})
    with pytest.raises(ValueError):
        t({'model': 'other', 'store': False})
    with pytest.raises(ValueError):
        t({'model': 'sam-3.1', 'store': False, 'tools': ['x']})
    assert t(body) == t(body)


def test_sam_text_official_parser_one_and_two_persons():
    one = asyncio.run(parse_sam_image_text(_sam_segmentation_text(80, 80, bytes(range(32))), Frame(80, 80, 'x'), wire_completed=True))
    two = asyncio.run(parse_sam_image_text(_sam_segmentation_text(80, 80, bytes([1]) + bytes(range(1, 32))), Frame(80, 80, 'y'), wire_completed=True))
    assert len(one['objects']) == 1 and len(two['objects']) == 2
    for obj in two['objects']:
        (x1, y1, x2, y2) = obj['box_half_open']
        assert obj['mask'].size == (x2 - x1, y2 - y1) and set(obj['mask'].tobytes()) == {255}
    a, b = [o['box_half_open'] for o in two['objects']]
    assert a[2] <= b[0] or b[2] <= a[0]  # disjoint, no cross-person crop ambiguity


def test_cors_allowed_and_refused_origins(tmp_path):
    service, token, cors, client, calls = make_install(tmp_path, origins=('http://localhost:3000',))
    preflight = client.options('/fresh-review-audit-governed', headers={
        'Origin': 'http://localhost:3000', 'Access-Control-Request-Method': 'POST'})
    assert preflight.status_code == 200
    assert preflight.headers.get('access-control-allow-origin') == 'http://localhost:3000'
    refused = client.options('/fresh-review-audit-governed', headers={
        'Origin': 'http://evil.example', 'Access-Control-Request-Method': 'POST'})
    assert refused.status_code == 400
    assert 'access-control-allow-origin' not in {k.lower(): v for k, v in refused.headers.items()}


def test_no_network_in_synthetic_module():
    import inspect
    import fresh_review.synthetic_transport as module
    source = inspect.getsource(module)
    for banned in ('import socket', 'import urllib', 'import httpx', 'import requests', 'urlopen'):
        assert banned not in source
