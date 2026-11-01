"""Local file permission preflight, not encryption or hostile-host isolation."""
import os
from fresh_review.platform_private import open_private

def require_private_file(path):
    # Never follow a file symlink/reparse point. A trusted private parent directory is
    # still required; no-follow does not defend concurrent directory replacement.
    # POSIX: O_NOFOLLOW + mode check. Windows: handle reparse refusal + DACL check.
    fd=open_private(str(path),os.O_CREAT|os.O_RDWR)
    os.close(fd)
