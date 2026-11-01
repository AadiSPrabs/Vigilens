"""Generated12person/twozone TestClient flow only. No real model/network dispatch."""
import sys,tempfile,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from pytest import MonkeyPatch
from fastapi.testclient import TestClient
from test_wide_scene import run_twelve_person_multizone_private_HTTP_report

def run(destination):
 destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
 token='generated-wide-smoke-private-token-123456789012345'
 original=TestClient.__init__
 def init(self,*a,**k):
  k['headers']={**k.get('headers',{}),'X-Vigilens-Local-Access':token};original(self,*a,**k)
 with tempfile.TemporaryDirectory()as d,MonkeyPatch.context()as patch:
  patch.setenv('VIGILENS_LOCAL_ACCESS_TOKEN',token);patch.setattr(TestClient,'__init__',init)
  out=run_twelve_person_multizone_private_HTTP_report(Path(d),patch)
  (destination/'wide-report.pdf').write_bytes(out[7]);(destination/'wide-report.json').write_text(json.dumps(out[6],indent=2))
  proof={'input':'generated1000x600pixels','SAM_masks':'synthetic_injected12persons','PPE':'synthetic2selectedresponses','external_calls':0,'detected':12,'assessed':2,'tiny_ambiguous_unassessed':True,'multizone_boundary_overlap_missingcontact':True,'HTTP':'TestClient_not_socket_or_frontend','private_PDF':200,'real_accuracy_verified':False,'full10plusPPEcoverage':False}
  (destination/'proof.json').write_text(json.dumps(proof,indent=2));print(json.dumps(proof,indent=2))
if __name__=='__main__':run(sys.argv[1])
