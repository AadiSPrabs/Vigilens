"""Cross-stage review signals only. Segmentation is not a worn-PPE classifier.
An empty mask and 'present' observation motivate review, never force absence or
rewrite a known original observation. No automatic new calls or budget authority.
"""
def review_signals(persons,segmentations):
    rows=[]
    by_concept={}
    for stage in segmentations:
        concept=stage['concept']
        if concept not in ('helmet','vest')or concept in by_concept:raise ValueError('One exact segmentation per PPE concept required')
        by_concept[concept]=stage
    for p in persons:
        for concept,stage in by_concept.items():
            if p[concept]not in ('present','absent','unknown'):raise ValueError('Original PPE observation required')
            if p[concept]=='present'and not stage['objects']:
                rows.append({'person_id':p['id'],'item':concept,'status':'needs_human_review','reason':'observed_present_but_no_auxiliary_mask','original_observation':p[concept],'observation_changed':False,'segmentation_absence_proven':False,'automatic_recheck_authorized':False})
    return {'status':'cross_stage_signals_not_ppe_verdict','signals':rows,'automatic_dispatch':False,'original_observations_unchanged':True}
