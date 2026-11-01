"""Private PDF preview from an exact treated overlay and server-built report.
No external assets, source fallback, release certification or general HTML renderer.
"""
import io,textwrap,hashlib
from PIL import Image,ImageDraw,ImageFont

def render_private_pdf(report,overlay_png,*,_pages_only=False):
    if report.get('source')!='private_report_preview_not_released'or report.get('evidence_export_allowed')is not False:
        raise ValueError('Exact private report required')
    if not isinstance(overlay_png,bytes)or len(overlay_png)>15_000_000:raise ValueError('Bounded treated overlay required')
    with Image.open(io.BytesIO(overlay_png))as im:
        im.load();overlay=im.convert('RGB').copy()
    pages=[];width,height=1240,1754
    regular=ImageFont.load_default(size=22);heading=ImageFont.load_default(size=38);small=ImageFont.load_default(size=18)
    page=None;draw=None;y=0
    def new_page():
        nonlocal page,draw,y
        if page is not None:pages.append(page)
        if len(pages)>=32:raise ValueError('Private document page quota exceeded')
        page=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(page);y=72
        draw.text((72,y),'Vigilens | Private audit preview',fill='#251f21',font=heading);y+=64
        draw.rectangle((72,y,width-72,y+76),fill='#f4efec')
        draw.text((88,y+12),'NOT RELEASED EVIDENCE. Human review required.',fill='#251f21',font=regular)
        draw.text((88,y+42),'No safety clearance, compliance finding or face-coverage guarantee.',fill='#585254',font=small);y+=104
    def line(text,font=None):
        nonlocal y
        # Fixed wrap, no executable markup. Keep all identifiers/findings, paginate.
        for part in textwrap.wrap(str(text),width=86,replace_whitespace=True)or['']:
            if y>height-110:new_page()
            draw.text((72,y),part,fill='#251f21',font=font or regular);y+=32
    new_page()
    line('Source pixel identity: '+report['source_digest'],small)
    line('Assessment: '+report['assessment_id'],small)
    line('Private preview image: '+report['derivative_sha256'],small)
    line('Privacy: '+report['privacy_review_status']+'. No hidden original fallback.',small)
    if report.get('clip_sample_label'):line(report['clip_sample_label'],small)
    if report.get('face_covering_review'):line('Face already hidden by opaque worn shield: operator claim, not privacy validation.',small)
    if report.get('archive_provenance'):
        line('ARCHIVED REAL INPUT REVIEW. No fresh inference or restored original job.',small)
    config=report.get('configured_rule_review',{}).get('configuration_scope')
    if config=='illustrative_demo':line('Illustrative demo rules, not legal or site-safety policy. See recorded operator approval.',small)
    if report.get('configured_rule_review',{}).get('policy_id'):line('Recorded policy label: '+report['configured_rule_review']['policy_id']+' (label alone does not verify authority).',small)
    if (report.get('zone_review')or{}).get('zone_snapshot'):line('Operator-drawn zones present (illustrative geometry only): zone membership comes from manual contact claims, no site policy or compliance applied.',small)
    if report.get('wide_scene'):
        w=report['wide_scene']
        if w.get('sequential'):
            deferred=w.get('budget_deferred_never_attempted',[])
            line(('PARTIAL JOB (budget stop). ' if w.get('job_state')=='partial_completed' else 'PPE WITHHELD FOR THIS SOURCE (unverified geometry); no PPE call was made. ' if w.get('ppe_withheld_unverified_geometry') else 'Sequential job finished its authorized stages. ')+str(w['detected_person_count'])+' detected, '+str(w['PPE_assessed_count'])+' with a provider PPE observation attempted (not resolved assessments).',small)
            line('Not attempted, budget deferred: '+str(len(deferred)),small)
            line('Evidence ineligible: '+str(w.get('ineligible_unassessed_count','?'))+' | Eligible, not selected: '+str(w.get('not_selected_eligible_count','?')),small)
            line('Unassessed people remain unknown, not clear. Not complete wide-area PPE qualification.',small)
            if w.get('geometry_unverified_count'):
                line('GEOMETRY UNVERIFIED: '+str(w['geometry_unverified_count'])+' person(s) kept as a raw box only (mask did not match box; provider geometry not verified, cause not established). Purple tag, dashed orange outline. Not assessed, no zone or contact use. No new PPE dispatch was made for ANY person in this source because geometry containment cannot be proved. Verified masks are not an accuracy certification. This is a geometry review only.',small)
            line('Tag colors show only whether a provider PPE observation was attempted, never safety: green = provider observation attempted (reading may be unknown or absent; partial evidence is labelled per person; not safe or clear), orange = not attempted (budget), grey = evidence ineligible, blue = eligible but not selected, purple = geometry unverified (never assessed), dark grey = eligible but PPE withheld for the whole source.',small)
        else:
            line('WIDE SCENE: '+str(w['detected_person_count'])+' detected, '+str(w['PPE_assessed_count'])+' with a provider PPE observation attempted (not resolved assessments). PARTIAL selected-crop coverage.',small)
            line('Unassessed people remain unknown. This is not complete wide-area PPE qualification.',small)
    bc=report.get('ppe_basis_counts')
    if bc and report.get('wide_scene'):
        line('PPE provider observations attempted: '+str(bc['provider_observation_attempted_count'])+' of '+str(bc['detected_count'])+' detected. Outcomes emitted: '+str(bc['outcome_emitted_count'])+' (all from the clean-crop rule); legacy basis not recorded, outcome withheld: '+str(bc['legacy_outcome_withheld_count'])+'. Partial evidence, attribution unresolved: '+str(bc['attribution_unresolved_partial_count'])+'. Fully resolved people (both items known on a proven clean crop): '+str(bc['fully_resolved_person_count'])+'.',small)
        line('Attempted and emitted are not resolved. Not the 10+ person qualification.',small)
    y+=16
    max_w,max_h=width-144,650
    scale=min(max_w/overlay.width,max_h/overlay.height,8)
    shown=overlay.resize((max(1,round(overlay.width*scale)),max(1,round(overlay.height*scale))),Image.Resampling.LANCZOS)
    page.paste(shown,((width-shown.width)//2,y));y+=shown.height+18
    line('Mask edges: person teal, helmet purple, vest blue; operator zones amber.',small)
    line('PPE mask overlap alone does not establish gear is worn.',small)
    line('Image is an operator-reviewed private preview, not validated shareable evidence.',small)
    rule_review=report.get('configured_rule_review',{})
    line('Rule review: '+rule_review.get('status','not_configured').replace('_',' '))
    line('Location uses current operator contact claims, not automatic ground contact.',small)
    for person in report['persons']:
        if y+250>height-110:new_page()  # keep each person block on one page
        y+=16
        line('Person '+person['person_id'])
        line('Protective hardhat worn: '+person['report_display_helmet']+' | Reflective vest worn: '+person['report_display_vest'])
        line('Hardhat observation is separate from a welding face shield and site-specific requirements.',small)
        line('Evidence: '+person['status'].replace('_',' '),small)
        if person.get('ppe_assessed')is True and report.get('wide_scene'):line('Provider PPE observation attempted on a crop (unvalidated)',small)
        if person.get('geometry_status')=='unverified_box_only':line('GEOMETRY UNVERIFIED: raw box only, no mask, no contact or zone use',small)
        pb=person.get('ppe_basis')
        if pb and person.get('ppe_assessed')is True:
            if pb['crop_basis']in('overlapped_crop','isolated_crop','crop_rule_ineligible'):line('PARTIAL EVIDENCE ('+pb['crop_basis'].replace('_',' ')+(': '+', '.join(r.replace('_',' ')for r in pb.get('crop_rule_reasons',[]))if pb.get('crop_rule_reasons')else'')+'): target attribution unresolved, no present/absent outcome shown',small)
            elif pb['crop_basis']=='clean_crop':line('Crop passed the existing no-other-person rule; association not verified',small)
            else:line('Crop basis NOT recorded (legacy path): raw reading kept, no present/absent outcome shown, needs review',small)
        if person.get('ppe_assessed')is False:line('PPE NOT ASSESSED: '+person.get('ppe_evidence_status','unknown').replace('_',' '),small)
        zr=report.get('zone_review')or{}
        if zr.get('zone_snapshot'):
            zrow=next((z for z in zr.get('persons',[])if z['person_id']==person['person_id']),None)
            if zrow:
                st=zrow['status']
                if st=='operator_contact_geometry':line('Operator zone (manual contact claim, not automatic): '+(', '.join(zrow.get('zone_ids')or[])or'outside all drawn zones'),small)
                elif st=='boundary_needs_review':line('Operator zone: on a zone boundary, needs review ('+', '.join(zrow.get('boundary_zone_ids',[]))+')',small)
                else:line('Operator zone: none recorded (zones drawn, no manual contact for this person)',small)
        evaluation=next((p for p in rule_review.get('persons',[])if p['person_id']==person['person_id']),None)
        if evaluation:
            for finding in evaluation['findings']:
                if y+110>height-110:new_page()
                line('Rule '+finding['rule_id']+' | Zone '+str(finding['zone_id'])+' | '+finding['status'].replace('_',' '))
                line('Priority: '+str(finding['priority']if finding['priority']is not None else'not configured / needs review')+' | '+finding['reason'].replace('_',' '),small)
            if not evaluation['findings']:line(evaluation['summary'],small)
    commentary=report.get('spatial_explanations',{})
    for attempt in commentary.get('attempts',[]):
        if attempt['state']!='completed':continue
        if y+230>height-110:new_page()
        y+=16;line('Muse commentary - unvalidated, human review required')
        line('Missing auxiliary PPE masks means not supplied, not proof that segmentation or PPE is absent.',small)
        line('Raw model text below is not accepted as accurate.',small)
        review=attempt.get('content_review',{})
        if review.get('flagged_finding_keys'):line('REVIEW FLAG: segmentation references unsupported because auxiliary PPE masks were not supplied.',small)
        for row in attempt['result']['explanations']:
            if y+160>height-110:new_page()
            line('Person '+row['person_id']+' | Rule '+row['rule_id']+' | '+row['status'].replace('_',' '),small)
            line(row['model_commentary'],small)
        line('Deterministic status and priority remain authoritative; commentary cannot change them.',small)
    if page is not None:pages.append(page)
    if len(pages)>32:raise ValueError('Private document page quota exceeded')
    for index,p in enumerate(pages):
        ImageDraw.Draw(p).text((72,height-65),'Private preview | '+str(index+1)+' / '+str(len(pages))+' | Export not approved',fill='#585254',font=small)
    if _pages_only:return pages
    buf=io.BytesIO();pages[0].save(buf,'PDF',save_all=True,append_images=pages[1:],resolution=150.0,title='Vigilens private preview',author='Vigilens')
    pdf=buf.getvalue()
    if len(pdf)>20_000_000:raise ValueError('Private document byte quota exceeded')
    return pdf,hashlib.sha256(pdf).hexdigest()


def render_clip_pdf(samples):
    if not 1<=len(samples)<=8:raise ValueError('Private clip PDF limited to eight reviewed samples')
    pages=[]
    for document,png,label in samples:
        pages.extend(render_private_pdf({**document,'clip_sample_label':label},png,_pages_only=True))
        if len(pages)>32:raise ValueError('Private clip page quota exceeded')
    for index,page in enumerate(pages):
        painter=ImageDraw.Draw(page);painter.rectangle((60,page.height-78,page.width-60,page.height-30),fill='white');painter.text((72,page.height-65),'Private sampled clip | '+str(index+1)+' / '+str(len(pages))+' | Export not approved',fill='#585254',font=ImageFont.load_default(size=18))
    buf=io.BytesIO();pages[0].save(buf,'PDF',save_all=True,append_images=pages[1:],resolution=150.0,title='Vigilens sampled clip private preview')
    pdf=buf.getvalue()
    if len(pdf)>20_000_000:raise ValueError('Private clip PDF byte quota exceeded')
    return pdf,hashlib.sha256(pdf).hexdigest()
