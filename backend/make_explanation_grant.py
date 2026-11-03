"""Format the exact explanation grant document for ONE plan, after the owner approved that plan in words.

This tool only formats a document and PRINTS it to stdout (so it lands wherever stdout goes; the grant is an
approval document, not an API secret, but treat its integrity as important). It never calls a provider,
reserves anything or writes files. It authorizes nothing by itself: the grant is inert until the operator places
the JSON in VIGILENS_EXPLANATION_GRANT_JSON and the service restarts with VIGILENS_STAGE_EXECUTORS=on.
It covers one plan_sha256 and one cost ceiling.

Usage: python make_explanation_grant.py --plan-sha256 HEX64 --execution-scope SCOPE --authority-reference REF
For a recheck grant use make_recheck_grant.py with the output of POST /fresh-review/{source}/recheck-plan.
"""
import argparse
import json
import re
import sys


def build(plan_sha256, execution_scope, authority_reference, maximum_reserved_usd=None):
    from fresh_review.ppe import MAX_COST
    if not re.fullmatch(r'[0-9a-f]{64}', plan_sha256 or ''):
        raise ValueError('plan_sha256 must be the exact 64-hex plan hash shown in the private report')
    if not execution_scope or not authority_reference:
        raise ValueError('execution scope and a reference to the owner approval are required')
    cap = str(MAX_COST) if maximum_reserved_usd is None else str(maximum_reserved_usd)
    if cap != str(MAX_COST):
        raise ValueError('the ceiling must equal the executor maximum for one explanation')
    return {'format': 'vigilens.exact-explanation-grant.v1', 'execution_scope': execution_scope,
            'plan_sha256': plan_sha256, 'maximum_reserved_usd': cap, 'authority_reference': authority_reference}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--plan-sha256', required=True)
    ap.add_argument('--execution-scope', required=True)
    ap.add_argument('--authority-reference', required=True)
    a = ap.parse_args(argv)
    try:
        sys.stdout.write(json.dumps(build(a.plan_sha256, a.execution_scope, a.authority_reference), sort_keys=True) + '\n')
    except ValueError as e:
        sys.stderr.write('refused: %s\n' % e)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
