"""Local file permission preflight, not encryption or hostile-host isolation."""
import os
import stat

def require_private_file(path):
    # Never follow a file symlink. A trusted private parent directory is still
    # required; O_NOFOLLOW does not defend concurrent directory replacement.
    fd=os.open(str(path),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode):raise ValueError('Local journal must be a regular file')
        if s.st_mode&0o077:raise ValueError('Local journal must have private permissions; back up and restrict it explicitly')
    finally:os.close(fd)
