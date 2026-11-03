"""E2 hosted approvals boot seeding: pinned env document, exact shape
validation, insert-only merge with divergence refusal, ephemeral file-state
wiring, clip host-binary gate, and the durable PG path (env-gated). Synthetic
fixtures only; no provider calls; request-time behavior unchanged."""
import base64
import hashlib
import json

import pytest

from fresh_review.approvals_seed import (EMPTY_DOC, ENV_DOC, ENV_SHA, env_pinned_document,
                                         merge_insert_only, validate_document_shape)

DIGEST_A = 'a' * 64
DIGEST_B = 'b' * 64


def spec(scope='synthetic_local_qualification', size=(64, 64)):
    return {'size': list(size), 'rights_reference': 'synthetic-test-fixture',
            'provider_upload_approved': True,
            'provenance': {'owner_instruction_reference': 'synthetic-owner-ref',
                           'rights_review_reference': 'synthetic-rights-ref',
                           'reviewed_at': '2026-11-02T00:00:00+00:00',
                           'reviewer': 'synthetic test', 'scope': scope}}


def doc(entries):
    return (json.dumps({'version': 1, 'approvals': entries}, sort_keys=True) + '\n').encode()


def env_for(raw):
    return {ENV_DOC: base64.b64encode(raw).decode(), ENV_SHA: hashlib.sha256(raw).hexdigest()}


class TestEnvPinnedDocument:
    def test_unset_is_none(self):
        assert env_pinned_document({}) is None

    def test_partial_config_refuses(self):
        with pytest.raises(SystemExit, match='set together'):
            env_pinned_document({ENV_DOC: 'e30='})
        with pytest.raises(SystemExit, match='set together'):
            env_pinned_document({ENV_SHA: 'x'})

    def test_bad_base64_refuses(self):
        with pytest.raises(SystemExit, match='base64'):
            env_pinned_document({ENV_DOC: '!!!', ENV_SHA: 'x'})

    def test_sha_mismatch_refuses(self):
        with pytest.raises(SystemExit, match='does not match'):
            env_pinned_document({ENV_DOC: base64.b64encode(EMPTY_DOC).decode(), ENV_SHA: '0' * 64})

    def test_valid_roundtrip(self):
        raw = doc({DIGEST_A: spec()})
        assert env_pinned_document(env_for(raw)) == raw


class TestShapeValidation:
    @pytest.mark.parametrize('bad', [
        b'not json',
        b'{"version":2,"approvals":{}}',
        b'{"version":1,"approvals":{},"extra":1}',
        json.dumps({'version': 1, 'approvals': {'not-a-digest': spec()}}).encode(),
        json.dumps({'version': 1, 'approvals': {DIGEST_A: {'size': [64, 64]}}}).encode(),
        json.dumps({'version': 1, 'approvals': {DIGEST_A: {**spec(), 'provider_upload_approved': False}}}).encode(),
        json.dumps({'version': 1, 'approvals': {DIGEST_A: spec(scope='live_unscoped')}}).encode(),
    ])
    def test_malformed_refuses_at_boot(self, bad):
        with pytest.raises(SystemExit):
            validate_document_shape(bad)

    def test_valid_passes(self):
        assert validate_document_shape(doc({DIGEST_A: spec()}))['approvals'][DIGEST_A]['provider_upload_approved'] is True


class TestMergeInsertOnly:
    def test_insert_and_idempotence(self):
        seed = doc({DIGEST_A: spec()})
        raw, sha, inserted = merge_insert_only(EMPTY_DOC, seed)
        assert inserted == 1 and sha == hashlib.sha256(raw).hexdigest()
        again, sha2, inserted2 = merge_insert_only(raw, seed)
        assert inserted2 == 0 and sha2 == sha  # identical re-seed: no drift

    def test_existing_entries_kept(self):
        existing = doc({DIGEST_A: spec()})
        raw, _sha, inserted = merge_insert_only(existing, doc({DIGEST_B: spec()}))
        merged = json.loads(raw)['approvals']
        assert set(merged) == {DIGEST_A, DIGEST_B} and inserted == 1

    def test_divergence_refuses_boot(self):
        existing = doc({DIGEST_A: spec(size=(64, 64))})
        seed = doc({DIGEST_A: spec(size=(32, 32))})
        with pytest.raises(SystemExit, match='diverges'):
            merge_insert_only(existing, seed)


