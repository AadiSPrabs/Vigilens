"""D4-followup pre-journal live gate: under LIVE wiring (private_provider_processing
+ real Meta transport) a request on an UNGATED route (upload/clip, which never set
the visitor key and never check VIGILENS_LIVE_DISPATCH) must be refused BEFORE the
seamless approval mint and BEFORE the journal claim/reservation. Refusals are
zero-dispatch, zero-claim, zero-reservation, zero-mint. Adopted from the
independent dispatch-conditions probes; expectations inverted post-fix.
Synthetic wiring is untouched (upload-as-approval demo flow still completes).
Offline: SyntheticTransport and key-less MetaRequestTransport; no network."""
import asyncio, base64, hashlib, io, json, os
import pytest
from PIL import Image

def png_bytes(size=(64, 64), color=(200, 30, 30)):
    b = io.BytesIO(); Image.new('RGB', size, color).save(b, 'PNG'); return b.getvalue()

def make_meta_service(tmp_path):
    import dev_install
    from fresh_review.demo_approvals import SeamlessDemoApprovalStore
    from fresh_review.pipeline import FreshPipeline
    from fresh_review.transport import MetaRequestTransport
    state = tmp_path / 'state'
    dev_install.create_state(str(state), seamless=True)
    config = json.loads((state / 'dev-config.json').read_bytes())
    ap = state / 'approvals.json'
    store = SeamlessDemoApprovalStore(ap, config['approval_sha256'], scope='private_provider_processing')
    service = FreshPipeline(config['journal'], execution_scope='private_provider_processing',
                            approval_store=store, carry_path=state / 'carry.json',
                            carry_sha=config['carry_sha256'], transport=MetaRequestTransport())
    return service, ap, config['journal']

def journal_rows(journal_path):
    # A pre-journal refusal never even creates the jobs table; treat 'no such
    # table' as the empty journal it is.
    import sqlite3
    c = sqlite3.connect(journal_path)
    try:
        return c.execute('SELECT owner,source,state,reserved FROM jobs').fetchall()
    except sqlite3.OperationalError as e:
        if 'no such table' in str(e):
            return []
        raise
    finally:
        c.close()


class TestOffGateRefusalIsZeroState:
    def test_no_claim_no_reservation_no_mint_no_wedge(self, tmp_path, monkeypatch):
        """LIVE_DISPATCH unset (off) and no visitor key in context, exactly as
        the upload/clip routes leave it: the upload refuses pre-journal."""
        from adapters import LiveTransportDisabled
        service, ap, journal = make_meta_service(tmp_path)
        monkeypatch.delenv('VIGILENS_LIVE_DISPATCH', raising=False)
        raw = png_bytes()
        from core import decode_image
        d = decode_image(raw, 'image/png').digest
        with pytest.raises(LiveTransportDisabled):
            asyncio.run(service.run(raw, 'image/png', [], owner='visitor-a'))
        assert journal_rows(journal) == []                      # no claim/reservation/wedge
        assert d not in json.loads(ap.read_bytes())['approvals']  # no live-scope mint
        # No journal-GLOBAL hold was created: a second owner is equally free to
        # be refused on its own merits, not held by the first request.
        with pytest.raises(LiveTransportDisabled):
            asyncio.run(service.run(raw, 'image/png', [], owner='visitor-b'))
        assert journal_rows(journal) == []

    def test_gate_on_without_visitor_key_still_refuses_pre_journal(self, tmp_path, monkeypatch):
        """LIVE_DISPATCH=on alone is not enough for the BYOK transport."""
        from adapters import LiveTransportDisabled
        service, ap, journal = make_meta_service(tmp_path)
        monkeypatch.setenv('VIGILENS_LIVE_DISPATCH', 'on')
        raw = png_bytes()
        from core import decode_image
        d = decode_image(raw, 'image/png').digest
        with pytest.raises(LiveTransportDisabled):
            asyncio.run(service.run(raw, 'image/png', [], owner='visitor-a'))
        assert journal_rows(journal) == []
        assert d not in json.loads(ap.read_bytes())['approvals']

    def test_gate_off_with_visitor_key_still_refuses_pre_journal(self, tmp_path, monkeypatch):
        """A visitor key alone does not open dispatch; the env gate governs."""
        from adapters import LiveTransportDisabled
        from fresh_review.transport import CURRENT_VISITOR_KEY
        service, ap, journal = make_meta_service(tmp_path)
        monkeypatch.delenv('VIGILENS_LIVE_DISPATCH', raising=False)
        tok = CURRENT_VISITOR_KEY.set('visitor-key-a')
        try:
            with pytest.raises(LiveTransportDisabled):
                asyncio.run(service.run(png_bytes(), 'image/png', [], owner='visitor-a'))
        finally:
            CURRENT_VISITOR_KEY.reset(tok)
        assert journal_rows(journal) == []


class TestSyntheticFlowUnchanged:
    def test_default_hosted_synthetic_seamless_completes_without_preseed(self, tmp_path, monkeypatch):
        """The synthetic seamless demo flow is NOT gated: upload IS the recorded
        synthetic approval, then the job completes. No pre-seed required."""
        import dev_install
        monkeypatch.delenv('VIGILENS_LIVE_DISPATCH', raising=False)
        state = tmp_path / 'state'
        dev_install.create_state(str(state), seamless=True)
        service, token, _ = dev_install.load_service(state / 'dev-config.json')
        raw = png_bytes()
        from core import decode_image
        d = decode_image(raw, 'image/png').digest
        assert d not in json.loads((state / 'approvals.json').read_bytes())['approvals']
        job = asyncio.run(service.run(raw, 'image/png', [], owner='visitor-a'))
        assert job['state'] == 'completed'
        recorded = json.loads((state / 'approvals.json').read_bytes())['approvals'][d]
        assert recorded['rights_reference'] == 'seamless-upload-recorded-at-upload-no-rights-review'
        assert recorded['provenance']['scope'] == 'synthetic_local_qualification'
