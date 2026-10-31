import io,asyncio
import pytest
from PIL import Image
from core import AuditError
from crops import prepare_raster,crop_for_selected_object,PreparedRaster
from pipeline import Frame
from sam_parser import parse_sam_image_text
from test_sam_parser import TEXT

def raster(colour='white'):
 im=Image.new('RGB',(320,334),colour);b=io.BytesIO();im.save(b,'PNG');return prepare_raster(b.getvalue(),'image/png')
def parsed(r):return asyncio.run(parse_sam_image_text(TEXT,r.frame,wire_completed=True))
def test_parser_to_exact_source_crop_to_disabled_muse_request():
 from muse_adapter import build_muse_ppe_request
 r=raster();p=parsed(r);crop=crop_for_selected_object(r,p,'0')
 assert (crop['width'],crop['height'])==(60,27) and not crop['person_identity_verified']
 request=build_muse_ppe_request(crop['png'],'image/png','object-0')
 assert request['model']=='muse-spark-1.3' and not crop['evidence_export_allowed']
 # This is plumbing against a doc mask, NOT a person detection on this blank input.

def test_same_dimensions_different_pixels_refuse_crop():
 a=raster();b=raster('red')
 with pytest.raises(AuditError):crop_for_selected_object(b,parsed(a),'0')
def test_prepared_raster_tampered_identity_refused():
 r=raster();bad=PreparedRaster(r.png,Frame(320,334,'wrong-digest'))
 with pytest.raises(AuditError):crop_for_selected_object(bad,parsed(r),'0')
def test_missing_object_no_other_crop_substitution():
 r=raster()
 with pytest.raises(AuditError):crop_for_selected_object(r,parsed(r),'other')
def test_duplicate_selected_object_refused():
 r=raster();p=parsed(r);p['objects']*=2
 with pytest.raises(AuditError):crop_for_selected_object(r,p,'0')
def test_crop_dimensions_cannot_swap():
 r=raster();p=parsed(r);p['objects'][0]['mask']=Image.new('L',(27,60))
 with pytest.raises(AuditError):crop_for_selected_object(r,p,'0')
