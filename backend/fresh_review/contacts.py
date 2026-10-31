"""Append-only local contact history. Browser nonce binds claims,not authenticated human identity."""
import hashlib,json,time
TTL=1800
CAP=128
class ContactStore:
 def __init__(self,service):self.service=service
 def connect(self):
  c=self.service.connect();c.execute('CREATE TABLE IF NOT EXISTS contact_events(id INTEGER PRIMARY KEY,source TEXT,result_sha TEXT,person TEXT,owner_hash TEXT,claim TEXT,at REAL)');return c
 def latest(self,source,result_sha,owner):
  c=self.connect()
  try:rows=c.execute('SELECT person,claim,at,id FROM contact_events WHERE source=? AND result_sha=? AND owner_hash=? ORDER BY id',(source,result_sha,hashlib.sha256(owner.encode()).hexdigest())).fetchall()
  finally:c.close()
  latest={person:{'claim':json.loads(claim),'at':at,'event_id':event}for person,claim,at,event in rows}
  return {k:v for k,v in latest.items()if time.time()-v['at']<=TTL}
 def append(self,source,result_sha,person,owner,claim):
  existing=self.latest(source,result_sha,owner).get(person)
  if existing and existing['claim']==claim:return existing
  c=self.connect()
  try:
   c.execute('BEGIN IMMEDIATE')
   if c.execute('SELECT count(*) FROM contact_events').fetchone()[0]>=CAP:raise ValueError('Contact history capacity reached; retain audit history')
   at=time.time();cur=c.execute('INSERT INTO contact_events(source,result_sha,person,owner_hash,claim,at) VALUES(?,?,?,?,?,?)',(source,result_sha,person,hashlib.sha256(owner.encode()).hexdigest(),json.dumps(claim,sort_keys=True),at));c.commit()
   return {'claim':claim,'at':at,'event_id':cur.lastrowid}
  finally:c.close()
