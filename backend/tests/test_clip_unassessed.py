from fresh_review.clip_audit import summary,unassessed
def job(w=None,persons=()):return {'state':'completed','result':{'wide_scene':w,'persons':list(persons)}}
def test_completed_wide_frame_with_withheld_ppe_is_flagged_not_assessed():
 clip={'source_clip_sha256':'x','duration_seconds':1,'frames':[1]}
 f=[{'sample_index':0,'image_job':job({'all_detected_people_assessed':False})},{'sample_index':1,'image_job':job({'all_detected_people_assessed':True})},{'sample_index':2,'image_job':job(None,[{'ppe_assessed':False}])},{'sample_index':3,'image_job':job(None,[{}])}]
 s=summary(clip,f,0,'sampled_image_jobs_completed_not_clip_safety_clearance')
 assert s['frames_with_unassessed_people']==[0,2] and s['completed_state_is_execution_terminal_not_assessment_complete'] is True
