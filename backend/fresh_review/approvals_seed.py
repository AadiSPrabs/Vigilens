"""Operator-pinned approvals seed (E2, hosted).

The hosted entrypoints (run_render.py / render_boot.py) merge an operator-pinned
approvals document into the install approvals state at boot. The document comes
from an environment variable set at provision time by the owner/operator; it is
never served over HTTP. Seeding is entry-level INSERT-only:

- digests absent from the state are added;
- entries already present and identical are kept;
- an entry whose digest exists but whose content differs from the seed refuses
  the boot loudly (operator intervention required) rather than silently
  overwriting an existing approval record;
- an EMPTY seed document degrades to adoption: existing state wins unchanged.

HONEST SEMANTICS - what this seed is NOT:
- NOT revocation. Removing a digest from the env document does NOT remove it
  from existing state; a seeded-and-committed entry stays approved until an
  explicit reset (a reset mechanism must preserve owner review of approval
  history - none is implemented, and none is authorized automatically).
- NOT admission control on hosted entrypoints. run_render/render_boot wire
  seamless=True, so the hosted SeamlessDemoApprovalStore records UNSEEDED
  digests at request (upload) time with provenance
  'seamless-upload-recorded-at-upload-no-rights-review'. The seed pre-approves
  the chosen fixture digests so they carry operator-reviewed provenance
  (freshness/rights refs) instead of the automatic seamless recording; it does
  not gate which digests may be processed. Safety assessment: seamless
  recording never overwrites an existing entry (verified in
  SeamlessDemoApprovalStore._record / _record_pg), so a seeded entry's
  provenance is stable; unseeded uploads are still processed and self-record
  under the seamless demo semantics, exactly as the unseeded install would.
  This is acceptable for the offline synthetic demo (no provider bytes leave
  the machine) and matches the install's existing seamless contract; it would
  be unacceptable presented as admission control, so nothing here claims that.

Integrity note: the env pin is an integrity check on the document bytes, not a
signature or an authority claim. Whoever can set the service's environment
variables already controls the deployment; this module records what was pinned
and refuses divergence, it does not establish that the operator's pin is
owner-authorized.
"""

import base64
import binascii
import hashlib
import json

ENV_DOC = 'VIGILENS_APPROVALS_DOC_JSON'
ENV_SHA = 'VIGILENS_APPROVALS_SHA256'

EMPTY_DOC = b'{"version":1,"approvals":{}}\n'
PROVENANCE_KEYS = {'owner_instruction_reference', 'rights_review_reference', 'reviewed_at', 'reviewer', 'scope'}
SCOPES = ('synthetic_local_qualification', 'private_provider_processing')


def validate_document_shape(raw):
    """Exact document shape, mirroring the store's runtime checks
    (fresh_review/approvals.py lookup) so a malformed document fails loudly at
    BOOT instead of at first request. Returns the parsed document."""
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise SystemExit('approvals document is not valid JSON; refusing to boot: %s' % e)
    if not isinstance(doc, dict) or set(doc) != {'version', 'approvals'} or doc['version'] != 1 \
            or not isinstance(doc['approvals'], dict):
        raise SystemExit('approvals document must be exactly {version: 1, approvals: {...}}; refusing to boot')
    for key, spec in doc['approvals'].items():
        if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            raise SystemExit('approvals document has a non-digest entry key; refusing to boot')
        if not isinstance(spec, dict) or spec.get('provider_upload_approved') is not True \
                or not isinstance(spec.get('size'), list) or len(spec['size']) != 2 \
                or not all(isinstance(v, int) and v > 0 for v in spec['size']) \
                or not spec.get('rights_reference'):
            raise SystemExit('approvals document entry is not in the reviewed-approval shape; refusing to boot')
        prov = spec.get('provenance')
        if not isinstance(prov, dict) or set(prov) != PROVENANCE_KEYS \
                or any(not isinstance(v, str) or not v.strip() for v in prov.values()) \
                or prov['scope'] not in SCOPES:
            raise SystemExit('approvals document entry lacks exact recorded provenance; refusing to boot')
    return doc


def env_pinned_document(env):
    """The decoded, pin-verified, shape-validated seed document, or None when
    the operator provisioned nothing. Any partial or mismatched provisioning
    refuses the boot."""
    b64 = env.get(ENV_DOC, '').strip()
    pin = env.get(ENV_SHA, '').strip().lower()
    if not b64 and not pin:
        return None
    if not b64 or not pin:
        raise SystemExit('%s and %s must be set together; refusing to boot' % (ENV_DOC, ENV_SHA))
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise SystemExit('%s is not valid base64; refusing to boot' % ENV_DOC)
    if hashlib.sha256(raw).hexdigest() != pin:
        raise SystemExit('%s does not match %s; refusing to boot' % (ENV_DOC, ENV_SHA))
    validate_document_shape(raw)
    return raw


def merge_insert_only(existing_raw, seed_raw):
    """Merge the seed document into the existing (durable or install) document.
    INSERT-only: absent digests are added, identical entries kept, a differing
    existing entry for the same digest refuses the boot. Returns
    (merged_raw, merged_sha256, inserted_count)."""
    existing = validate_document_shape(existing_raw)
    seed = validate_document_shape(seed_raw)
    merged = dict(existing['approvals'])
    inserted = 0
    for key, spec in seed['approvals'].items():
        if key in merged:
            if merged[key] != spec:
                raise SystemExit('approvals boot seed diverges from an existing entry; refusing to boot '
                                 '(divergence is an operator event, not a silent merge)')
        else:
            merged[key] = spec
            inserted += 1
    raw = (json.dumps({'version': 1, 'approvals': merged}, sort_keys=True) + '\n').encode()
    import sys
    print('note: approvals boot seed: %d entries present, %d inserted by seed' % (len(merged), inserted), file=sys.stderr)
    return raw, hashlib.sha256(raw).hexdigest(), inserted
