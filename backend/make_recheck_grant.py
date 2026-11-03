"""Format the exact recheck grant for ONE person plan, after the owner approved that plan and ceiling in words.

Input: the JSON returned by POST /fresh-review/{source}/recheck-plan (hashes only; no crop pixels), on stdin.
Output: the grant document on stdout. It is an approval document, not an API secret, but its integrity matters.
This tool only formats and prints: it calls no provider, reserves nothing, writes no file, creates no endpoint
and authorizes nothing by itself. The grant takes effect only when the operator places it in
VIGILENS_RECHECK_GRANT_JSON and the service restarts with VIGILENS_STAGE_EXECUTORS=on.

Usage: python make_recheck_grant.py --authority-reference REF < plan.json
"""
import argparse
import json
import re
import sys

REQUIRED = ('status', 'source_digest', 'result_sha256', 'person_id', 'plan_sha256', 'request_sha256', 'max_reserved_usd', 'execution_scope')


def build(plan_view, authority_reference):
    from fresh_review.recheck_journal import RECHECK_RESERVE
    if not isinstance(plan_view, dict) or any(k not in plan_view for k in REQUIRED) or plan_view['status'] != 'planned_requires_exact_grant':
        raise ValueError('the plan view from /recheck-plan (status planned_requires_exact_grant) is required')
    for k in ('source_digest', 'result_sha256', 'plan_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', str(plan_view[k])):
            raise ValueError('%s must be an exact 64-hex hash' % k)
    reqs = plan_view['request_sha256']
    if not isinstance(reqs, list) or len(reqs) != 2 or any(not re.fullmatch(r'[0-9a-f]{64}', str(r)) for r in reqs):
        raise ValueError('exactly two exact request hashes are required')
    if str(plan_view['max_reserved_usd']) != str(RECHECK_RESERVE):
        raise ValueError('the ceiling must equal the executor recheck reserve')
    if not isinstance(authority_reference, str) or not authority_reference.strip():
        raise ValueError('a reference to the owner approval is required')
    return {'format': 'vigilens.exact-recheck-approval.v1', 'execution_scope': plan_view['execution_scope'], 'source_digest': plan_view['source_digest'],
            'result_sha256': plan_view['result_sha256'], 'person_id': plan_view['person_id'], 'plan_sha256': plan_view['plan_sha256'],
            'authority_reference': authority_reference.strip(), 'request_sha256': list(reqs), 'max_reserved_usd': str(plan_view['max_reserved_usd'])}


def main(argv=None, stdin=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--authority-reference', required=True)
    a = ap.parse_args(argv)
    try:
        grant = build(json.loads((stdin or sys.stdin).read()), a.authority_reference)
    except ValueError as e:
        sys.stderr.write('refused: %s\n' % e)
        return 2
    sys.stdout.write(json.dumps(grant, sort_keys=True) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
