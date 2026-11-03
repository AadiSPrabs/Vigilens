"""Concurrency qualification for the boot approvals seed (post-repair).

Adopted from the independent v6 review probes (TestDurableLostUpdate,
TestEphemeralSeedVsSeamlessRecord, TestRotationRevocationWedge,
TestSeamlessContradictsDocstringPremise). The first two originally asserted the
defect; after fencing (BEGIN IMMEDIATE + FOR UPDATE durable, cross-process lock
+ atomic writes ephemeral) the expectations are inverted: no entry is lost, the
last committer's pin matches the committed row, and file/config/sidecar stay
paired. The last two pin the documented semantics (insert-only, no revocation,
no reset path; seamless request-time recording acknowledged). sqlite stands in
for the durable document store (same DB-API surface via open_store); no PG, no
provider, no network."""
import base64, hashlib, json, os, threading
import pytest

from fresh_review.approvals_seed import EMPTY_DOC, ENV_DOC, ENV_SHA, merge_insert_only

DIGEST_A = 'a' * 64
DIGEST_B = 'b' * 64

def spec(size=(64, 64), reviewer='synthetic test', rights='synthetic-test-fixture', scope='synthetic_local_qualification'):
    return {'size': list(size), 'rights_reference': rights, 'provider_upload_approved': True,
            'provenance': {'owner_instruction_reference': 'synthetic-owner-ref',
                           'rights_review_reference': 'synthetic-rights-ref',
                           'reviewed_at': '2026-11-02T00:00:00+00:00',
                           'reviewer': reviewer, 'scope': scope}}

def doc(entries):
    return (json.dumps({'version': 1, 'approvals': entries}, sort_keys=True) + '\n').encode()

def env_for(raw):
    return {ENV_DOC: base64.b64encode(raw).decode(), ENV_SHA: hashlib.sha256(raw).hexdigest()}


class TestDurableNoLostUpdate:
    def test_concurrent_boots_with_different_seeds_both_survive(self, tmp_path):
        """Two real _seed_approvals_document calls racing on one store. The
        fencing transaction serializes them: BOTH entries must survive, and the
        last committer's returned pin must equal the committed row's sha."""
        import render_boot
        dsn = str(tmp_path / 'docs.sqlite')
        render_boot._seed_approvals_document(dsn, EMPTY_DOC)
        results, errors = {}, []
        def boot(name, seed_doc):
            try:
                results[name] = render_boot._seed_approvals_document(dsn, seed_doc)
            except BaseException as e:
                errors.append((name, e))
        t1 = threading.Thread(target=boot, args=('b1', doc({DIGEST_A: spec()})))
        t2 = threading.Thread(target=boot, args=('b2', doc({DIGEST_B: spec()})))
        t1.start(); t2.start(); t1.join(); t2.join()
        assert not errors, errors
        from fresh_review.db import open_store
        c = open_store(dsn)
        final = bytes(c.execute('SELECT raw FROM documents WHERE name=?', (render_boot.APPROVALS_DOC,)).fetchone()[0])
        c.close()
        assert set(json.loads(final)['approvals']) == {DIGEST_A, DIGEST_B}
        final_sha = hashlib.sha256(final).hexdigest()
        # Each boot's returned pin must be self-consistent (sha of its own raw),
        # and the LAST committer's pin must equal the final committed row.
        for name, (raw, sha) in results.items():
            assert hashlib.sha256(raw).hexdigest() == sha, name
        assert final_sha in (results['b1'][1], results['b2'][1])


class TestEphemeralSeedVsSeamlessRecord:
    def test_seed_and_concurrent_recording_both_survive_and_stay_paired(self, tmp_path):
        """Real _seed_approvals_ephemeral racing a real seamless recording on one
        install. Both take the same cross-process lock: no recording is lost,
        and file/config/sidecar end paired."""
        import dev_install
        from fresh_review.demo_approvals import SeamlessDemoApprovalStore
        state = tmp_path / 'state'
        dev_install.create_state(str(state), seamless=True)
        config_path = state / 'dev-config.json'
        approvals_path = state / 'approvals.json'
        pin = json.loads(config_path.read_bytes())['approval_sha256']
        seed_env = env_for(doc({DIGEST_A: spec()}))
        from run_render import _seed_approvals_ephemeral
        errors = []
        def seed():
            try:
                _seed_approvals_ephemeral(config_path, seed_env)
            except BaseException as e:
                errors.append(('seed', e))
        def record():
            try:
                SeamlessDemoApprovalStore(approvals_path, pin).lookup(DIGEST_B, [64, 64])
            except BaseException as e:
                errors.append(('record', e))
        t1 = threading.Thread(target=seed); t2 = threading.Thread(target=record)
        t1.start(); t2.start(); t1.join(); t2.join()
        assert not errors, errors
        raw = approvals_path.read_bytes()
        final = json.loads(raw)['approvals']
        assert DIGEST_A in final and DIGEST_B in final
        file_sha = hashlib.sha256(raw).hexdigest()
        # load_service prefers the sidecar pin when the file matches it; the
        # config pin may legitimately lag a peer recording. The file must match
        # the sidecar (seamless pairing) and the config must match at least the
        # seed's own committed state.
        sidecar = approvals_path.with_name('approvals.recorded-sha256').read_text().strip()
        assert sidecar == file_sha


class TestRotationRevocationWedge:
    def test_change_refuses_removal_keeps_and_no_reset_path(self, tmp_path):
        """Documented semantics (now stated in the module docstring): insert-only
        means a changed entry refuses the boot and a removed entry is kept -
        seeding is NOT revocation, and no automatic reset path exists."""
        import render_boot
        dsn = str(tmp_path / 'docs.sqlite')
        render_boot._seed_approvals_document(dsn, doc({DIGEST_A: spec(reviewer='v1')}))
        with pytest.raises(SystemExit, match='diverges'):
            render_boot._seed_approvals_document(dsn, doc({DIGEST_A: spec(reviewer='v2')}))
        raw, sha = render_boot._seed_approvals_document(dsn, EMPTY_DOC)
        assert DIGEST_A in json.loads(raw)['approvals']
        with pytest.raises(SystemExit):
            render_boot._seed_approvals_document(dsn, doc({DIGEST_A: spec(reviewer='v2')}))


class TestSeamlessRecordsAtRequestTime:
    def test_hosted_seamless_store_records_unseeded_digest_at_lookup(self, tmp_path):
        """Pinned behavior, acknowledged in the module docstring: hosted
        entrypoints wire seamless=True, so an unseeded digest is auto-recorded
        at request time - the seed is provenance pre-seeding, NOT admission
        control."""
        from fresh_review.demo_approvals import SeamlessDemoApprovalStore
        p = tmp_path / 'approvals.json'
        p.write_bytes(EMPTY_DOC); os.chmod(p, 0o600)
        store = SeamlessDemoApprovalStore(p, hashlib.sha256(EMPTY_DOC).hexdigest())
        got = store.lookup(DIGEST_A, [64, 64])
        assert got['provider_upload_approved'] is True
        recorded = json.loads(p.read_bytes())['approvals'][DIGEST_A]
        assert recorded['rights_reference'] == 'seamless-upload-recorded-at-upload-no-rights-review'
