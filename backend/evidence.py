"""Bounded private local synthetic-asset storage. Not real evidence release.
No HTTP route, URL, auth identity provider, face detector or public export exists.
"""
import hashlib
import io
import os
import sqlite3
import uuid
from contextlib import contextmanager
from PIL import Image
from core import fail,decode_image
from pipeline import Frame

class SyntheticEvidenceStore:
    def __init__(self,path,max_asset_bytes=2_000_000,max_total_bytes=8_000_000,max_records=256):
        if any(type(v) is not int or v<=0 for v in (max_asset_bytes,max_total_bytes,max_records)):raise ValueError('Positive test storage limits required')
        self.path=str(path);self.max_asset=max_asset_bytes;self.max_total=max_total_bytes;self.max_records=max_records
        # Created with private mode before sqlite opens it. Existing files must be private.
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            if os.fstat(fd).st_mode&0o077:raise ValueError('Local store must not be group/world accessible')
        finally:os.close(fd)
        with self.tx() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS synthetic_assets(asset_id TEXT PRIMARY KEY,scope TEXT NOT NULL,audit_id TEXT NOT NULL,frame_id TEXT NOT NULL,digest TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,payload BLOB,state TEXT NOT NULL,UNIQUE(scope,audit_id,frame_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS synthetic_asset_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,asset_id TEXT NOT NULL,action TEXT NOT NULL)''')
    @contextmanager
    def tx(self):
        c=sqlite3.connect(self.path,timeout=10,isolation_level=None);c.row_factory=sqlite3.Row;c.execute('PRAGMA secure_delete=ON');c.execute('PRAGMA synchronous=FULL');c.execute('BEGIN IMMEDIATE')
        try:yield c;c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()
    def put(self,scope,audit_id,frame,image,*,source):
        if source!='synthetic':fail('REAL_EVIDENCE_DISABLED','Real evidence storage/release is not enabled.',503)
        if not all(isinstance(v,str) and 1<=len(v)<=128 for v in (scope,audit_id)):fail('INVALID_ASSET_IDENTITY','Explicit bounded local identity required.')
        frame.validate()
        if not isinstance(image,Image.Image) or image.size!=(frame.width,frame.height):fail('EVIDENCE_FRAME_MISMATCH','Synthetic image frame mismatch.')
        # Re-encode pixels only; no input EXIF, info, filenames or metadata copied.
        clean=Image.frombytes('RGB',image.size,image.convert('RGB').tobytes());data=io.BytesIO();clean.save(data,'PNG');payload=data.getvalue()
        if len(payload)>self.max_asset:fail('ASSET_TOO_LARGE','Synthetic asset exceeds local size limit.',413)
        digest=decode_image(payload,'image/png').digest
        with self.tx() as c:
            old=c.execute('SELECT * FROM synthetic_assets WHERE scope=? AND audit_id=? AND frame_id=?',(scope,audit_id,frame.identity)).fetchone()
            if old:
                if old['digest']!=digest:fail('EVIDENCE_IDENTITY_CONFLICT','Identity already binds different pixels.',409)
                # Tombstones remain deleted; caller cannot reanimate a removed asset.
                return self._public(old)
            n,total=c.execute("SELECT COUNT(*),COALESCE(SUM(LENGTH(payload)),0) FROM synthetic_assets").fetchone()
            if n>=self.max_records or total+len(payload)>self.max_total:fail('LOCAL_STORAGE_FULL','Local synthetic storage bound reached.',503)
            aid='synthetic-'+uuid.uuid4().hex
            c.execute('INSERT INTO synthetic_assets VALUES(?,?,?,?,?,?,?,?,?)',(aid,scope,audit_id,frame.identity,digest,frame.width,frame.height,payload,'stored'))
            c.execute('INSERT INTO synthetic_asset_events(asset_id,action) VALUES(?,?)',(aid,'synthetic_stored_no_release'))
            return self._public(c.execute('SELECT * FROM synthetic_assets WHERE asset_id=?',(aid,)).fetchone())
    def _row(self,c,aid,scope):
        r=c.execute('SELECT * FROM synthetic_assets WHERE asset_id=? AND scope=?',(aid,scope)).fetchone()
        if r is None:raise KeyError(aid)
        return r
    def _public(self,row):
        return {k:row[k] for k in ('asset_id','audit_id','frame_id','digest','width','height','state')}|{'source':'synthetic','evidence_export_allowed':False,'evidence_status':'unavailable'}
    def metadata(self,aid,scope):
        with self.tx() as c:return self._public(self._row(c,aid,scope))
    def read_for_local_test(self,aid,scope):
        with self.tx() as c:
            r=self._row(c,aid,scope)
            if r['state']!='stored':raise KeyError(aid)
            c.execute('INSERT INTO synthetic_asset_events(asset_id,action) VALUES(?,?)',(aid,'local_test_read_not_export'))
            return bytes(r['payload'])
    def delete(self,aid,scope):
        with self.tx() as c:
            r=self._row(c,aid,scope)
            if r['state']=='deleted':return False
            c.execute("UPDATE synthetic_assets SET payload=NULL,state='deleted' WHERE asset_id=?",(aid,))
            c.execute('INSERT INTO synthetic_asset_events(asset_id,action) VALUES(?,?)',(aid,'synthetic_payload_deleted_tombstone_retained'))
            return True
    def events(self,aid,scope):
        with self.tx() as c:
            self._row(c,aid,scope)
            return [dict(r) for r in c.execute('SELECT * FROM synthetic_asset_events WHERE asset_id=? ORDER BY seq',(aid,))]
