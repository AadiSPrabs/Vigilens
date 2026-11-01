"""Explicit operator harness for one archived-result commentary, not fresh ingestion.
Accounting carry must include all prior jobs/calls. No restored jobs table. Only an
exact explanation grant can dispatch through ExplanationExecutor; run stays disabled.
"""
import hashlib
from pathlib import Path
from .archive_verification import ArchiveVerification
from .pipeline import FreshPipeline
from core import decode_image

class ArchiveExplanation(ArchiveVerification):
 execution_scope='private_provider_processing'
 def __init__(self,path,verifier,*,source_path,source_png_sha256,carry_path,carry_sha,transport=None):
  super().__init__(path,verifier)
  self.source_path=Path(source_path);self.source_sha=source_png_sha256
  self.carry_path=Path(carry_path);self.carry_sha=carry_sha
  from .pipeline import disabled_transport
  self.transport=transport or disabled_transport
 def carry(self):return FreshPipeline.carry(self)
 save_private=staticmethod(FreshPipeline.save_private)
 def original_source_png(self,source):
  raw=self.private_bytes(self.source_path)
  if hashlib.sha256(raw).hexdigest()!=self.source_sha or decode_image(raw,'image/png').digest!=source or self.read(source)is None:raise ValueError('Exact verified archive original required')
  return raw
