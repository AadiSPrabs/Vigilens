"""Native-Windows platform layer for the backend's local-privacy checks.

STATUS: the POSIX branch preserves today's exact semantics and is covered by the normal
suite. The Windows branch is design-reviewed and unit-tested only where offline-testing is
possible (the DACL parser and principal policy); its Win32 handle code has NEVER EXECUTED
ON WINDOWS and is gated behind windows_preflight.py on the target machine. No code path
selects it silently on other platforms, and nothing here weakens a POSIX check.

Windows design (fixed per source review):
- No-follow: Python's os.open follows links before any handle check, so checking target
  attributes after a plain open CANNOT establish no-follow. Instead every path component,
  including the final one, is opened with CreateFileW + FILE_FLAG_OPEN_REPARSE_POINT
  (directories also FILE_FLAG_BACKUP_SEMANTICS) and the OPEN HANDLE is checked for
  FILE_ATTRIBUTE_REPARSE_POINT; a reparse point is refused, never followed. Handles use
  msvcrt/typed ctypes signatures (64-bit HANDLE safe); there is no _get_osfhandle misuse.
  Residual, stated exactly: each parent component is opened, checked, and CLOSED before
  descending, so a component swapped between those steps inside the walk is not detected;
  only the FINAL handle, which we open and check ourselves and then return, is held
  continuously. Callers must not reopen the path and expect these guarantees to carry.
- Byte integrity: the CRT fd is always opened with O_BINARY; Windows text-mode translation
  would corrupt journal/artifact bytes. Flag mapping is explicit: only O_RDONLY/O_WRONLY/
  O_RDWR/O_CREAT/O_EXCL/O_APPEND are supported; anything else (e.g. O_TRUNC, O_TEXT) is
  REJECTED, never silently mis-mapped.
- Scope: developer self-issued approval metadata in dev_install is a local test
  authorization only; it is never an owner or provider grant.
- DACL privacy: `icacls` output is parsed STRICTLY - nonzero exit status, any
  unrecognized line, any DENY ace, or any principal not exactly the current user (by SID
  resolved via `whoami /user`, or exact DOMAIN\name), NT AUTHORITY\SYSTEM, or
  BUILTIN\Administrators refuses the file. No tail/startswith matching, no skipped lines.
  Locale-mangled output fails closed (validation item W3 double-checks on a real machine).
"""
import os
import re
import stat
import subprocess

IS_WINDOWS = os.name == 'nt'


def is_private_posix(path):
    """Exact current semantics: regular file/dir whose mode grants nothing to group/other."""
    s = os.stat(path, follow_symlinks=False)
    if stat.S_ISLNK(s.st_mode):
        return False
    return (s.st_mode & 0o077) == 0


_ICACLS_ACE = re.compile(r'^\s*(?P<principal>.+?):(?P<groups>(?:\([^)]*\))+)\s*$')
_ICACLS_SUMMARY = re.compile(r'^\s*Successfully processed \d+ files; Failed processing 0 files')


class IcaclsParseError(ValueError):
    """Any output shape we cannot account for line-by-line; callers must fail closed."""


def parse_icacls(output, path=None):
    """Strict parser for `icacls <file>` output. Returns [(principal, rights-groups)].
    Raises IcaclsParseError on ANY line that is not: the path-echo prefix, an ACE line, or
    the exact success summary. Pure function; unit-tested with canned output."""
    lines = [ln.rstrip() for ln in output.splitlines() if ln.strip()]
    aces = []
    saw_summary = False
    for i, line in enumerate(lines):
        if _ICACLS_SUMMARY.match(line):
            saw_summary = True
            continue
        if i == 0 and path is not None and line.startswith(str(path)):
            line = line[len(str(path)):].strip()
            if not line:
                raise IcaclsParseError('path echo with no ACE on first line')
        m = _ICACLS_ACE.match(line)
        if not m:
            raise IcaclsParseError('unrecognized icacls line: %r' % line)
        aces.append((m.group('principal').strip(), m.group('groups')))
    if not saw_summary:
        raise IcaclsParseError('missing icacls success summary')
    if not aces:
        raise IcaclsParseError('no ACEs')
    return aces


