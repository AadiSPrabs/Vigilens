"""Configured bounded unknown rechecks, never new grants, sources or silent adoption.
Only pre-reserved exact attempts and operator-selected one-person association may run.
"""
from .pipeline import digest

async def run_review_loop(service,source,*,attempt_ids):
 job=service.read(source)
 if not job or job['state']!='completed':raise ValueError('Exact completed original job required')
 if not isinstance(attempt_ids,list)or len(attempt_ids)>2 or len(set(attempt_ids))!=len(attempt_ids):raise ValueError('Bounded distinct pre-reserved attempts required')
 unknown=[p['id']for p in job['result']['persons']if p.get('ppe_assessed',True)and any(p[k]=='unknown'for k in ('helmet','vest'))]
 executor=getattr(service,'recheck_executor',None)
 if attempt_ids and executor is None:raise ValueError('Exact granted recheck executor required')
 planned=[];seen=set()
 # Preflight every exact attempt before first dispatch, never allocate grants here.
 for aid in attempt_ids:
  attempt=executor.read(aid);plan=attempt['plan']
  if plan['source_digest']!=source or plan['result_sha256']!=digest(job['result'])or plan['person_id']not in unknown or plan['person_id']in seen:raise ValueError('One exact attempt per original unknown person required')
  executor.approval(attempt);seen.add(plan['person_id']);planned.append(attempt)
 results=[]
 for attempt in planned:
  out=await executor.run(attempt['attempt_id'])
  results.append({'person_id':attempt['plan']['person_id'],'attempt_id':out['attempt_id'],'state':out['state'],'candidate':out['result'],'original_overwrite_allowed':False})
  if out['state']!='completed':break
 return {'source_digest':source,'original_result_sha256':digest(job['result']),'status':'human_review_required'if unknown else'no_initial_unknown_recheck_not_needed','original_unknown_person_ids':unknown,'attempts':results,'unattempted_unknown_person_ids':[p for p in unknown if p not in {r['person_id']for r in results}],'automatic_candidate_adoption':False,'automatic_retry':False,'evidence_export_allowed':False,'notice':'Original observations retained. Completed candidates and unresolved/uncertain attempts require human review; no safety clearance.'}