class TestEphemeralWiring:
    def test_seed_repins_config_and_merges(self, tmp_path, monkeypatch):
        import dev_install
        from run_render import _seed_approvals_ephemeral
        state = tmp_path / 'state'
        dev_install.create_state(str(state), seamless=True)
        config_path = state / 'dev-config.json'
        seed = doc({DIGEST_A: spec()})
        for k, v in env_for(seed).items():
            monkeypatch.setenv(k, v)
        _seed_approvals_ephemeral(config_path, __import__('os').environ)
        config = json.loads(config_path.read_bytes())
        raw = (state / 'approvals.json').read_bytes()
        assert json.loads(raw)['approvals'][DIGEST_A]['provider_upload_approved'] is True
        assert config['approval_sha256'] == hashlib.sha256(raw).hexdigest()
        # idempotent re-seed: same sha, no drift
        _seed_approvals_ephemeral(config_path, __import__('os').environ)
        assert json.loads(config_path.read_bytes())['approval_sha256'] == config['approval_sha256']
        # divergence refuses
        for k, v in env_for(doc({DIGEST_A: spec(size=(32, 32))})).items():
            monkeypatch.setenv(k, v)
        with pytest.raises(SystemExit, match='diverges'):
            _seed_approvals_ephemeral(config_path, __import__('os').environ)

    def test_unset_env_leaves_install_untouched(self, tmp_path):
        import dev_install
        from run_render import _seed_approvals_ephemeral
        state = tmp_path / 'state'
        dev_install.create_state(str(state), seamless=True)
        before = (state / 'dev-config.json').read_bytes()
        _seed_approvals_ephemeral(state / 'dev-config.json', {})
        assert (state / 'dev-config.json').read_bytes() == before


class TestExportApprovals:
    def test_export_roundtrips_through_env_pin(self, tmp_path, capsys):
        import dev_install
        state = tmp_path / 'state'
        dev_install.create_state(str(state), seamless=True)
        import sys
        argv = sys.argv
        sys.argv = ['dev_install.py', 'export-approvals', '--state-dir', str(state)]
        try:
            dev_install.main()
        finally:
            sys.argv = argv
        out = capsys.readouterr().out.strip().splitlines()
        pair = dict(line.split('=', 1) for line in out)
        assert env_pinned_document(pair) == (state / 'approvals.json').read_bytes()


class TestClipBinaryGate:
    def _limits_env(self, monkeypatch):
        monkeypatch.setenv('VIGILENS_CLIP_LIMITS_JSON', json.dumps(
            {'max_bytes': 20_000_000, 'max_seconds': 30, 'max_frames': 4,
             'max_side': 1920, 'max_pixels': 2_073_600, 'subprocess_seconds': 20}))

    def test_missing_binary_refuses_boot(self, monkeypatch):
        import shutil
        from run_render import _wire_clip_limits
        self._limits_env(monkeypatch)
        monkeypatch.setattr(shutil, 'which', lambda b: None if b == 'ffmpeg' else '/usr/bin/' + b)
        with pytest.raises(SystemExit, match='ffmpeg'):
            _wire_clip_limits(object())

    def test_present_binaries_wire_limits(self, monkeypatch):
        import shutil
        from run_render import _wire_clip_limits
        self._limits_env(monkeypatch)
        monkeypatch.setattr(shutil, 'which', lambda b: '/usr/bin/' + b)

        class S:
            pass
        s = S()
        _wire_clip_limits(s)
        assert s.trusted_clip_limits.max_frames == 4

    def test_unset_limits_skips_gate(self, monkeypatch):
        import shutil
        from run_render import _wire_clip_limits
        monkeypatch.delenv('VIGILENS_CLIP_LIMITS_JSON', raising=False)
        monkeypatch.setattr(shutil, 'which', lambda b: None)  # would fail if the gate ran
        _wire_clip_limits(object())  # no raise


@pytest.fixture()
def pg_uri(tmp_path):
    pgserver = pytest.importorskip('pgserver')
    srv = pgserver.get_server(str(tmp_path / 'pg'))
    yield srv.get_uri()
    srv.cleanup()


class TestDurableSeeding:
    def test_pg_seed_lookup_and_divergence(self, pg_uri, monkeypatch):
        from render_boot import boot_pg_service
        from fresh_review.synthetic_transport import SyntheticTransport
        seed = doc({DIGEST_A: spec()})
        for k, v in env_for(seed).items():
            monkeypatch.setenv(k, v)
        kw = dict(cap='5', scope='synthetic_local_qualification', seamless=False,
                  transport=SyntheticTransport())
        s1 = boot_pg_service(pg_uri, **kw)
        assert s1.approval_store.lookup(DIGEST_A, [64, 64])['provider_upload_approved'] is True
        s2 = boot_pg_service(pg_uri, **kw)  # redeploy with same pin: idempotent
        assert s2.approval_store.lookup(DIGEST_A, [64, 64])
        # unseeded digest still fail-closes at request time; nothing recorded
        with pytest.raises(ValueError):
            s2.approval_store.lookup(DIGEST_B, [64, 64])
        # changed document for the SAME digest refuses the boot
        for k, v in env_for(doc({DIGEST_A: spec(size=(32, 32))})).items():
            monkeypatch.setenv(k, v)
        with pytest.raises(SystemExit, match='diverges'):
            boot_pg_service(pg_uri, **kw)
