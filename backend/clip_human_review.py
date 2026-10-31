"""Local human reviewer for sampled clip frames. PRIVATE, no provider call, no network, no key use.

Every answer is typed by the reviewer. Nothing is defaulted to yes. Closed input, an unopenable viewer,
or any failed binding aborts and records the frame as not acknowledged. It is not a safety or privacy
clearance and keeps export disabled. It reuses the repo's own display, review and clip-report routes.
"""
from io import BytesIO
import json,os,shutil,subprocess,platform,time,hashlib,secrets
from pathlib import Path
from PIL import Image,ImageDraw
from fresh_review.pipeline import digest

class ReviewAbort(Exception):pass
MAX_RETRY=5
FRAME_KEYS=('foreground_checked','background_checked','reflections_checked','derivative_checked')
FRAME_Q={'foreground_checked':'I looked at the whole foreground of this preview',
 'background_checked':'I looked at the whole background of this preview',
 'reflections_checked':'I checked reflections, glass and shiny surfaces',
 'derivative_checked':'The black boxes hide every visible face in this preview'}
PERSON_Q=(('exact_source_confirmed','This person in the preview is the same person as the saved box'),
 ('face_coverage_checked','This person\'s face is fully covered in the preview'),
 ('head_evidence_visible','The head/headgear is visible enough to judge a helmet'),
 ('torso_evidence_visible','The torso is visible enough to judge a vest'))

class Console:
    def __init__(self,inp=input,out=print):self.inp=inp;self.out=out
    def say(self,*a):self.out(' '.join(str(x)for x in a))
    def ask(self,q):
        try:return self.inp(q+' ').strip()
        except EOFError:raise ReviewAbort('input closed; nothing acknowledged')
    def yn(self,q):
        for _ in range(MAX_RETRY):
            a=self.ask(q+' [y/n]')
            if a in('y','n'):return a=='y'
            self.say('  type exactly y or n')
        raise ReviewAbort('no valid y/n answer')

