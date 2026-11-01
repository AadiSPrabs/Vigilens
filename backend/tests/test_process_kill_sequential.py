"""Real SIGKILL of a forked child during the sequential wide pipeline, then restart in a fresh process view.
Synthetic fake transport only. Bodies sent by the dead child are logged to a file so the restart can be checked
against the full cross-process call history (no stage body may be sent twice)."""
import os,signal,json,asyncio
import pytest
from test_wide_sequential import seq,run,unique

def kill_self():os.kill(os.getpid(),signal.SIGKILL)

def child_dies(fn):
 pid=os.fork()
 if pid==0:
  try:fn()
  finally:os._exit(3)
 _,st=os.waitpid(pid,0)
 assert os.WIFSIGNALED(st) and os.WTERMSIG(st)==signal.SIGKILL,'child not killed at intended point'

@pytest.mark.parametrize('kill_at',[1,2,4,8,13])
@pytest.mark.parametrize('when',['inside_transport_before_reply','after_reply_before_next_stage'])
def test_sequential_sigkill_restart_no_repeated_body(tmp_path,monkeypatch,kill_at,when):
 p,raw,f,calls=seq(tmp_path,monkeypatch);inner=p.transport;log=tmp_path/'child-bodies.jsonl'
 def logged(body):
  with open(log,'a') as h:h.write(json.dumps(body,sort_keys=True)+'\n');h.flush();os.fsync(h.fileno())
  n=sum(1 for _ in open(log))
  if when=='inside_transport_before_reply' and n==kill_at:kill_self()
  out=inner(body)
  if when=='after_reply_before_next_stage' and n==kill_at:kill_self()
  return out
 p.transport=logged
 child_dies(lambda:run(p,raw))
 sent=[json.loads(l) for l in open(log)];assert len(sent)==kill_at
 p.transport=inner;calls.clear()
 s=p.read(f.digest);assert s['state'] in('running_uncertain','completed') or s.get('resumable_without_repeat')
 out=run(p,raw)
 allb=[json.dumps(b,sort_keys=True) for b in sent]+[json.dumps(b,sort_keys=True) for b in calls]
 assert len(allb)==len(set(allb)),'a request body was sent twice across the kill'
 assert len(allb)<=13
 again=run(p,raw)
 assert again['provider_calls_this_request']==0 and len(calls)==len(allb)-len(sent)
