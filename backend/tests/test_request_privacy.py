import io,base64
from PIL import Image,PngImagePlugin
from adapters import build_sam_image_request
from muse_adapter import build_muse_ppe_request
from core import decode_image

def photo():
 im=Image.new('RGB',(64,32),'#123456');b=io.BytesIO();info=PngImagePlugin.PngInfo();info.add_text('PrivateLocation','SENSITIVE_TEST_METADATA');im.save(b,'PNG',pnginfo=info);return b.getvalue()
def test_request_bytes_are_metadata_free_exact_pixels():
 data=photo()
 for x in (build_sam_image_request(data,'image/png','person'),build_muse_ppe_request(data,'image/png','p1')):
  uri=x['input'][0]['content'][1]['image_url'];payload=base64.b64decode(uri.split(',')[1]);im=Image.open(io.BytesIO(payload))
  assert b'SENSITIVE_TEST_METADATA' not in payload and not im.info
  assert decode_image(payload,'image/png').digest==decode_image(data,'image/png').digest

def test_request_schema_caller_mutation_cannot_change_future_requests():
 x=build_muse_ppe_request(photo(),'image/png','p1');x['text']['format']['schema']['properties'].clear()
 assert 'helmet' in build_muse_ppe_request(photo(),'image/png','p1')['text']['format']['schema']['properties']
