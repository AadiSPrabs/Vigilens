"""Explicit private live startup config. No secrets or owner approval created here."""
import hashlib,json
from pathlib import Path
from .pipeline import FreshPipeline
from .approvals import ApprovalStore
from .transport import MetaTransport

def from_config(path):
    path=Path(path);raw=FreshPipeline.private_bytes(path);config=json.loads(raw)
    keys={'version','journal','carry_path','carry_sha256','approval_path','approval_sha256','key_file','access_token_file','execution_scope'}
    optional={'recheck_grant_path','recheck_grant_sha256','review_loop_attempts','explanation_grant_path','explanation_grant_sha256','trusted_clip_limits','operator_private_download_enabled','wide_scene_limits','chain_manifest_path','chain_manifest_sha256','chain_proof_dir'}
    if set(config)-optional!=keys or config['version']!=1 or config['execution_scope']!='private_provider_processing':raise ValueError('Exact private runtime configuration required')
    def file(key):
        p=Path(config[key])
        if not p.is_absolute():raise ValueError('Private configuration paths must be absolute')
        return p
    journal=file('journal')
    if not journal.parent.is_dir()or journal.parent.stat().st_mode&0o077:raise ValueError('Private existing data directory required')
    token=FreshPipeline.private_bytes(file('access_token_file')).decode().strip()
    if not 32<=len(token)<=256 or any(ord(c)<33 or ord(c)>126 for c in token):raise ValueError('Strong private access token required')
    pipeline_class=FreshPipeline;extra={}
    if 'wide_scene_limits'in config:
        from .wide_scene import WideScenePipeline,WideLimits
        raw_limits=dict(config['wide_scene_limits']);sequential=raw_limits.pop('sequential',False)
        if type(sequential)is not bool:raise ValueError('Explicit sequential boolean required')
        if sequential:
            from .wide_sequential import SequentialWidePipeline,SequentialLimits
            limits=SequentialLimits(**raw_limits);pipeline_class=SequentialWidePipeline
        else:limits=WideLimits(**raw_limits);pipeline_class=WideScenePipeline
        limits.validate();extra={'wide_limits':limits}
    if {'chain_manifest_path','chain_manifest_sha256','chain_proof_dir'}&set(config):
        if not {'chain_manifest_path','chain_manifest_sha256','chain_proof_dir'}<=set(config)or pipeline_class.__name__!='SequentialWidePipeline':raise ValueError('Pinned chain manifest, proof directory and sequential pipeline required together')
        from .carry_chain import load_manifest
        extra['chain_manifest']=load_manifest(file('chain_manifest_path'),config['chain_manifest_sha256']);extra['chain_proof_dir']=str(file('chain_proof_dir'))
    service=pipeline_class(journal,**extra,approval_store=ApprovalStore(file('approval_path'),config['approval_sha256']),carry_path=file('carry_path'),carry_sha=config['carry_sha256'],transport=MetaTransport(file('key_file')))
    service.carry() #No journal creation/dispatch during startup validation.
    approval=FreshPipeline.private_bytes(file('approval_path'))
    if hashlib.sha256(approval).hexdigest()!=config['approval_sha256']:raise ValueError('Approval store changed before startup')
    doc=json.loads(approval)
    if set(doc)!={'version','approvals'}or doc['version']!=1 or not isinstance(doc['approvals'],dict):raise ValueError('Exact approval document required')
    FreshPipeline.private_bytes(file('key_file'))
    if 'operator_private_download_enabled'in config:
        if type(config['operator_private_download_enabled'])is not bool:raise ValueError('Explicit private-download boolean required')
        service.operator_private_download_enabled=config['operator_private_download_enabled']
    if 'trusted_clip_limits'in config:
        from .clips import ClipLimits
        service.trusted_clip_limits=ClipLimits(**config['trusted_clip_limits']);service.trusted_clip_limits.validate()
    if {'recheck_grant_path','recheck_grant_sha256'}&set(config):
        if not {'recheck_grant_path','recheck_grant_sha256'}<=set(config):raise ValueError('Pinned recheck grant pair required')
        from .recheck_execution import RecheckExecutor
        service.recheck_executor=RecheckExecutor(service,approval_path=file('recheck_grant_path'),approval_sha256=config['recheck_grant_sha256'])
        if hashlib.sha256(FreshPipeline.private_bytes(file('recheck_grant_path'))).hexdigest()!=config['recheck_grant_sha256']:raise ValueError('Recheck grant pin changed')
    if 'review_loop_attempts'in config:
        if not hasattr(service,'recheck_executor')or not isinstance(config['review_loop_attempts'],dict):raise ValueError('Explicit configured recheck executor required')
        for source,ids in config['review_loop_attempts'].items():
            if not isinstance(source,str)or len(source)!=64 or not isinstance(ids,list)or not 1<=len(ids)<=2 or any(not isinstance(i,str)or len(i)!=64 for i in ids):raise ValueError('Bounded existing attempt IDs required')
            for identity in ids:
                attempt=service.recheck_executor.read(identity)
                if attempt['plan']['source_digest']!=source:raise ValueError('Configured attempt source mismatch')
                service.recheck_executor.approval(attempt)
        service.review_loop_attempts=config['review_loop_attempts']
    if {'explanation_grant_path','explanation_grant_sha256'}&set(config):
        if not {'explanation_grant_path','explanation_grant_sha256'}<=set(config):raise ValueError('Pinned explanation grant pair required')
        from .explanation_execution import ExplanationExecutor
        service.explanation_executor=ExplanationExecutor(service,approval_path=file('explanation_grant_path'),approval_sha256=config['explanation_grant_sha256'])
        if hashlib.sha256(FreshPipeline.private_bytes(file('explanation_grant_path'))).hexdigest()!=config['explanation_grant_sha256']:raise ValueError('Explanation grant pin changed')
    from app import create_app
    return create_app(fresh_service=service,fresh_token=token)
