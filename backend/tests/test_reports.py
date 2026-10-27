import copy
import pytest
from pydantic import ValidationError
from reports import validate_offline_report,OfflineReport
from pipeline import OfflinePipeline,Frame,Observation,SegmentationBatch
from test_backend import PERSON,Z

def report():return OfflinePipeline().run(SegmentationBatch(Frame(128,72,'synthetic'),(Observation('p',tuple(PERSON),'absent','unknown'),),True),Z)

def test_typed_report_schema_local_only():
 x=report();assert validate_offline_report(x)==x
 assert OfflineReport.model_json_schema()['properties']['evidence_export_allowed']['const'] is False
@pytest.mark.parametrize('field,value',[('evidence_export_allowed',True),('evidence_status','masked'),('evidence_image','raw.jpg'),('source','backend'),('privacy_review_status','approved')])
def test_report_rejects_evidence_and_real_labels(field,value):
 x=report();x[field]=value
 with pytest.raises(ValidationError):validate_offline_report(x)
def test_report_rejects_favourable_severity():
 x=report();x['persons'][0]['worst_severity']=None
 with pytest.raises(ValidationError):validate_offline_report(x)
def test_report_rejects_removed_uncertainty():
 x=report();x['persons'][0]['findings']=[f for f in x['persons'][0]['findings'] if f['kind']!='uncertainty']
 with pytest.raises(ValidationError):validate_offline_report(x)
def test_report_rejects_recheck_count_fiction():
 x=report();x['recheck_attempts']=1
 with pytest.raises(ValidationError):validate_offline_report(x)
def test_report_rejects_unapproved_extra_prose():
 x=report();x['model_claim']='safe'
 with pytest.raises(ValidationError):validate_offline_report(x)
def test_report_rejects_wrong_zone_membership():
 x=report();x['persons'][0]['zone_ids']=[]
 with pytest.raises(ValidationError):validate_offline_report(x)

def test_report_rejects_invented_recheck_person():
 x=report();x['recheck_attempts']=1;x['recheck_trace']=[{'person_id':'not-real','attempt':1,'action':'local_mock_recheck','outcome':'returned'}]
 with pytest.raises(ValidationError):validate_offline_report(x)
def test_report_rejects_missing_original_provenance():
 x=report();x['persons'][0]['original_observations']={}
 with pytest.raises(ValidationError):validate_offline_report(x)
