"""Bounded local clip preparation only. No provider dispatch or cross-frame identity.
Requires operator-selected technical limits and offsets; not an HTTP upload API.
"""
import hashlib,io,json,math,subprocess,tempfile,os,signal,shutil
from dataclasses import dataclass
from pathlib import Path
from PIL import Image
from core import decode_image

@dataclass(frozen=True)
class ClipLimits:
    max_bytes:int
    max_seconds:float
    max_frames:int
    max_side:int
    max_pixels:int
    subprocess_seconds:float
    def validate(self):
        for value,ceiling in [(self.max_bytes,50_000_000),(self.max_frames,16),(self.max_side,4096),(self.max_pixels,16_000_000)]:
            if type(value)is not int or not 1<=value<=ceiling:raise ValueError('Bounded explicit clip limits required')
        if any(type(v)not in (int,float)or not math.isfinite(v)or not 0<v<=120 for v in (self.max_seconds,self.subprocess_seconds)):raise ValueError('Bounded duration/timeout required')

def _run(command,timeout,output_cap=500_000):
    # Files only, no network protocols or shell. Caller-generated paths only.
    with tempfile.TemporaryFile()as out,tempfile.TemporaryFile()as err:
        limiter=shutil.which('prlimit')
        if not limiter:raise ValueError('Linux prlimit required for local clip decoding')
        bounded=[limiter,'--as=2147483648','--fsize=16000000','--cpu='+str(math.ceil(timeout))+':'+str(math.ceil(timeout)+1),'--nofile=64','--core=0','--']+command
        process=subprocess.Popen(bounded,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,
                                 env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
        try:process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait();raise ValueError('Local clip decoder timeout; no retry')
        if process.returncode:raise ValueError('Local clip decoder failed')
        if out.tell()>output_cap:raise ValueError('Decoder metadata/output cap exceeded')
        out.seek(0);return out.read(output_cap+1)

def extract_clip_frames(raw,offsets,limits,*,ffmpeg='ffmpeg',ffprobe='ffprobe'):
    limits.validate()
    if not isinstance(raw,bytes)or not 1<=len(raw)<=limits.max_bytes:raise ValueError('Clip byte cap exceeded')
    if not isinstance(offsets,list)or not 1<=len(offsets)<=limits.max_frames or any(type(t)not in (int,float)or not math.isfinite(t)or t<0 for t in offsets)or sorted(set(offsets))!=offsets:raise ValueError('Explicit ordered unique frame offsets required')
    # Restrict local intake to ISO-BMFF MP4, not playlists, image sequences or
    # formats that can reference arbitrary external local files.
    if len(raw)<16 or raw[4:8]!=b'ftyp':raise ValueError('MP4 container required for bounded local intake')
    source_sha=hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory(prefix='vigilens-clip-local-')as tmp:
        path=Path(tmp)/'source.clip';path.write_bytes(raw);path.chmod(0o600)
        probe=json.loads(_run([ffprobe,'-v','error','-protocol_whitelist','file,pipe','-format_whitelist','mov','-enable_drefs','0','-use_absolute_path','0','-show_format','-show_streams','-of','json',str(path)],limits.subprocess_seconds))
        videos=[s for s in probe.get('streams',[])if s.get('codec_type')=='video']
        if len(videos)!=1:raise ValueError('Exactly one video stream required')
        stream=videos[0];duration=float(probe.get('format',{}).get('duration','nan'))
        w,h=stream.get('width'),stream.get('height')
        if any(type(v)is not int or not 1<=v<=limits.max_side for v in (w,h))or w*h>limits.max_pixels:raise ValueError('Clip raster quota exceeded')
        if not math.isfinite(duration)or not 0<duration<=limits.max_seconds or offsets[-1]>=duration:raise ValueError('Clip duration or offsets outside limits')
        if stream.get('tags',{}).get('rotate')not in (None,'0')or any(s.get('rotation',0)!=0 for s in stream.get('side_data_list',[])):raise ValueError('Upright clip required; do not silently rotate source coordinates')
        frames=[]
        for index,offset in enumerate(offsets):
            # Accurate decode seek after input, not keyframe-only fast seek.
            image_path=Path(tmp)/f'frame-{index}.png'
            _run([ffmpeg,'-v','error','-nostdin','-protocol_whitelist','file,pipe','-format_whitelist','mov','-enable_drefs','0','-use_absolute_path','0','-noautorotate','-i',str(path),'-ss',str(offset),'-map','0:v:0','-frames:v','1','-an','-sn','-dn','-threads','1','-c:v','png','-f','image2',str(image_path)],limits.subprocess_seconds)
            if not image_path.is_file()or image_path.stat().st_size>15_000_000:raise ValueError('Frame output unavailable/too large')
            with Image.open(image_path)as im:
                im.load();rgb=im.convert('RGB');clean=Image.frombytes('RGB',rgb.size,rgb.tobytes());buf=io.BytesIO();clean.save(buf,'PNG');png=buf.getvalue()
            frame=decode_image(png,'image/png')
            if (frame.width,frame.height)!=(w,h):raise ValueError('Decoded clip frame shape changed')
            frames.append({'sample_index':index,'requested_offset_seconds':offset,
                           'timestamp_basis':'requested_decode_offset_not_exact_presentation_timestamp',
                           'source_clip_sha256':source_sha,'pixel_digest':frame.digest,
                           'width':w,'height':h,'png':png})
    return {'source_clip_sha256':source_sha,'duration_seconds':duration,'frames':frames,
            'frame_identity':'clip_hash_plus_sample_index_plus_pixel_digest',
            'decoder_limits':'local_linux_memory_cpu_file_descriptor_file_size_timeout_bounds_not_security_sandbox',
            'cross_frame_person_identity':'not_inferred','inference_status':'not_run',
            'sampled_frames_are_not_complete_clip_coverage':True,
            'provider_calls':0,'evidence_export_allowed':False}
