import hashlib,shutil,subprocess
import pytest
from fresh_review.clips import ClipLimits,extract_clip_frames
LIMITS=ClipLimits(1_000_000,3,3,640,640*640,5)
@pytest.fixture
def clip(tmp_path):
 if not shutil.which('ffmpeg')or not shutil.which('ffprobe'):pytest.fail('ffmpeg and ffprobe required for clip preparation verification')
 p=tmp_path/'generated.mp4'
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=64x48:r=5:d=2','-c:v','mpeg4','-y',str(p)],check=True,timeout=5)
 return p.read_bytes()
def test_generated_clip_frames_bound_identity_no_inference(clip):
 out=extract_clip_frames(clip,[0,.8,1.6],LIMITS)
 assert len(out['frames'])==3 and out['provider_calls']==0 and out['inference_status']=='not_run'
 assert out['source_clip_sha256']==hashlib.sha256(clip).hexdigest()and out['evidence_export_allowed']is False
 assert all(f['width']==64 and f['height']==48 and f['timestamp_basis'].startswith('requested_decode')for f in out['frames'])
 assert len({f['sample_index']for f in out['frames']})==3 # repeated pixels do not collapse sampled positions
@pytest.mark.parametrize('offsets',[[2],[-1],[True],[.8,.2],[0,0],[float('nan')],[0,.3,.6,.9]])
def test_clip_bad_offsets(clip,offsets):
 with pytest.raises(ValueError):extract_clip_frames(clip,offsets,LIMITS)
def test_clip_caps_and_corruption(clip):
 with pytest.raises(ValueError):extract_clip_frames(clip,[0],ClipLimits(1,3,3,640,409600,5))
 with pytest.raises(ValueError):extract_clip_frames(clip,[0],ClipLimits(1000000,1,3,640,409600,5))
 with pytest.raises(ValueError):extract_clip_frames(b'not a clip',[0],LIMITS)
 with pytest.raises(ValueError):extract_clip_frames(clip,[0],ClipLimits(1000000,3,3,32,1024,5))

def test_playlist_or_external_reference_input_rejected():
 # Never hand a playlist/local-file reference document to an autodetecting decoder.
 with pytest.raises(ValueError,match='MP4 container'):extract_clip_frames(b'#EXTM3U\nfile:///etc/passwd\n',[0],LIMITS)

def test_local_decoder_requires_limiter(clip,monkeypatch):
 monkeypatch.setattr('fresh_review.clips.shutil.which',lambda _:None)
 with pytest.raises(ValueError,match='prlimit'):extract_clip_frames(clip,[0],LIMITS)
