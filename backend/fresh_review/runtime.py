"""Explicit private live startup config. No secrets or owner approval created here."""
import hashlib,json
from pathlib import Path
from .pipeline import FreshPipeline
from .approvals import ApprovalStore
from .transport import MetaTransport

def from_config(path):
    path=Path(path);raw=FreshPipeline.private_bytes(path);config=json.loads(raw)
    keys={'version','journal','carry_path','carry_sha256','approval_path','approval_sha256','key_file','access_token_file','execution_scope'}
    if set(config)!=keys or config['version']!=1 or config['execution_scope']!='private_provider_processing':raise ValueError('Exact private runtime configuration required')
    def file(key):
        p=Path(config[key])
        if not p.is_absolute():raise ValueError('Private configuration paths must be absolute')
        return p
    journal=file('journal')
    if not journal.parent.is_dir()or journal.parent.stat().st_mode&0o077:raise ValueError('Private existing data directory required')
    token=FreshPipeline.private_bytes(file('access_token_file')).decode().strip()
    if not 32<=len(token)<=256 or any(ord(c)<33 or ord(c)>126 for c in token):raise ValueError('Strong private access token required')
    service=FreshPipeline(journal,approval_store=ApprovalStore(file('approval_path'),config['approval_sha256']),carry_path=file('carry_path'),carry_sha=config['carry_sha256'],transport=MetaTransport(file('key_file')))
    service.carry() #No journal creation/dispatch during startup validation.
    approval=FreshPipeline.private_bytes(file('approval_path'))
    if hashlib.sha256(approval).hexdigest()!=config['approval_sha256']:raise ValueError('Approval store changed before startup')
    doc=json.loads(approval)
    if set(doc)!={'version','approvals'}or doc['version']!=1 or not isinstance(doc['approvals'],dict):raise ValueError('Exact approval document required')
    FreshPipeline.private_bytes(file('key_file'))
    from app import create_app
    return create_app(fresh_service=service,fresh_token=token)
