"""Seamless-demo approval recording and tracking-only cap mode. Synthetic scope, no network."""
import asyncio,hashlib,io,json,threading
import pytest
from PIL import Image
from core import decode_image
from fresh_review.pipeline import FreshPipeline
import fresh_review.pipeline as m
from fresh_review.demo_approvals import SeamlessDemoApprovalStore
from fresh_test_helpers import response

def _img(w=80,h=80,color='blue'):
    im=Image.new('RGB',(w,h),color);out=io.BytesIO();im.save(out,'PNG');raw=out.getvalue()
    return raw,decode_image(raw,'image/png')

def _empty_store(tmp_path,scope='synthetic_local_qualification'):
    path=tmp_path/'approvals.json';raw=b'{"version":1,"approvals":{}}\n';path.write_bytes(raw);path.chmod(0o600)
    return SeamlessDemoApprovalStore(path,hashlib.sha256(raw).hexdigest(),scope=scope)

def _carry(tmp_path,cap='5'):
    raw=json.dumps({'blocked_source_digests':[],'provider_calls_total':0,'conservative_booked_usd':'0','aggregate_cap_usd':cap,'provenance':'generated-test-only-not-real-budget'}).encode()
    path=tmp_path/'carry.json';path.write_bytes(raw);path.chmod(0o600)
    return {'carry_path':path,'carry_sha':hashlib.sha256(raw).hexdigest()}

def _pipeline(tmp_path,monkeypatch,store,cap='5',cap_enforcement=True):
    calls=[]
    async def parse(*a,**k):
        return {'objects':[{'object_id':'0','box_half_open':[0,0,20,60],'mask':Image.new('L',(20,60),255)}]}
    monkeypatch.setattr(m,'parse_sam_image_text',parse)
    def transport(body):
        calls.append(body)
        if body['model']=='sam-3.1':return b'data: {"type":"response.completed","response":{"model":"sam-3.1","id":"synthetic-sam","status":"completed","usage":{"images_processed":1},"output":[]}}\n\n'
        return response('unknown','absent')
    p=FreshPipeline(tmp_path/'fresh.sqlite',**_carry(tmp_path,cap),execution_scope='synthetic_local_qualification',
                    approval_store=store,transport=transport,cap_enforcement=cap_enforcement)
    return p,calls

def test_record_on_miss_then_pinned_lookup(tmp_path):
    store=_empty_store(tmp_path)
    spec=store.lookup('a'*64,[80,80])
    assert spec['provider_upload_approved'] is True and spec['provenance']['scope']=='synthetic_local_qualification'
    assert 'not-owner-authority' in spec['provenance']['owner_instruction_reference']
    assert 'no-provider-upload-occurs' in spec['provenance']['rights_review_reference']
    # pin rebound in-process: file matches the store's pin, repeat lookup is stable
    raw=store.path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==store.sha
    assert store.lookup('a'*64,[80,80])==spec
    assert json.loads(raw)['approvals']['a'*64]['rights_reference'].startswith('seamless-upload-recorded-at-upload')

def test_never_overwrites_existing_entry(tmp_path):
    store=_empty_store(tmp_path)
    doc=json.loads(store.path.read_bytes());doc['approvals']['b'*64]={'size':'bogus'}
    raw=(json.dumps(doc,sort_keys=True)+'\n').encode();store.path.write_bytes(raw);store.path.chmod(0o600)
    store.sha=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):store.lookup('b'*64,[80,80])
    assert json.loads(store.path.read_bytes())['approvals']['b'*64]=={'size':'bogus'}

def test_live_scope_recording_labelled_owner_configured(tmp_path):
    store=_empty_store(tmp_path,scope='private_provider_processing')
    spec=store.lookup('c'*64,[80,80])
    assert spec['provenance']['scope']=='private_provider_processing'
    assert 'owner-configured' in spec['provenance']['owner_instruction_reference']

def test_bad_scope_refused(tmp_path):
    with pytest.raises(ValueError):_empty_store(tmp_path,scope='public_demo')

def test_concurrent_record_single_writer(tmp_path):
    store=_empty_store(tmp_path);out=[];errs=[]
    def hit():
        try:out.append(store.lookup('d'*64,[80,80]))
        except Exception as e:errs.append(e)
    ts=[threading.Thread(target=hit) for _ in range(8)]
    [t.start() for t in ts];[t.join() for t in ts]
    assert not errs and len(out)==8 and all(s==out[0] for s in out)
    assert len(json.loads(store.path.read_bytes())['approvals'])==1

