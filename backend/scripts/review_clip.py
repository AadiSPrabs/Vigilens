#!/usr/bin/env python3
"""python scripts/review_clip.py BUNDLE_DIR [--manual-view] [--check]. See clip_human_review.py."""
import sys,json,tempfile,os,secrets,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from clip_human_review import *
def main():
    args=[a for a in sys.argv[1:]if not a.startswith('--')];B=Path(args[0]);manual='--manual-view'in sys.argv;check='--check'in sys.argv
    from fresh_review.runtime import from_config
    from fresh_review.clip_review import ClipReviewStore
    from fastapi.testclient import TestClient
    work=Path(tempfile.mkdtemp(prefix='vigilens-review-'))
    try:
        rt,token=setup_workdir(B,work);app=from_config(str(rt));pl=app.state.fresh_pipeline
        owner=secrets.token_urlsafe(40);c=TestClient(app,headers={'X-Vigilens-Display-Session':owner,'X-Vigilens-Local-Access':token})
        summary=json.loads((B/'out-clip2.json').read_text());cid=ClipReviewStore(pl).register(summary,owner);manifest=ClipReviewStore(pl).read(cid,owner)
        print('Manifest registered; every saved result hash re-verified:',len(manifest['frames']),'frames. Provider calls: 0.')
        if check:print('CHECK OK (no preview built, no acknowledgment).');return
        out=ROOT/'review-output';io=Console()
        label=io.ask('Type your reviewer label (text only, max 80 chars):')
        load=lambda fr:(B/'frames'/f"n{fr['sample_index']}.png").read_bytes()
        rec=run_review(c,pl,cid,manifest,load,out,io,label=label[:80],manual_view=manual)
        print('Done. Wrote',out,'(private; not a safety or privacy clearance; export false).')
    except ReviewAbort as e:print('STOPPED:',e);sys.exit(2)
    finally:shutil.rmtree(work,ignore_errors=True)
main()
