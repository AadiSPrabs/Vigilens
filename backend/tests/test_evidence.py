import io,os
import pytest
from PIL import Image,PngImagePlugin
from pipeline import Frame
from core import AuditError
from evidence import SyntheticEvidenceStore
F=Frame(64,32,'synthetic-frame')
def im():return Image.new('RGB',(64,32),'white')
def test_store_binds_scope_audit_pixels_restart(tmp_path):
 p=tmp_path/'s';s=SyntheticEvidenceStore(p);x=s.put('scope','audit',F,im(),source='synthetic')
 assert x['source']=='synthetic' and not x['evidence_export_allowed']
 assert SyntheticEvidenceStore(p).put('scope','audit',F,im(),source='synthetic')==x
 assert os.stat(p).st_mode&0o077==0
 with pytest.raises(KeyError):s.read_for_local_test(x['asset_id'],'wrong')
 with pytest.raises(KeyError):s.delete(x['asset_id'],'wrong')
 with pytest.raises(AuditError):s.put('scope','audit',F,Image.new('RGB',im().size,'red'),source='synthetic')
def test_deleted_tombstone_cannot_restore_or_read(tmp_path):
 s=SyntheticEvidenceStore(tmp_path/'s');x=s.put('s','a',F,im(),source='synthetic');a=x['asset_id']
 assert s.delete(a,'s') and not s.delete(a,'s')
 assert s.put('s','a',F,im(),source='synthetic')['state']=='deleted'
 with pytest.raises(KeyError):s.read_for_local_test(a,'s')
 assert s.events(a,'s')[-1]['action']=='synthetic_payload_deleted_tombstone_retained'
def test_strip_private_metadata(tmp_path):
 s=SyntheticEvidenceStore(tmp_path/'s');image=im();image.info['secret']='private GPS';x=s.put('s','a',F,image,source='synthetic')
 data=s.read_for_local_test(x['asset_id'],'s')
 assert b'private GPS' not in data and not Image.open(io.BytesIO(data)).info
 assert s.events(x['asset_id'],'s')[-1]['action']=='local_test_read_not_export'
def test_real_asset_fails_closed(tmp_path):
 s=SyntheticEvidenceStore(tmp_path/'s')
 with pytest.raises(AuditError):s.put('s','a',F,im(),source='backend')
def test_frame_mismatch(tmp_path):
 s=SyntheticEvidenceStore(tmp_path/'s')
 with pytest.raises(AuditError):s.put('s','a',F,Image.new('RGB',(32,64)),source='synthetic')
def test_asset_and_record_limits(tmp_path):
 s=SyntheticEvidenceStore(tmp_path/'one',max_asset_bytes=4)
 with pytest.raises(AuditError):s.put('s','a',F,im(),source='synthetic')
 s=SyntheticEvidenceStore(tmp_path/'two',max_records=1);s.put('s','a',F,im(),source='synthetic')
 with pytest.raises(AuditError):s.put('s','b',F,im(),source='synthetic')
def test_existing_public_file_refused(tmp_path):
 p=tmp_path/'s';p.touch();p.chmod(0o644)
 with pytest.raises(ValueError):SyntheticEvidenceStore(p)
def test_path_symlink_refused(tmp_path):
 p=tmp_path/'s';p.symlink_to(tmp_path/'target')
 with pytest.raises(OSError):SyntheticEvidenceStore(p)
