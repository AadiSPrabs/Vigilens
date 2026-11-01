"""Reviewer-delta coverage (connect-3): exact image-error status mapping on the governed
route, fail-closed cross-process locking, CLI/seamless lock sharing with sidecar resync.
Synthetic scope only; no network."""
import hashlib, io, json
import pytest
from PIL import Image
from fastapi.testclient import TestClient

import dev_install as di
from app import create_app
from fresh_review.demo_approvals import SeamlessDemoApprovalStore


def _png(color, size=(80, 80)):
    im = Image.new('RGB', size, color); out = io.BytesIO(); im.save(out, 'PNG')
    return out.getvalue()


def _rotated_jpeg():
    im = Image.new('RGB', (60, 40), (10, 20, 30))
    exif = Image.Exif(); exif[274] = 6  # orientation: rotate 90
    out = io.BytesIO(); im.save(out, 'JPEG', exif=exif)
    return out.getvalue()


def _client(tmp_path):
    di.create_state(tmp_path / 'state', images=(), cors_origins=['http://localhost:5199'], seamless=True)
    service, token, origins = di.load_service(str(tmp_path / 'state' / 'dev-config.json'))
    return TestClient(create_app(fresh_service=service, fresh_token=token, cors_origins=origins)), token


def _H(token):
    return {'X-Vigilens-Local-Access': token, 'X-Vigilens-Display-Session': '7a' * 32}


def test_oversized_upload_keeps_413_not_generic_409(tmp_path):
    client, token = _client(tmp_path)
    big = b'\x89PNG\r\n\x1a\n' + b'0' * (15_000_100)
    r = client.post('/fresh-review-audit-governed', files={'image': ('big.png', big, 'image/png')},
                    data={'zones': '[]'}, headers=_H(token))
    assert r.status_code == 413
    assert r.json()['error']['code'] == 'IMAGE_TOO_LARGE'


def test_exif_rotated_upload_keeps_422_and_records_no_approval(tmp_path):
    client, token = _client(tmp_path)
    r = client.post('/fresh-review-audit-governed', files={'image': ('r.jpg', _rotated_jpeg(), 'image/jpeg')},
                    data={'zones': '[]'}, headers=_H(token))
    assert r.status_code == 422
    assert r.json()['error']['code'] == 'IMAGE_ORIENTATION_UNSUPPORTED'
    # refused before approval recording: the seamless store stays empty
    doc = json.loads((tmp_path / 'state' / 'approvals.json').read_bytes())
    assert doc['approvals'] == {}


def test_unsupported_media_keeps_415(tmp_path):
    client, token = _client(tmp_path)
    gif = b'GIF89a' + b'\x00' * 100
    r = client.post('/fresh-review-audit-governed', files={'image': ('a.gif', gif, 'image/gif')},
                    data={'zones': '[]'}, headers=_H(token))
    assert r.status_code == 415
    assert r.json()['error']['code'] == 'UNSUPPORTED_MEDIA_TYPE'


def test_lock_failure_fails_closed_never_unlocked(tmp_path, monkeypatch):
    path = tmp_path / 'approvals.json'
    raw = b'{"version":1,"approvals":{}}\n'
    path.write_bytes(raw); path.chmod(0o600)
    store = SeamlessDemoApprovalStore(path, hashlib.sha256(raw).hexdigest())
    import fcntl
    monkeypatch.setattr(fcntl, 'flock', lambda *a, **k: (_ for _ in ()).throw(OSError('lock down')))
    with pytest.raises(ValueError, match='lock'):
        store.lookup('a' * 64, [80, 80])
    # nothing recorded, file untouched
    assert json.loads(path.read_bytes())['approvals'] == {}


def test_cli_approve_serializes_and_running_seamless_server_resyncs(tmp_path):
    di.create_state(tmp_path / 'state', images=(), cors_origins=['http://localhost:5199'], seamless=True)
    approvals_path = tmp_path / 'state' / 'approvals.json'
    raw = approvals_path.read_bytes()
    # a "running server": seamless store holding the install-time pin
    server = SeamlessDemoApprovalStore(approvals_path, hashlib.sha256(raw).hexdigest())
    server.lookup('b' * 64, [80, 80])  # one seamless upload recording first
    img = tmp_path / 'seed.png'; img.write_bytes(_png('grey'))
    digest = di.approve_image(tmp_path / 'state', img)
    # the same server object resyncs via the lock + sidecar: no restart, both entries present
    frame = __import__('core').decode_image(img.read_bytes(), 'image/png')
    spec = server.lookup(frame.digest, [frame.width, frame.height])
    assert spec['rights_reference'] == 'developer-install-provided-test-image'
    doc = json.loads(approvals_path.read_bytes())['approvals']
    assert set(doc) == {'b' * 64, frame.digest}
    assert digest == frame.digest
    sidecar = approvals_path.with_name('approvals.recorded-sha256').read_text().strip()
    assert sidecar == hashlib.sha256(approvals_path.read_bytes()).hexdigest()
    # config pin advanced too (restart consistency either way)
    config = json.loads((tmp_path / 'state' / 'dev-config.json').read_text())
    assert config['approval_sha256'] == sidecar