def test_pipeline_runs_new_images_without_restart_or_cli(tmp_path,monkeypatch):
    store=_empty_store(tmp_path)
    p,calls=_pipeline(tmp_path,monkeypatch,store)
    raw1,f1=_img(color='blue');raw2,f2=_img(color='red')
    r1=asyncio.run(p.run(raw1,'image/png',[]));assert r1['state']=='completed'and len(calls)==2
    # second, different image: recorded at upload, no restart, no CLI approval
    r2=asyncio.run(p.run(raw2,'image/png',[]));assert r2['state']=='completed'and len(calls)==4
    # repeat upload of the first image serves the stored result: no new dispatch
    r3=asyncio.run(p.run(raw1,'image/png',[]));assert r3['state']=='completed'and len(calls)==4
    approvals=json.loads(store.path.read_bytes())['approvals']
    assert set(approvals)=={f1.digest,f2.digest}

def test_cap_tracking_only_still_books(tmp_path,monkeypatch):
    store=_empty_store(tmp_path)
    raw,f=_img()
    # cap far below the reservation: enforced mode refuses before any claim
    p,_=_pipeline(tmp_path,monkeypatch,store,cap='0.0001')
    with pytest.raises(ValueError):asyncio.run(p.run(raw,'image/png',[]))
    # tracking-only mode: same booking path, refusal skipped; job completes and cost is booked in full
    store2=_empty_store(tmp_path)
    import fresh_review.pipeline as pl
    p2,_=_pipeline(tmp_path,monkeypatch,store2,cap='0.0001',cap_enforcement=False)
    r=asyncio.run(p2.run(raw,'image/png',[]));assert r['state']=='completed'
    assert r['reservation_usd']==str(pl.RESERVE) and float(r['known_listed_usd'])>0

def test_restart_reloads_recorded_state_via_sidecar(tmp_path):
    store=_empty_store(tmp_path)
    spec=store.lookup('e'*64,[80,80])
    # simulate a backend restart: fresh store built the way load_service builds it
    import hashlib as h
    from pathlib import Path
    sidecar=store.path.with_name('approvals.recorded-sha256')
    assert sidecar.is_file()
    pin=sidecar.read_text().strip()
    assert h.sha256(store.path.read_bytes()).hexdigest()==pin
    reloaded=SeamlessDemoApprovalStore(store.path,pin,scope='synthetic_local_qualification')
    assert reloaded.lookup('e'*64,[80,80])==spec

# ---- Live (meta) transport path over a fake-HTTP boundary: the exact frontend request,
# ---- seamless live-scope recording, provider-error holds, geometry/zones. No network.

import io as _io
from PIL import Image as _Image
from fastapi.testclient import TestClient as _TC
import dev_install as _di
from app import create_app as _create_app
from fresh_review.synthetic_transport import SyntheticTransport as _Syn
from fresh_review.transport import MetaTransport as _Meta

def _png(color, size=(80, 80)):
    im = _Image.new('RGB', size, color); out = _io.BytesIO(); im.save(out, 'PNG')
    return out.getvalue()

class _FakeResp:
    def __init__(self, status, payload): self.status, self.payload = status, payload
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n): return self.payload

class _LiveIdOpener:
    """urllib-boundary fake provider: replies carry NON-synthetic response ids, so the
    live origin labelling path is exercised. Swaps ids to an equal-length 'live-prov-' token."""
    def __init__(self, status=200):
        self.requests = []; self.status = status; self.synthetic = _Syn()
    def open(self, request, timeout=None):
        self.requests.append(request)
        payload = self.synthetic(json.loads(request.data)).replace(b'synthetic-', b'live-prov-')
        return _FakeResp(self.status, payload)

def _key(tmp_path):
    p = tmp_path / 'developer-key.txt'; p.write_bytes(b'developer-owned-test-key-not-real-0123456789'); p.chmod(0o600)
    return str(p)

def _seamless_meta_client(tmp_path, opener):
    _di.create_state(tmp_path / 'state', images=(), cors_origins=['http://localhost:5199'], seamless=True)
    service, token, origins = _di.load_service(str(tmp_path / 'state' / 'dev-config.json'),
                                               transport='meta', key_file=_key(tmp_path))
    assert isinstance(service.transport, _Meta)
    service.transport.opener = opener  # test-only boundary swap; request build and key handling stay real
    return _TC(_create_app(fresh_service=service, fresh_token=token, cors_origins=origins)), token, service

_H = lambda token: {'X-Vigilens-Local-Access': token, 'X-Vigilens-Display-Session': '8b' * 32}