def _current_user_principals():
    """Exact allowed self-identities: the user's SID and DOMAIN\\name, resolved live.
    Returns a lowercase set. Raises ValueError (fail closed) when unresolvable."""
    if not IS_WINDOWS:
        raise ValueError('Windows principal resolution on non-Windows')
    r = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError('whoami /user failed; refusing')
    # csv row: "DOMAIN\name","SID"
    row = r.stdout.strip().strip('"').split('","')
    if len(row) != 2 or not row[1].upper().startswith('S-1-'):
        raise ValueError('unexpected whoami output; refusing')
    return {row[0].lower(), row[1].lower()}


_ALLOWED_FIXED = ('nt authority\\system', 'builtin\\administrators')


def _dacl_private(aces, allowed_self):
    """True only when every ACE is an allow-ACE for an exactly-matched allowed principal."""
    for principal, rights in aces:
        if '(DENY)' in rights.upper():
            return False
        p = principal.lower()
        if p in allowed_self or p in _ALLOWED_FIXED:
            continue
        return False
    return True


def is_private_windows_proposed(path, icacls_output=None, icacls_returncode=0, allowed_self=None):
    """Windows DACL privacy check. NEVER EXECUTED ON WINDOWS in this package's tests; the
    parser/policy parts are unit-tested offline via the injected-output form.
    Refuses (fail closed) on: icacls nonzero exit, unparseable/localized output, DENY aces,
    or any grant to a principal other than the current user (SID or exact DOMAIN\\name),
    NT AUTHORITY\\SYSTEM, BUILTIN\\Administrators."""
    try:
        allowed = set(allowed_self) if allowed_self is not None else _current_user_principals()
    except ValueError:
        return False
    if icacls_output is None:
        r = subprocess.run(['icacls', str(path)], capture_output=True, text=True)
        if r.returncode != 0:
            return False
        icacls_output = r.stdout
    elif icacls_returncode != 0:
        return False
    try:
        aces = parse_icacls(icacls_output, path=path)
    except IcaclsParseError:
        return False
    return _dacl_private(aces, allowed)


def open_nofollow_posix(path, flags):
    return os.open(path, flags | os.O_NOFOLLOW, 0o600)


_O_BINARY = getattr(os, 'O_BINARY', 0)  # 0 on POSIX; real on Windows
_SUPPORTED_OPEN_BITS = os.O_RDONLY | os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_APPEND


def win32_access_and_disposition(flags):
    # Pure mapping, unit-tested offline. Returns (access_mask, creation_disposition).
    # Raises ValueError on any flag bit outside the supported set - never silently wrong.
    if flags & ~_SUPPORTED_OPEN_BITS:
        raise ValueError('unsupported open flags 0x%x for the governed private-file open' % (flags & ~_SUPPORTED_OPEN_BITS))
    access = 0x80000000  # GENERIC_READ always (privacy check + callers read)
    if flags & (os.O_RDWR | os.O_WRONLY | os.O_CREAT | os.O_APPEND):
        access |= 0x40000000  # GENERIC_WRITE
    if flags & os.O_EXCL:
        disp = 1  # CREATE_NEW
    elif flags & os.O_CREAT:
        disp = 4  # OPEN_ALWAYS
    else:
        disp = 3  # OPEN_EXISTING
    return access, disp


