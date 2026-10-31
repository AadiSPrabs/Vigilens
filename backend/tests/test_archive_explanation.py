import json,hashlib
import pytest
from test_fresh_upload_routes import material,prepare,acknowledge,report
from test_fresh_zones import submit
from test_rule_report_integration import rules
from test_spatial_explanation import setup_explanation,response
from fresh_review.archive_explanation import ArchiveExplanation
from fresh_review.explanation_execution import ExplanationExecutor
from fresh_review.pipeline import digest
from fresh_review.ppe import MAX_COST

def test_archive_explanation_carry_no_fake_job_no_repeat_and_artifact_tamper(material,tmp_path):
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 _,plan,_=setup_explanation(p,raw,job,c,x)
 root=tmp_path/'archive';root.mkdir(mode=0o700)
 source=root/'source.png';source.write_bytes(raw);source.chmod(0o600)
 carry=root/'carry.json';carry.write_text(json.dumps({'aggregate_cap_usd':'5','provider_calls_total':2,'conservative_booked_usd':'.01','blocked_source_digests':[frame.digest]}));carry.chmod(0o600)
 def verify():return {'result':job['result'],'archive_provenance':{'original_fresh_job_restored':False}}
 dispatched=[]
 def transport(body):dispatched.append(body);return response(plan)
 a=ArchiveExplanation(root/'archive.sqlite',verify,source_path=source,source_png_sha256=hashlib.sha256(raw).hexdigest(),carry_path=carry,carry_sha=hashlib.sha256(carry.read_bytes()).hexdigest(),transport=transport)
 grant={'format':'vigilens.exact-explanation-grant.v1','execution_scope':a.execution_scope,'plan_sha256':digest(plan),'maximum_reserved_usd':str(MAX_COST),'authority_reference':'synthetic-test-not-real-authority'}
 path=root/'grant.json';path.write_text(json.dumps(grant));path.chmod(0o600)
 e=ExplanationExecutor(a,approval_path=path,approval_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 identity=e.reserve(plan);assert a.original_source_png(frame.digest)==raw
 assert e.run(identity,plan)['state']=='completed'and len(dispatched)==1
 assert e.run(identity,plan)['provider_calls_this_request']==0 and len(dispatched)==1
 db=a.connect();assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone();db.close()
 e.artifact(identity,'reply.bin').write_bytes(b'changed')
 with pytest.raises(ValueError):e.read(identity)
 assert len(dispatched)==1 and len(calls)==2
