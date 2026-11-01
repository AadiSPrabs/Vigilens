# Native Windows support - validation requirements (wired, Windows-tested only via preflight)

fresh_review/platform_private.py is now WIRED at every private-file call site. The POSIX
branch keeps today's semantics exactly (the full suite passes unchanged on Linux). The
Windows branch has still never executed on a real Windows machine: run
backend/windows_preflight.py on the target Windows machine first - it exercises W2/W4
mechanically plus a synthetic end-to-end smoke (part of W5) and prints paste-back output.

## What the layer must preserve
- POSIX behavior is byte-for-byte today's semantics (mode-bit checks, O_NOFOLLOW,
  per-site mask differences such as 0o022 vs 0o077); the existing suite (754 tests,
  including the frozen app-v3 lineage's 746) passes unchanged on Linux after wiring.
- No fallback that silently follows links/reparse points. os.open follows links before any
  check, so the Windows no-follow does NOT use os.open: every path component, including
  the final one, is opened with CreateFileW + FILE_FLAG_OPEN_REPARSE_POINT (typed ctypes
  signatures, 64-bit HANDLEs, msvcrt.open_osfhandle for the returned fd) and refused when
  the OPEN HANDLE shows FILE_ATTRIBUTE_REPARSE_POINT. Residual: a component swapped after
  our walk and before the caller reuses the path; the returned handle is opened and
  checked by us.
- The DACL check is strict: icacls nonzero exit, any unrecognized line, any DENY ace, or
  any principal not EXACTLY the current user (live SID via whoami /user, or exact
  DOMAIN\name), NT AUTHORITY\SYSTEM or BUILTIN\Administrators refuses. No tail or
  startswith matching, no skipped lines. Parser and policy are unit-tested offline.

## Validation items (run on real Windows 10/11, Python 3.10)
- W1 Wiring: DONE. All privacy call sites (dev_install.py key-file check AND the
  config/token reads in load_service, which go through the same privacy-checked open,
  fresh_review/approvals.py 0o022 semantics, carry_chain.py follow=True,
  pipeline.py journal/artifact/private-bytes/reply paths, runtime.py data-dir,
  private_sqlite.py require_private_file) route through platform_private
  path_private/open_private. Linux regression: full suite still passes (754). Remaining:
  run the suite once on Windows itself.
- W2 DACL semantics: a file explicitly restricted (icacls /inheritance:r /grant:r
  %USERNAME%:F) must be ACCEPTED; an added Everyone grant must be REFUSED; after removal,
  accepted again. windows_preflight.py runs exactly this with checked exit codes; also
  confirm once with a second real user grant (User2:R) manually.
- W3 Locale: on a non-English Windows, icacls output is localized; the parser must FAIL
  CLOSED (refuse), never accept. If it accepts localized output, the parser is wrong;
  switch to GetNamedSecurityInfo before shipping.
- W4 Reparse points: create a directory junction (mklink /J) and a file symlink
  (mklink) pointing at the key file; open_nofollow_windows_proposed must REFUSE both.
  A plain file must open (and its fd is usable). windows_preflight.py covers the junction
  case mechanically (refusal path and fd cleanup); the file-symlink case stays manual.
  W3 (localized icacls) also stays manual: run once on a non-English Windows.
- W5 Setup flow: dev_install.py setup + approve + run_dev.py + a synthetic browser run,
  all on native Windows, paths under a normal user directory (C:\Users\<you>\...).
  windows_preflight.py covers the offline setup + governed-service load smoke and proves
  it executes; the browser run stays manual.

## Test-execution routes investigated
- This environment: Linux-only boxes and a hosted browser; no Windows execution possible.
- GitHub Actions windows-latest would run W1/W4 mechanically (W2/W3 need interactive ACL
  and locale setups). A workflow can be added when a repo push is authorized; none is.
- WSL2 is NOT a validation route for this layer: WSL presents Linux semantics, so it tests
  the POSIX branch, not the Windows one.
