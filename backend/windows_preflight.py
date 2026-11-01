"""One-command native-Windows preflight for the Vigilens backend.

Run on the target Windows machine from this backend folder, after installing Python 3.10:
    python windows_preflight.py
Prints PASS/FAIL lines and a final verdict. Paste the whole output back if anything fails.
It makes no network calls, only creates and removes one temporary directory, and never
touches real keys, journals, approvals, or provider state. On non-Windows systems it runs
the offline setup-and-load smoke only and exits 0 (the POSIX path needs no preflight).

What it covers on Windows (see WINDOWS-VALIDATION.md):
- W2 mechanically: a file whose ACL we explicitly restrict is accepted; adding an Everyone
  grant is refused; removing it is accepted again. Every icacls call's exit code checked.
- W4 mechanically (junction case): a directory junction's target file must be REFUSED by
  the no-follow open; a plain file must open. The symlink case stays manual.
- W5 partially: offline setup + governed-service load smoke (dev_install.create_state +
  load_service, synthetic transport). The browser end-to-end stays manual.
- W3 (localized icacls fail-closed) stays manual on a non-English machine.
"""
import os, sys, platform, tempfile, shutil, subprocess
from pathlib import Path

def line(ok, name, detail=''):
    print('%s %s%s' % ('PASS' if ok else 'FAIL', name, (' - ' + detail) if detail else ''))
    return ok

def restrict_acl_argv(path):
    """icacls argv restricting the file to the current user, with %USERNAME% expanded
    HERE - a literal %USERNAME% in argv never expands without a shell (review finding)."""
    user = os.environ.get('USERNAME')
    if not user:
        raise RuntimeError('USERNAME environment variable unset; cannot build ACL grant')
    return ['icacls', str(path), '/inheritance:r', '/grant:r', user + ':F']


def run(cmd):
    """Subprocess with checked exit code; returns (returncode, combined output)."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

def smoke_setup_and_load(tmp):
    """Offline smoke: create dev state with one approved synthetic image, load the
    governed service (synthetic transport, no server, no network). Returns bool."""
    from PIL import Image
    import dev_install
    img = tmp / 'scene.png'; Image.new('RGB', (64, 64), 'gray').save(img)
    state = tmp / 'state'
    dev_install.create_state(str(state), images=[str(img)], cors_origins=['http://localhost:5173'])
    if not (state / 'dev-config.json').is_file():
        return False
    service, token, origins = dev_install.load_service(str(state / 'dev-config.json'))
    return service is not None and isinstance(token, str) and len(token) >= 32

def main():
    print('preflight on %s / python %s' % (platform.platform(), platform.python_version()))
    ok = line(sys.version_info[:2] == (3, 10), 'python-3.10', platform.python_version())
    tmp = Path(tempfile.mkdtemp(prefix='vigilens-preflight-'))
    try:
        ok &= line(smoke_setup_and_load(tmp), 'setup-and-load-smoke-synthetic-offline')
        if os.name != 'nt':
            print('NOTE: not Windows - DACL/reparse items skipped, POSIX path needs no preflight.')
            print('PREFLIGHT %s (POSIX smoke only)' % ('OK' if ok else 'FAILED'))
            return 0 if ok else 1
        from fresh_review import platform_private as pp

        # W2: DACL accept/refuse on a file whose ACL we set explicitly (not assumed).
        f = tmp / 'key.txt'; f.write_text('dummy')
        rc, out = run(restrict_acl_argv(f))
        ok &= line(rc == 0, 'acl-explicit-restrict-applied', out if rc else '')
        if rc == 0:
            ok &= line(pp.is_private_windows_proposed(f), 'dacl-accepts-restricted')
        rc, out = run(['icacls', str(f), '/grant', 'Everyone:R'])
        ok &= line(rc == 0, 'acl-everyone-grant-applied', out if rc else '')
        if rc == 0:
            ok &= line(not pp.is_private_windows_proposed(f), 'dacl-refuses-everyone-grant')
        rc, out = run(['icacls', str(f), '/remove', 'Everyone'])
        ok &= line(rc == 0, 'acl-everyone-removed', out if rc else '')
        if rc == 0:
            ok &= line(pp.is_private_windows_proposed(f), 'dacl-accepts-after-removal')

        # W4 (junction case): target file through a junction must be refused; fd closed on refusal.
        target = tmp / 'real'; target.mkdir(); (target / 'j.txt').write_text('x')
        plain = tmp / 'plain.txt'; plain.write_text('x')
        junc = tmp / 'junction'
        rc, out = run(['cmd', '/c', 'mklink', '/J', str(junc), str(target)])
        ok &= line(rc == 0, 'junction-created', out if rc else '')
        if rc == 0:
            try:
                fd = pp.open_nofollow_windows_proposed(junc / 'j.txt', os.O_RDONLY)
            except (ValueError, OSError):
                ok &= line(True, 'junction-target-refused')
            else:
                os.close(fd)  # no fd leak on the unexpected-success path
                ok &= line(False, 'junction-target-refused', 'opened through reparse point')
        try:
            fd = pp.open_nofollow_windows_proposed(plain, os.O_RDONLY)
        except (ValueError, OSError) as e:
            ok &= line(False, 'plain-file-opens', str(e))
        else:
            os.close(fd)
            ok &= line(True, 'plain-file-opens')

        # Binary roundtrip through the governed open: all 256 byte values must survive
        # (catches missing O_BINARY - Windows CRT text translation would corrupt them).
        binf = tmp / 'bin.dat'
        payload = bytes(range(256))
        try:
            fd = pp.open_private(binf, os.O_RDWR | os.O_CREAT | os.O_EXCL)
            os.write(fd, payload); os.lseek(fd, 0, os.SEEK_SET)
            got = os.read(fd, 512); os.close(fd)
            ok &= line(got == payload, 'binary-roundtrip-exact', '' if got == payload else 'bytes altered by CRT translation')
        except (ValueError, OSError) as e:
            ok &= line(False, 'binary-roundtrip-exact', str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('PREFLIGHT %s' % ('OK' if ok else 'FAILED'))
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
