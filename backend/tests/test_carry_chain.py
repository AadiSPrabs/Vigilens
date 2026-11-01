import json,hashlib,os,sqlite3,asyncio
from decimal import Decimal
import pytest
from PIL import Image
import fresh_review.carry_chain as cc
from fresh_review.carry_chain import verify_chain,load_manifest,sha
from test_wide_sequential import seq,run
from fresh_review.wide_sequential import SequentialWidePipeline
PRES='b'*64;H=['1'*64,'2'*64]
def settled(tmp,**over):
 d={'kind':'supplemental_accounting_carry_not_recovered_original_journal','provider_calls_total':19,'combined_listed_usd':'0.03969310','conservative_booked_usd':'0.05457125','aggregate_cap_usd':'5','blocked_source_digests':[PRES,'c'*64],'historical_unresolved_reservations':[],'new_unresolved_reservations':[]}
 d.update(over);raw=json.dumps(d).encode();p=tmp/'c.json';p.write_bytes(raw);p.chmod(0o600);return p,sha(raw),d
def manifest(tmp,csha,proof=None,**over):
 pf={'qualification.sqlite':sha(b'proof')}
 m={'format':cc.FORMAT,'carry_sha256':csha,'carry_kind':'supplemental_accounting_carry_not_recovered_original_journal','provider_calls_total':19,'combined_listed_usd':'0.03969310','conservative_booked_usd':'0.05457125','history_chain':H,'preserved':[{'source_digest':PRES,'files':proof or pf,'listed_usd':'0.0025','counted_in_carry':True}]}
 m.update(over);raw=json.dumps(m).encode();p=tmp/'m.json';p.write_bytes(raw);p.chmod(0o600);return load_manifest(p,sha(raw))
def test_valid_chain(tmp_path):
 _,cs,c=settled(tmp_path);m=manifest(tmp_path,cs);assert verify_chain(m,cs,c)
def test_proof_dir_checked_and_tamper_or_missing_refused(tmp_path):
 _,cs,c=settled(tmp_path);m=manifest(tmp_path,cs);d=tmp_path/'proof';d.mkdir()
 with pytest.raises(ValueError,match='proof'):verify_chain(m,cs,c,proof_dir=str(d))
 (d/'qualification.sqlite').write_bytes(b'proof');assert verify_chain(m,cs,c,proof_dir=str(d))
 (d/'qualification.sqlite').write_bytes(b'tampered')
 with pytest.raises(ValueError,match='proof'):verify_chain(m,cs,c,proof_dir=str(d))
def test_wrong_or_changed_carry_refused(tmp_path):
 _,cs,c=settled(tmp_path);m=manifest(tmp_path,cs)
 with pytest.raises(ValueError):verify_chain(m,'f'*64,c)
 for over in [{'provider_calls_total':18},{'conservative_booked_usd':'0'},{'conservative_booked_usd':'0.06'},{'combined_listed_usd':'0.0'}]:
  with pytest.raises(ValueError):verify_chain(m,cs,{**c,**over})
def test_blocked_set_must_keep_preserved_source(tmp_path):
 _,cs,c=settled(tmp_path);m=manifest(tmp_path,cs)
 with pytest.raises(ValueError,match='blocked'):verify_chain(m,cs,{**c,'blocked_source_digests':['c'*64]})
def test_hidden_or_unresolved_holds_refused(tmp_path):
 _,cs,c=settled(tmp_path);m=manifest(tmp_path,cs)
 for k in['historical_unresolved_reservations','new_unresolved_reservations']:
  with pytest.raises(ValueError,match='holds'):verify_chain(m,cs,{**c,k:['x']})
def test_duplicate_history_and_double_count_refused(tmp_path):
 _,cs,c=settled(tmp_path);m=manifest(tmp_path,cs)
 with pytest.raises(ValueError,match='double count'):verify_chain(m,cs,c,journal_sources=[PRES])
 with pytest.raises(ValueError):manifest(tmp_path,cs,history_chain=['1'*64,'1'*64])
 with pytest.raises(ValueError):manifest(tmp_path,cs,preserved=[{'source_digest':PRES,'files':{'a':'1'*64},'listed_usd':'0.0025','counted_in_carry':True}]*2)
 with pytest.raises(ValueError):manifest(tmp_path,cs,preserved=[{'source_digest':PRES,'files':{'a':'1'*64},'listed_usd':'0.0025','counted_in_carry':False}])
def test_manifest_tamper_and_permissions(tmp_path):
 _,cs,c=settled(tmp_path);manifest(tmp_path,cs);p=tmp_path/'m.json'
 with pytest.raises(ValueError,match='changed'):load_manifest(p,'0'*64)
 p.chmod(0o644)
 with pytest.raises(ValueError,match='private'):load_manifest(p,sha(p.read_bytes()))
def test_pipeline_runs_against_settled_carry_with_chain_and_refuses_double_count_or_change(tmp_path,monkeypatch):
 p,raw,f,calls=seq(tmp_path,monkeypatch,booked='0.05457125')
 d=json.loads(p.carry_path.read_text());d.update({'kind':'supplemental_accounting_carry_not_recovered_original_journal','provider_calls_total':19,'combined_listed_usd':'0.03969310','historical_unresolved_reservations':[],'blocked_source_digests':[PRES]})
 p.carry_path.write_text(json.dumps(d));p.carry_sha=sha(p.carry_path.read_bytes())
 p.chain_manifest=manifest(tmp_path,p.carry_sha)
 out=run(p,raw);assert out['state']=='completed'and len(calls)==13
 assert Decimal(p.carry()['conservative_booked_usd'])==Decimal('0.05457125')
 # a later carry change is refused by the manifest pin even if the carry file itself is consistently re-hashed
 d['conservative_booked_usd']='0.01';p.carry_path.write_text(json.dumps(d));p.carry_sha=sha(p.carry_path.read_bytes())
 with pytest.raises(ValueError):p.carry()
