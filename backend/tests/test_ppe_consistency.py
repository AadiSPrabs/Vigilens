from fresh_review.ppe_consistency import review_signals

def test_actual_failure_shape_empty_mask_does_not_rewrite_present():
 persons=[{'id':'0','helmet':'present','vest':'present'}]
 r=review_signals(persons,[{'concept':'helmet','objects':[{'object_id':'0'}]},{'concept':'vest','objects':[]}])
 assert len(r['signals'])==1 and r['signals'][0]['item']=='vest'
 assert r['signals'][0]['original_observation']=='present'and not r['signals'][0]['segmentation_absence_proven']and not r['automatic_dispatch']
 assert persons[0]['vest']=='present'

def test_empty_detection_does_not_prove_absence_or_create_unneeded_signal():
 assert review_signals([{'id':'0','helmet':'absent','vest':'unknown'}],[{'concept':'vest','objects':[]}])['signals']==[]