def test_seamless_meta_upload_records_live_scope_and_live_origin(tmp_path):
    raw = _png('teal')
    opener = _LiveIdOpener()
    client, token, service = _seamless_meta_client(tmp_path, opener)
    zones = json.dumps([{'id': 'z1', 'name': 'Scaffold edge', 'hazard': True,
                         'points': [{'x': 0.1, 'y': 0.1}, {'x': 0.5, 'y': 0.1}, {'x': 0.5, 'y': 0.5}]}])
    r = client.post('/fresh-review-audit-governed', files={'image': ('t.png', raw, 'image/png')},
                    data={'zones': zones}, headers=_H(token))
    assert r.status_code == 200, r.text
    body = r.json()
    # live origin labelling from the recorded (fake) provider response ids
    assert body['readings_origin'] == 'live_provider'
    assert body['person_geometry_origin'] == 'provider_returned_unvalidated'
    # zones validated and echoed; membership/matrix applied to the stored masks as draft evaluations (never compliance claims)
    assert body['zones'] and body['zones'][0]['id'] == 'z1' and body['zones_applied'] is True
    assert body['ruleset_version'] == 'draft-unapproved' and 'never compliance determinations' in body['zones_applied_meaning']
    # geometry usable: normalized polygons inside the unit square, 4-point boxes
    for person in body['persons']:
        assert len(person['polygon']) == 4
        assert all(0 <= q['x'] <= 1 and 0 <= q['y'] <= 1 for q in person['polygon'])
        assert all(f['kind'] == 'uncertainty' for f in person['findings'])
        # readings unknown -> no violations; membership itself resolved from the stored mask, no provider call at view time
        assert person['zone_membership_status'] == 'known' and person['ground_contact']['basis'] == 'mask_derived_estimate_unverified'
    # exact wire requests hit the provider endpoint with the bearer key
    assert [json.loads(q.data)['model'] for q in opener.requests][0] == 'sam-3.1'
    for q in opener.requests:
        assert q.full_url == 'https://api.meta.ai/v1/responses'
        assert q.get_header('Authorization') == 'Bearer developer-owned-test-key-not-real-0123456789'
    # seamless live approval recorded at upload, labelled owner-configured
    import hashlib as _h
    digest = _h.sha256  # frame digest comes from the recorded approvals file
    approvals = json.loads((tmp_path / 'state' / 'approvals.json').read_bytes())['approvals']
    assert len(approvals) == 1
    prov = list(approvals.values())[0]['provenance']
    assert prov['scope'] == 'private_provider_processing'
    assert 'owner-configured' in prov['owner_instruction_reference']

def test_seamless_meta_provider_error_held_never_retried(tmp_path):
    raw = _png('olive')
    opener = _LiveIdOpener(status=500)
    client, token, service = _seamless_meta_client(tmp_path, opener)
    r = client.post('/fresh-review-audit-governed', files={'image': ('t.png', raw, 'image/png')},
                    data={'zones': '[]'}, headers=_H(token))
    assert r.status_code == 409
    assert r.json()['detail']['code'] == 'ATTEMPT_UNCERTAIN'
    calls = len(opener.requests)
    again = client.post('/fresh-review-audit-governed', files={'image': ('t.png', raw, 'image/png')},
                        data={'zones': '[]'}, headers=_H(token))
    assert again.status_code == 409 and len(opener.requests) == calls  # held, no automatic retry

def test_two_processes_no_lost_recording(tmp_path):
    """Real multiprocess contention: two interpreter processes record different digests
    against one state directory; both recordings must survive."""
    import subprocess, sys, textwrap
    store = _empty_store(tmp_path)
    script = textwrap.dedent('''
        import sys, hashlib
        sys.path.insert(0, %r)
        from fresh_review.demo_approvals import SeamlessDemoApprovalStore
        path = sys.argv[1]; digest = sys.argv[2]
        raw = open(path, 'rb').read()
        s = SeamlessDemoApprovalStore(path, hashlib.sha256(raw).hexdigest())
        s.lookup(digest, [80, 80])
        print('ok')
    ''') % (str(tmp_path.parent.parent.resolve()),)
    procs = [subprocess.Popen([sys.executable, '-c', script, str(store.path), d * 64],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for d in ('f', '0')]
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0 and out.strip() == b'ok', err.decode()
    approvals = json.loads(store.path.read_bytes())['approvals']
    assert set(approvals) == {'f' * 64, '0' * 64}
    sidecar = store.path.with_name('approvals.recorded-sha256').read_text().strip()
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == sidecar
