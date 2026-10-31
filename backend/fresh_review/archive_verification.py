"""Operator/test harness for authentic retained evidence, never a paid-job restore.
A trusted local verifier re-reads original artifacts on every access. No HTTP
intake of records, no inference transport, and no jobs table is created.
"""
import copy,hashlib,sqlite3,concurrent.futures
from pathlib import Path
from adapters import LiveTransportDisabled
from .pipeline import FreshPipeline,digest
from core import decode_image

class ArchiveVerification:
    archive_verification_only=True
    def __init__(self,path,verifier):
        self.path=Path(path);self.verifier=verifier
    def connect(self):
        c=sqlite3.connect(self.path);self.path.chmod(0o600);return c
    def read(self,source):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1)as pool:record=pool.submit(self.verifier).result()
        if set(record)!={'result','archive_provenance'}or record['archive_provenance'].get('original_fresh_job_restored')is not False:raise ValueError('Explicit verified archive provenance required')
        if record['result']['image']['pixel_digest']!=source:return None
        return {'state':'archived_verified','result':copy.deepcopy(record['result']),'archive_provenance':copy.deepcopy(record['archive_provenance']),'provider_calls_this_request':0,'evidence_export_allowed':False}
    async def run(self,*a,**k):raise LiveTransportDisabled('Archived evidence verification cannot dispatch')
    private_bytes=staticmethod(FreshPipeline.private_bytes)
    def register_derivative(self,png,source):
        if self.read(source)is None:raise ValueError('Unknown archive source')
        f=decode_image(png,'image/png');c=self.connect()
        try:c.execute('CREATE TABLE IF NOT EXISTS archive_derivatives(pixel_digest TEXT PRIMARY KEY,source TEXT)');c.execute('INSERT OR IGNORE INTO archive_derivatives VALUES(?,?)',(f.digest,source));c.commit()
        finally:c.close()