def crt_oflags(flags):
    # Pure CRT flag mapping for msvcrt.open_osfhandle, unit-tested offline.
    # Always includes O_BINARY (byte-exact journal/artifact IO); rejects unsupported bits.
    if flags & ~_SUPPORTED_OPEN_BITS:
        raise ValueError('unsupported open flags 0x%x for the governed private-file open' % (flags & ~_SUPPORTED_OPEN_BITS))
    of = os.O_RDONLY
    if flags & os.O_RDWR:
        of = os.O_RDWR
    elif flags & os.O_WRONLY:
        of = os.O_WRONLY
    if flags & os.O_APPEND:
        of |= os.O_APPEND
    return of | _O_BINARY


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _CreateFileW = _k32.CreateFileW
    _CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _CreateFileW.restype = wintypes.HANDLE  # 64-bit safe, no truncation
    _CloseHandle = _k32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]
    _GetFileInformationByHandle = _k32.GetFileInformationByHandle
    _GetFileInformationByHandle.argtypes = [wintypes.HANDLE, wintypes.LPVOID]

    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _SHARE_ALL = 0x7
    _OPEN_EXISTING = 3
    _OPEN_ALWAYS = 4
    _CREATE_NEW = 1
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _INVALID = wintypes.HANDLE(-1).value

    def _open_component(comp, is_dir):
        """Open one path component WITHOUT following a reparse point; return handle."""
        h = _CreateFileW(str(comp), 0, _SHARE_ALL, None, _OPEN_EXISTING,
                         _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS, None)
        if h == _INVALID or h is None:
            raise ValueError('cannot open path component %r (winerror %d); refusing' % (comp, ctypes.get_last_error()))
        return h

    def _handle_is_reparse(h):
        buf = ctypes.create_string_buffer(52)  # BY_HANDLE_FILE_INFORMATION, 52 bytes
        if not _GetFileInformationByHandle(h, buf):
            raise ValueError('handle identity check failed; refusing')
        attrs = wintypes.DWORD.from_buffer_copy(buf, 0).value
        return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)

    def open_nofollow_windows_proposed(path, flags):
        """Open with no-follow semantics on Windows. NEVER EXECUTED in package tests;
        windows_preflight.py exercises it on the target machine. Every component is opened
        with FILE_FLAG_OPEN_REPARSE_POINT and checked on the handle; a reparse point is
        refused, never followed. Returns an os fd wrapping the final checked handle."""
        import msvcrt
        p = os.path.abspath(str(path))
        drive, rest = os.path.splitdrive(p)
        comps = [c for c in rest.split(os.sep) if c]
        # 1. Refuse a reparse point at any parent component.
        cur = drive + os.sep
        for comp in comps[:-1]:
            cur = os.path.join(cur, comp)
            h = _open_component(cur, is_dir=True)
            try:
                if _handle_is_reparse(h):
                    raise ValueError('reparse point in path component %r; refusing' % cur)
            finally:
                _CloseHandle(h)
        # 2. Final component: map flags, open without following, check, keep.
        access, disp = win32_access_and_disposition(flags)
        h = _CreateFileW(p, access, _SHARE_ALL, None, disp, _FILE_FLAG_OPEN_REPARSE_POINT, None)
        if h == _INVALID or h is None:
            raise ValueError('cannot open %r (winerror %d)' % (p, ctypes.get_last_error()))
        try:
            if _handle_is_reparse(h):
                raise ValueError('reparse point refused (no-follow semantics)')
            fd = msvcrt.open_osfhandle(h, crt_oflags(flags))  # O_BINARY always; fd owns the handle
            return fd
        except BaseException:
            _CloseHandle(h)
            raise
else:
    def open_nofollow_windows_proposed(path, flags):  # pragma: no cover
        raise NotImplementedError('Windows-only')


def is_private(path):
    return is_private_windows_proposed(path) if IS_WINDOWS else is_private_posix(path)


def path_private(path, mask=0o077, follow=True):
    """Privacy predicate with per-site POSIX semantics preserved exactly.
    POSIX: symlink refused when follow=False, then (mode & mask) == 0 on the (possibly
    followed) target - identical to the inline checks this replaces.
    Windows (see module STATUS): mode bits are meaningless; strict DACL check instead.
    Directories are acceptable subjects (the runtime data-dir check uses this)."""
    if IS_WINDOWS:
        return is_private_windows_proposed(path)
    s = os.stat(path, follow_symlinks=follow)
    if not follow and stat.S_ISLNK(s.st_mode):
        return False
    return (s.st_mode & mask) == 0


def open_private(path, flags, mask=0o077):
    """Open with no-follow + privacy semantics on both platforms.
    POSIX: O_NOFOLLOW, then fstat regular-file and mode check - identical to
    private_sqlite.require_private_file / FreshPipeline.save_private today.
    Windows (see module STATUS): component-wise reparse-refusing open, then the strict
    DACL check on the opened path; a file created new inherits the parent DACL, which the
    check then validates (fail closed)."""
    if IS_WINDOWS:
        fd = open_nofollow_windows_proposed(path, flags)
        try:
            if not is_private_windows_proposed(path):
                raise ValueError('File grants access beyond owner/SYSTEM/Administrators; restrict it explicitly')
            return fd
        except BaseException:
            os.close(fd)
            raise
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode):
            raise ValueError('Local journal must be a regular file')
        if s.st_mode & mask:
            raise ValueError('Local journal must have private permissions; back up and restrict it explicitly')
        return fd
    except BaseException:
        os.close(fd)
        raise
