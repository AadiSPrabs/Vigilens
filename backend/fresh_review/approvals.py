"""Private server-side source approval evidence. Integrity pin is local, not a signature.
No owner authority is inferred from this file. Populate only after source evidence review.
Default contains no approvals. Tests use explicitly synthetic scope, never live authority.
"""
import hashlib,json
from pathlib import Path
DEFAULT_PATH=Path(__file__).with_name('fresh-source-approvals.json')
DEFAULT_SHA=hashlib.sha256(b'{"version":1,"approvals":{}}\n').hexdigest()
class ApprovalStore:
 def __init__(self,path=DEFAULT_PATH,sha=DEFAULT_SHA):self.path=Path(path);self.sha=sha
 def lookup(self,source,size):
  p=self.path
  if not p.is_file()or p.is_symlink()or p.stat().st_mode&0o022:raise ValueError('Server-controlled approval store required')
  raw=p.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=self.sha:raise ValueError('Approval store integrity pin changed')
  doc=json.loads(raw)
  if set(doc)!={'version','approvals'}or doc['version']!=1:raise ValueError('Approval store version required')
  spec=doc['approvals'].get(source)
  if not isinstance(spec,dict)or spec.get('size')!=size or spec.get('provider_upload_approved')is not True or not spec.get('rights_reference'):raise ValueError('Exact reviewed source approval required')
  provenance=spec.get('provenance')
  if not isinstance(provenance,dict)or set(provenance)!={'owner_instruction_reference','rights_review_reference','reviewed_at','reviewer','scope'}or any(not isinstance(v,str)or not v.strip()for v in provenance.values()):raise ValueError('Recorded approval provenance required')
  if provenance['scope']not in ('synthetic_local_qualification','private_provider_processing'):raise ValueError('Exact processing scope required')
  return spec
