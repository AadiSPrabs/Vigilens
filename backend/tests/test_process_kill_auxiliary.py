"""Real process death (SIGKILL of a forked child) around dispatch and settlement of the auxiliary executors.
Synthetic fake transport only, no provider. Each case: child dies at a named point, a fresh executor in the parent
(the restart) must not re-dispatch, must keep the attempt uncertain and the reservation held."""
import asyncio,os,signal
import pytest
from test_fresh_upload_routes import material,prepare,acknowledge
from test_recheck_execution import executor as recheck_executor
from test_ppe_segmentation import helper as mask_helper
from test_spatial_explanation import setup_explanation,response
from test_fresh_zones import submit
from test_rule_report_integration import rules
from fresh_review.recheck_journal import RECHECK_RESERVE,reservation_total
from fresh_review.ppe_segmentation import total as mask_total,BATCH_RESERVE
from fresh_review.explanation_execution import total as explanation_total

def kill_self():os.kill(os.getpid(),signal.SIGKILL)

def in_child(fn):
 pid=os.fork()
 if pid==0:
  try:fn()
  finally:os._exit(3)  # reaching here means the kill point was never hit
 _,status=os.waitpid(pid,0)
 assert os.WIFSIGNALED(status) and os.WTERMSIG(status)==signal.SIGKILL,'child was not killed at the intended point'

def hold(p,fn):
 d=p.connect()
 try:return fn(d)
 finally:d.close()

@pytest.mark.parametrize('point',['first_transport','second_transport','after_transport_before_settle'])
def test_recheck_sigkill_then_restart_never_redispatches(material,monkeypatch,point):
 import fresh_review.recheck_execution as module
 p,raw,frame,calls,c,job=material;e,a=recheck_executor(p,frame,monkeypatch)
 real=module.parse_sam_image_text;live=p.transport;n=[0]
 def dying(body):
  n[0]+=1
  if (point=='first_transport' and n[0]==1)or(point=='second_transport' and n[0]==2):kill_self()
  return live(body)
 if point=='after_transport_before_settle':
  async def parse(*args,**kwargs):kill_self()
  monkeypatch.setattr(module,'parse_sam_image_text',parse)
 p.transport=dying
 in_child(lambda:asyncio.run(e.run(a['attempt_id'])))
 p.transport=live;monkeypatch.setattr(module,'parse_sam_image_text',real);before=len(calls)
 fresh=type(e)(p,approval_path=e.approval_path,approval_sha256=e.approval_sha256)
 assert fresh.read(a['attempt_id'])['state']=='attempted_uncertain'
 assert hold(p,reservation_total)==RECHECK_RESERVE
 again=asyncio.run(fresh.run(a['attempt_id']))
 assert again['state']=='attempted_uncertain' and again['provider_calls_this_request']==0 and len(calls)==before
 assert hold(p,reservation_total)==RECHECK_RESERVE

@pytest.mark.parametrize('point',['transport','after_transport_before_settle'])
def test_mask_batch_sigkill_then_restart_never_redispatches(material,monkeypatch,point):
 import fresh_review.ppe_segmentation as module
 p,raw,frame,calls,c,job=material;h,identity=mask_helper(p,frame,monkeypatch)
 live=p.transport;real=module.parse_sam_image_text
 if point=='transport':
  def dying(body):kill_self()
  p.transport=dying
 else:
  async def parse(*args,**kwargs):kill_self()
  monkeypatch.setattr(module,'parse_sam_image_text',parse)
 in_child(lambda:asyncio.run(h.run(identity)))
 p.transport=live;monkeypatch.setattr(module,'parse_sam_image_text',real);before=len(calls)
 fresh=type(h)(p,approval_path=h.approval_path,approval_sha256=h.approval_sha)
 assert fresh.read(identity)['state']=='attempted_uncertain'
 held=hold(p,mask_total);assert held>0
 again=asyncio.run(fresh.run(identity))
 assert again['state']=='attempted_uncertain' and len(calls)==before and hold(p,mask_total)==held

@pytest.mark.parametrize('point',['transport','after_transport_before_settle'])
def test_explanation_sigkill_then_restart_never_redispatches(material,monkeypatch,point):
 import fresh_review.explanation_execution as module
 p,raw,frame,calls,c,job=material;x=prepare(c,raw,frame);acknowledge(c,x);submit(c,frame,job);rules(c,frame,job)
 e,plan,identity=setup_explanation(p,raw,job,c,x)
 live=lambda body:(calls.append(body),response(plan))[1];p.transport=live;real=module.parse_spatial_reply
 if point=='transport':
  def dying(body):kill_self()
  p.transport=dying
 else:
  def parse(*args,**kwargs):kill_self()
  monkeypatch.setattr(module,'parse_spatial_reply',parse)
 in_child(lambda:e.run(identity,plan))
 p.transport=live;monkeypatch.setattr(module,'parse_spatial_reply',real);before=len(calls)
 fresh=type(e)(p,approval_path=e.path,approval_sha256=e.sha)
 assert fresh.read(identity)['state']=='attempted_uncertain'
 held=hold(p,explanation_total);assert held>0
 again=fresh.run(identity,plan)
 assert again['state']=='attempted_uncertain' and again['provider_calls_this_request']==0 and len(calls)==before
 assert hold(p,explanation_total)==held