def open_viewer(path):
    """True only if a viewer launch command ran and reported success. Never assumed."""
    try:
        s=platform.system()
        if s=='Darwin':cmd=['open',str(path)]
        elif s=='Windows':os.startfile(str(path));return True
        else:cmd=['xdg-open',str(path)]
        return subprocess.run(cmd,timeout=15,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    except Exception:return False

def show(path,io,viewer,manual_view):
    io.say('  File:',path)
    if viewer(Path(path)):return
    if not manual_view:raise ReviewAbort('could not open an image viewer; nothing acknowledged (rerun with --manual-view to open the file yourself)')
    if io.ask('  Viewer did not open. Open that file yourself, then type exactly: viewed ->')!='viewed':raise ReviewAbort('viewing not confirmed')

def guide_image(png,persons,path):
    im=Image.open(BytesIO(png)).convert('RGB');d=ImageDraw.Draw(im);w,h=im.size
    for x in range(0,w,64):d.line([(x,0),(x,h)],fill=(255,255,0),width=1);d.text((x+2,2),str(x),fill=(255,255,0))
    for y in range(0,h,64):d.line([(0,y),(w,y)],fill=(255,255,0),width=1);d.text((2,y+2),str(y),fill=(255,255,0))
    for p in persons:
        b=p['box_half_open'];d.rectangle(b,outline=(0,255,255),width=3);d.text((b[0]+6,b[1]+6),'#'+p['id'],fill=(0,255,255))
    im.save(path)

def parse_regions(io,frame_size):
    io.say('  Type one black box per line as:  id left top right bottom   (pixels of this frame; blank line to finish).')
    io.say('  Cover each face. Boxes also hide whatever is under them (a helmet under a box is not visible evidence).')
    regions=[];seen=set()
    while len(regions)<64:
        s=io.ask('   box>')
        if not s:break
        a=s.split()
        try:
            if len(a)!=5 or a[0]in seen:raise ValueError
            b=[int(v)for v in a[1:]]
            if not(0<=b[0]<b[2]<=frame_size[0]and 0<=b[1]<b[3]<=frame_size[1]):raise ValueError
        except ValueError:io.say('   rejected (need: unique id then 4 ints inside the frame)');continue
        seen.add(a[0]);regions.append({'person_id':a[0],'box':b})
    if not regions:raise ReviewAbort('at least one covering box is required; zero boxes cannot show there are no faces')
    return regions

def run_review(c,pl,clip_id,manifest,load_png,out,io,*,label,viewer=open_viewer,manual_view=False):
    """c: client carrying the owner/display headers. Returns record. Writes outputs only if every frame was acknowledged."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if not label.strip()or len(label)>80:raise ReviewAbort('reviewer label required (text only, not verified identity)')
    record={'kind':'local_human_review_record','reviewer_label_typed':label,'clip_review_id':clip_id,'complete':False,'frames':[],'privacy_review_status':'not_validated','evidence_export_allowed':False}
    sessions=[];done={}
    def save():(out/'review-record-TYPED-BY-HUMAN.json').write_text(json.dumps(record,indent=1))
    try:
        for fr in manifest['frames']:
            i=fr['sample_index'];src=fr['pixel_digest'];size=[fr['width'],fr['height']]
            if src in done:
                j,prev=done[src];io.say(f'\nFrame {i} has the same pixels as frame {j}; your answers for frame {j} apply to the same preview.')
                sessions.append({'sample_index':i,'session_id':prev['session_id'],'review':prev['review']});record['frames'].append({'sample_index':i,'source_digest':src,'same_pixels_as':j});continue
            png=load_png(fr)
            job=pl.read(src)
            if not job or job['state']!='completed'or digest(job['result'])!=fr['result_sha256']:raise ReviewAbort(f'frame {i}: saved result changed')
            res=job['result'];persons=res['persons']
            io.say(f"\n===== FRAME {i} (requested offset {fr['requested_offset_seconds']}s, {size[0]}x{size[1]}) =====")
            for p in persons:
                r=f"helmet {p['helmet']}, vest {p['vest']}"if p.get('ppe_assessed')else'UNASSESSED '+str((p.get('crop_eligibility',{}).get('review_reasons')or['n/a'])[0])
                io.say(f"  person #{p['id']}  box {p['box_half_open']}  provider: {r}")
            guide=out/f'guide-frame{i}.png';guide_image(png,persons,guide)
            io.say('  Guide image: cyan boxes = detected people, yellow grid = pixel coordinates.');show(guide,io,viewer,manual_view)
            for attempt in range(3):
                regions=parse_regions(io,size)
                body=json.dumps({'source_digest':src,'frame_size':size,'regions':regions,'reviewer_label':label})
                resp=c.post(f'/fresh-review/{src}/private-display',files={'image':('f.png',png,'image/png')},data={'review':body})
                if resp.status_code!=200:io.say('  preview refused:',resp.text[:160]);continue
                x=resp.json();img=c.get(f"/private-display/{x['session_id']}/image").content
                pv=out/f'preview-frame{i}.png';pv.write_bytes(img);show(pv,io,viewer,manual_view)
                ack={'source_digest':x['source_digest'],'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'frame_size':size}
                for k in FRAME_KEYS:ack[k]=io.yn('   '+FRAME_Q[k]+'?')
                if all(ack[k]for k in FRAME_KEYS):break
                io.say('  Not all confirmed. Re-enter the boxes.')
            else:raise ReviewAbort(f'frame {i}: not acknowledged')
            if c.post(f"/private-display/{x['session_id']}/review",json=ack).status_code!=200:raise ReviewAbort(f'frame {i}: preview binding refused')
            pp={}
            for p in persons:
                io.say(f"  Person #{p['id']}:");pp[p['id']]={k:io.yn('   '+q+'?')for k,q in PERSON_Q}
            rev={'assessment_id':'fresh:'+src+':'+digest(res),'source_digest':src,'output_sha256':x['output_sha256'],'regions_digest':x['regions_digest'],'persons':pp}
            sessions.append({'sample_index':i,'session_id':x['session_id'],'review':rev});done[src]=(i,sessions[-1])
            record['frames'].append({'sample_index':i,'source_digest':src,'output_sha256':x['output_sha256'],'regions':regions,'whole_frame_ack':ack,'persons':pp,'typed_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')})
        path=f'/fresh-private-clip-report/{clip_id}';payload={'frames':sessions}
        rep=c.post(path,json=payload);pdf=c.post(path+'/pdf-preview',json=payload)
        record['report_http']=rep.status_code;record['pdf_http']=pdf.status_code
        if rep.status_code!=200 or pdf.status_code!=200 or pdf.content[:5]!=b'%PDF-':raise ReviewAbort('combined report refused; no output written')
        (out/'combined-report.json').write_text(json.dumps(rep.json(),indent=1));(out/'combined-private-clip-preview.pdf').write_bytes(pdf.content)
        record['complete']=True;return record
    finally:save()

def setup_workdir(bundle,work):
    """Copy-only runtime. The bundle (journal, proofs, approvals) is never opened for writing."""
    bundle=Path(bundle);work=Path(work);work.mkdir(mode=0o700,exist_ok=True);os.chmod(work,0o700)
    d=work/'data';d.mkdir(mode=0o700);os.chmod(d,0o700);shutil.copytree(bundle/'proof-v4',work/'proof-v4')
    for f in(bundle/'data').iterdir():shutil.copy(f,d/f.name)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    for n in('approvals.json','carry-v4-candidate.json','manifest-v4-candidate.json'):shutil.copy(bundle/n,work/n);os.chmod(work/n,0o600)
    (work/'token').write_text(secrets.token_urlsafe(40));os.chmod(work/'token',0o600)
    (work/'nokey').write_text('REVIEW-ONLY-NO-PROVIDER-CALLS');os.chmod(work/'nokey',0o600)
    cfg={'version':1,'journal':str(d/'journal.sqlite'),'carry_path':str(work/'carry-v4-candidate.json'),'carry_sha256':sha(work/'carry-v4-candidate.json'),'approval_path':str(work/'approvals.json'),'approval_sha256':sha(work/'approvals.json'),'key_file':str(work/'nokey'),'access_token_file':str(work/'token'),'execution_scope':'private_provider_processing','wide_scene_limits':{'sequential':True,'max_people':10,'max_ppe_calls':2,'min_crop_width':32,'min_crop_height':64},'chain_manifest_path':str(work/'manifest-v4-candidate.json'),'chain_manifest_sha256':sha(work/'manifest-v4-candidate.json'),'chain_proof_dir':str(work/'proof-v4')}
    (work/'rt.json').write_text(json.dumps(cfg));os.chmod(work/'rt.json',0o600)
    return work/'rt.json',(work/'token').read_text().strip()
