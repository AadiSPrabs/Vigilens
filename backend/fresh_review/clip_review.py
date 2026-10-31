"""Private sampled-clip manifests, never temporal tracking or release approval."""
import json,hashlib
from .pipeline import digest

class ClipReviewStore:
 def __init__(self,service):self.service=service
 def register(self,summary,owner):
  if summary['status']!='sampled_image_jobs_completed_not_clip_safety_clearance':return None
  frames=[{k:frame[k]for k in ('sample_index','requested_offset_seconds','timestamp_basis','pixel_digest','width','height')}|{'result_sha256':digest(frame['image_job']['result'])}for frame in summary['frames']]
  manifest={'source_clip_sha256':summary['source_clip_sha256'],'duration_seconds':summary['duration_seconds'],'frames':frames}
  identity=digest(manifest);c=self.service.connect()
  try:
   c.execute('CREATE TABLE IF NOT EXISTS clip_review_manifests(id TEXT,owner TEXT,manifest TEXT,PRIMARY KEY(id,owner))')
   who=hashlib.sha256(owner.encode()).hexdigest()
   if c.execute('SELECT count(*) FROM clip_review_manifests').fetchone()[0]>=64 and not c.execute('SELECT 1 FROM clip_review_manifests WHERE id=? AND owner=?',(identity,who)).fetchone():raise ValueError('Private clip manifest capacity reached')
   c.execute('INSERT OR IGNORE INTO clip_review_manifests VALUES(?,?,?)',(identity,who,json.dumps(manifest,sort_keys=True)));c.commit()
  finally:c.close()
  return identity
 def read(self,identity,owner):
  c=self.service.connect()
  try:
   c.execute('CREATE TABLE IF NOT EXISTS clip_review_manifests(id TEXT,owner TEXT,manifest TEXT,PRIMARY KEY(id,owner))')
   row=c.execute('SELECT manifest FROM clip_review_manifests WHERE id=? AND owner=?',(identity,hashlib.sha256(owner.encode()).hexdigest())).fetchone()
  finally:c.close()
  if not row:raise ValueError('Own clip manifest required')
  manifest=json.loads(row[0])
  if digest(manifest)!=identity:raise ValueError('Clip manifest changed')
  for frame in manifest['frames']:
   job=self.service.read(frame['pixel_digest'])
   if not job or job['state']!='completed'or digest(job['result'])!=frame['result_sha256']:raise ValueError('Sample result changed')
  return manifest
