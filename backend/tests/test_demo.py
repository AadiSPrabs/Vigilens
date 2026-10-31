from demo_offline import run_demo

def test_runnable_demo_no_real_analysis_or_export():
 x=run_demo();assert x['http_fixture_job']['source']=='fixture'
 assert not x['http_fixture_job']['duplicate_created_new_execution']
 assert x['offline_pipeline']['assessment_status']=='needs_human_review'
 assert not x['evidence_export_allowed'] and 'no model call' in x['notice']
