import os,sqlite3
import pytest
from ledger import Ledger
from usage import UsageLedger

@pytest.mark.parametrize('cls',[Ledger,UsageLedger])
def test_new_journal_private_under_permissive_umask(tmp_path,cls):
 p=tmp_path/'j';old=os.umask(0o022)
 try:cls(p)
 finally:os.umask(old)
 assert os.stat(p).st_mode&0o077==0
@pytest.mark.parametrize('cls',[Ledger,UsageLedger])
def test_journal_file_symlink_refused(tmp_path,cls):
 p=tmp_path/'j';p.symlink_to(tmp_path/'target')
 with pytest.raises(OSError):cls(p)
 assert not (tmp_path/'target').exists()
@pytest.mark.parametrize('cls',[Ledger,UsageLedger])
def test_existing_broad_permissions_require_explicit_fix(tmp_path,cls):
 p=tmp_path/'j';p.touch();p.chmod(0o644)
 with pytest.raises(ValueError):cls(p)
 assert p.stat().st_mode&0o777==0o644
 p.chmod(0o600);cls(p)

def test_sqlite_wal_sidecars_private_while_open(tmp_path):
 p=tmp_path/'j';l=Ledger(p);c=sqlite3.connect(p);c.execute('PRAGMA journal_mode=WAL');c.execute('BEGIN IMMEDIATE');c.execute("INSERT INTO events(job_id,occurred,new_state,reason) VALUES('test',1,'queued','local')");c.commit()
 try:
  for name in (str(p)+'-wal',str(p)+'-shm'):
   if os.path.exists(name):assert os.stat(name).st_mode&0o077==0
 finally:c.close()
