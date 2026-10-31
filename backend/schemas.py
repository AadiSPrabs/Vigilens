"""Typed local-job response contract, separate from unapproved model reports."""
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,model_validator

class LocalJob(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    job_id:str
    state:Literal['queued','running','completed','failed','needs_review','cancelled']
    created:float
    updated:float
    result:dict[str,Any]|None
    error_code:str|None
    cost_state:Literal['unknown','zero_local_only']
    result_expired:bool
    result_available:bool
    retryable_with_same_key:Literal[False]
    same_key_behavior:Literal['may_start_queued_local_work','retrieve_only_no_new_execution']
    status_reason:str
    cancellation_kind:Literal['before_local_execution']|None
    result_expires_at:None
    dedup_expires_at:None
    retention_policy:Literal['manual_local_cleanup_no_dedup_expiry_configured']
    @model_validator(mode='after')
    def invariants(self):
        if (self.same_key_behavior=='may_start_queued_local_work')!=(self.state=='queued'):raise ValueError('Same-key behavior mismatch')
        if self.result_available!=(self.result is not None and not self.result_expired):raise ValueError('Result availability mismatch')
        if self.result_expired and (self.state!='completed' or self.result is not None):raise ValueError('Expired result requires completed tombstone')
        if self.result is not None and self.state!='completed':raise ValueError('Result requires completed job')
        if (self.cancellation_kind is not None)!=(self.state=='cancelled'):raise ValueError('Cancellation kind mismatch')
        return self

class JobResponse(BaseModel):
    model_config=ConfigDict(extra='forbid')
    job:LocalJob

class CancelResponse(JobResponse):
    cancelled_before_execution:bool

class ErrorBody(BaseModel):
    code:str
    message:str
class ErrorResponse(BaseModel):
    error:ErrorBody
