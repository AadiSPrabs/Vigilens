"""Continuity check for a next-run journal bound to a settled historical accounting carry.

The carry holds the historical aggregate and blocked-source set. Preserved journal rows (immutable proof) stay outside
the live journal because the carry already counts them; counting them again or reading them against a carry that blocks
their source would double count or fail closed. This module proves that division stays continuous. It is not authority
to dispatch: it only refuses when continuity cannot be shown.
"""
import hashlib,json,os
from decimal import Decimal as D
FORMAT='vigilens.carry-chain.v1'
KEYS={'format','carry_sha256','carry_kind','provider_calls_total','combined_listed_usd','conservative_booked_usd','history_chain','preserved'}
PKEYS={'source_digest','files','listed_usd','counted_in_carry'}
def sha(b):return hashlib.sha256(b).hexdigest()
def hexok(v):return isinstance(v,str)and len(v)==64 and all(x in '0123456789abcdef' for x in v)
def load_manifest(path,expected_sha):
 st=os.stat(path)
 if st.st_mode&0o077:raise ValueError('Chain manifest must be private')
 raw=open(path,'rb').read()
 if sha(raw)!=expected_sha:raise ValueError('Chain manifest changed')
 m=json.loads(raw)
 if not isinstance(m,dict)or set(m)!=KEYS or m['format']!=FORMAT:raise ValueError('Chain manifest shape invalid')
 if not hexok(m['carry_sha256'])or not isinstance(m['history_chain'],list)or not m['history_chain']or any(not hexok(h)for h in m['history_chain'])or len(set(m['history_chain']))!=len(m['history_chain']):raise ValueError('History chain invalid or duplicated')
 if not isinstance(m['preserved'],list)or not m['preserved']:raise ValueError('Preserved proof list required')
 seen=set()
 for p in m['preserved']:
  if not isinstance(p,dict)or set(p)!=PKEYS or not hexok(p['source_digest'])or p['source_digest']in seen or p['counted_in_carry']is not True or not isinstance(p['files'],dict)or not p['files']or any(not hexok(v)for v in p['files'].values()):raise ValueError('Preserved proof entry invalid or duplicated')
  seen.add(p['source_digest']);D(p['listed_usd'])
 return m
def verify_chain(manifest,carry_sha,carry,*,journal_sources=(),proof_dir=None):
 """carry is the already-validated carry dict; journal_sources are sources with rows in the live journal."""
 m=manifest
 if m['carry_sha256']!=carry_sha:raise ValueError('Carry is not the manifest-pinned settled carry')
 if m['history_chain'][-1]==carry_sha or carry_sha in m['history_chain']:raise ValueError('Chain must list only prior closeouts')
 if carry.get('kind')!=m['carry_kind']or carry.get('provider_calls_total')!=m['provider_calls_total']:raise ValueError('Carry history differs from manifest')
 if D(carry['conservative_booked_usd'])!=D(m['conservative_booked_usd'])or D(carry.get('combined_listed_usd','x')if carry.get('combined_listed_usd')else 'NaN')!=D(m['combined_listed_usd']):raise ValueError('Carry accounting differs from manifest')
 if carry.get('historical_unresolved_reservations')!=[]or carry.get('new_unresolved_reservations',[])!=[]:raise ValueError('Unresolved historical holds remain')
 if D(carry['conservative_booked_usd'])<D(carry['combined_listed_usd']):raise ValueError('Booked below listed spend')
 blocked=set(carry['blocked_source_digests'])
 for p in m['preserved']:
  if p['source_digest']not in blocked:raise ValueError('Preserved source missing from blocked set')
 pres={p['source_digest']for p in m['preserved']}
 dup=pres&set(journal_sources)
 if dup:raise ValueError('Preserved historical row duplicated in live journal (would double count)')
 if proof_dir is not None:
  for p in m['preserved']:
   for name,want in p['files'].items():
    f=os.path.join(proof_dir,os.path.basename(name))
    if not os.path.isfile(f)or sha(open(f,'rb').read())!=want:raise ValueError('Preserved proof missing or changed')
 return True
