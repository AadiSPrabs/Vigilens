"""Deterministic private overlays on treated pixels only. Never a released evidence asset."""
import io,hashlib
from PIL import Image,ImageDraw,ImageFilter,ImageChops
from .masks import decode_mask
from .zones import canonical_zones


def person_display_labels(result):
    """Stable display labels shared with the stage: position in the stored persons list plus 1, only when the
    id is unique and the stored box is a usable integer box inside the frame. Otherwise the person is unmapped
    (no number, no tag). The id always travels with the label."""
    frame=result.get('image')or{};W,H=frame.get('width'),frame.get('height');people=result.get('persons')or[]
    counts={}
    for p in people:counts[p.get('id')]=counts.get(p.get('id'),0)+1
    out={}
    for i,p in enumerate(people):
        box=p.get('box_half_open');ok=(isinstance(box,(list,tuple))and len(box)==4 and all(type(v)is int for v in box)and type(W)is int and type(H)is int
            and 0<=box[0]<box[2]<=W and 0<=box[1]<box[3]<=H)
        pid=str(p.get('id'));mapped=bool(ok and counts[p.get('id')]==1)
        out[pid]={'mapped':mapped,'label':('Person %d'%(i+1))if mapped else'Unmapped person','text':(('Person %d (backend id %s)'%(i+1,pid))if mapped else('Unmapped person (backend id %s)'%pid))}
    return out

def render_overlay(treated_png,result,zones,redaction_regions=(),ppe_segmentations=()):
    with Image.open(io.BytesIO(treated_png))as image:
        image.load();out=image.convert('RGB').copy()
    frame=result['image']
    if out.size!=(frame['width'],frame['height']):raise ValueError('Exact treated source frame required')
    # One-pixel inner raster boundary from actual lossless mask, not a bounding-box substitute.
    for person in result['persons']:
        if person.get('mask')is None:
            # Unverified geometry: raw box only, distinct dashed outline, never a mask or person shape.
            l,t,r,b=person['box_half_open'];d=ImageDraw.Draw(out)
            for x in range(l,r,12):d.line([(x,t),(min(x+6,r-1),t)],fill=(230,140,20),width=2);d.line([(x,b-1),(min(x+6,r-1),b-1)],fill=(230,140,20),width=2)
            for y in range(t,b,12):d.line([(l,y),(l,min(y+6,b-1))],fill=(230,140,20),width=2);d.line([(r-1,y),(r-1,min(y+6,b-1))],fill=(230,140,20),width=2)
            continue
        mask=decode_mask(person['mask']);l,t,r,b=person['box_half_open']
        if mask.size!=(r-l,b-t)or person['mask']['source_frame_size']!=list(out.size):raise ValueError('Exact mask placement required')
        padded=Image.new('L',(mask.width+2,mask.height+2));padded.paste(mask,(1,1))
        eroded=padded.filter(ImageFilter.MinFilter(3)).crop((1,1,mask.width+1,mask.height+1))
        edge=ImageChops.subtract(mask,eroded)
        out.paste((35,130,110),(l,t,r,b),edge)
    # Auxiliary PPE masks are source-coordinate geometry only, not proof gear
    # is worn. Preserve every object; never convert empty matches to absence.
    for segmentation in ppe_segmentations:
        concept=segmentation['concept']
        if concept not in ('helmet','vest'):raise ValueError('Unsupported PPE overlay concept')
        for obj in segmentation['objects']:
            mask=decode_mask(obj['mask']);l,t,r,b=obj['box_half_open']
            if obj['mask']['source_frame_size']!=list(out.size)or mask.size!=(r-l,b-t):raise ValueError('PPE mask frame changed')
            padded=Image.new('L',(mask.width+2,mask.height+2));padded.paste(mask,(1,1))
            eroded=padded.filter(ImageFilter.MinFilter(3)).crop((1,1,mask.width+1,mask.height+1))
            edge=ImageChops.subtract(mask,eroded)
            out.paste((135,70,170)if concept=='helmet'else(40,100,210),(l,t,r,b),edge)
    draw=ImageDraw.Draw(out)
    for zone in canonical_zones(zones):
        # Map normalized edge coordinates to the same raster, clipped at outermost pixel.
        points=[(min(out.width-1,max(0,round(p['x']*out.width))),min(out.height-1,max(0,round(p['y']*out.height))))for p in zone['points']]
        draw.line(points+[points[0]],fill=(230,170,30),width=1)
    if result.get('wide_scene',{}).get('sequential')is True:
        # Wide sequential jobs only: number every person and color-code PPE evidence status.
        from PIL import ImageFont
        fs=max(13,round(out.width/90));font=ImageFont.load_default(size=fs);colors={'provider_observed':(20,120,60),'budget_deferred_never_attempted':(200,110,0),'crop_evidence_ineligible':(110,110,110),'not_selected_within_explicit_PPE_call_budget':(70,70,170),'geometry_unverified_not_assessed':(150,30,150),'ppe_withheld_source_has_unverified_geometry':(90,90,90)}
        for person in result['persons']:
            l,t,r,b=person['box_half_open'];label='P'+str(person['id']);w=int(draw.textlength(label,font=font))+6;th=fs+4;y0=t-th-1 if t>=th+1 else t+1
            x0=min(max(0,l),max(0,out.width-w));draw.rectangle((x0,y0,x0+w,y0+th),fill=colors.get(person.get('ppe_evidence_status'),(0,0,0)));draw.text((x0+3,y0+2),label,fill=(255,255,255),font=font)
    else:
        # Non-sequential jobs: tag each mapped person with the same "Person N" label the stage shows.
        from PIL import ImageFont
        labels=person_display_labels(result);fs=max(13,round(out.width/70));font=ImageFont.load_default(size=fs)
        for person in result['persons']:
            info=labels.get(str(person['id']))
            if not info or not info['mapped']:continue
            l,t,r,b=person['box_half_open'];label=info['label'];w=int(draw.textlength(label,font=font))+6;th=fs+4
            # Above the head when there is room, else below the feet, else (no room anywhere) inside the box top.
            y0=t-th-1 if t>=th+1 else (b+1 if b+th+1<=out.height else t+1)
            x0=min(max(0,l),max(0,out.width-w));draw.rectangle((x0,y0,x0+w,y0+th),fill=(20,20,20));draw.text((x0+3,y0+2),label,fill=(255,255,255),font=font)
    # Restore every treated privacy region after drawing, so overlay lines cannot
    # alter or obscure the reviewed treatment. No source pixels are used.
    with Image.open(io.BytesIO(treated_png))as treated:
        for region in redaction_regions:
            box=region['box'];out.paste(treated.crop(box),(box[0],box[1]))
    clean=Image.frombytes('RGB',out.size,out.tobytes());buf=io.BytesIO();clean.save(buf,'PNG');png=buf.getvalue()
    return png,hashlib.sha256(png).hexdigest()
