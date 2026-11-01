"""Deterministic offline tests for the Windows open-flag mapping and preflight argv
construction (review findings: O_BINARY byte corruption, literal %USERNAME%). These run
on Linux; they pin the PURE mapping functions the Windows branch uses."""
import os
import pytest
from fresh_review.platform_private import win32_access_and_disposition, crt_oflags

GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
CREATE_NEW, OPEN_EXISTING, OPEN_ALWAYS = 1, 3, 4

def test_disposition_mapping():
    assert win32_access_and_disposition(os.O_RDONLY) == (GENERIC_READ, OPEN_EXISTING)
    assert win32_access_and_disposition(os.O_RDWR | os.O_CREAT | os.O_EXCL) == (GENERIC_READ | GENERIC_WRITE, CREATE_NEW)
    assert win32_access_and_disposition(os.O_WRONLY | os.O_CREAT) == (GENERIC_READ | GENERIC_WRITE, OPEN_ALWAYS)
    assert win32_access_and_disposition(os.O_APPEND | os.O_RDWR) == (GENERIC_READ | GENERIC_WRITE, OPEN_EXISTING)

def test_unsupported_flags_rejected_never_mismapped():
    for bad in (os.O_TRUNC, getattr(os, 'O_TEXT', 0x4000), os.O_TRUNC | os.O_RDWR | os.O_CREAT, 0x1000000):
        with pytest.raises(ValueError):
            win32_access_and_disposition(bad)
        with pytest.raises(ValueError):
            crt_oflags(bad)

def test_crt_oflags_always_binary_and_preserves_access():
    ob = getattr(os, 'O_BINARY', 0)
    assert crt_oflags(os.O_RDONLY) == os.O_RDONLY | ob
    assert crt_oflags(os.O_RDWR | os.O_APPEND) == os.O_RDWR | os.O_APPEND | ob
    assert crt_oflags(os.O_WRONLY) == os.O_WRONLY | ob
    # O_BINARY must be a real nonzero bit on Windows; on POSIX the getattr fallback is 0
    # and byte mode is the only mode, so the mapping degenerates safely.

def test_preflight_acl_argv_expands_username_no_shell():
    import windows_preflight as w
    old = os.environ.get('USERNAME')
    os.environ['USERNAME'] = 'reviewuser'
    try:
        argv = w.restrict_acl_argv('C:\\tmp\\k.txt')
    finally:
        if old is None:
            del os.environ['USERNAME']
        else:
            os.environ['USERNAME'] = old
    assert argv[0] == 'icacls'
    assert 'reviewuser:F' in argv
    assert not any('%USERNAME%' in a for a in argv)

def test_preflight_acl_argv_fails_without_username():
    import windows_preflight as w
    old = os.environ.pop('USERNAME', None)
    try:
        with pytest.raises(RuntimeError):
            w.restrict_acl_argv('k.txt')
    finally:
        if old is not None:
            os.environ['USERNAME'] = old

def test_token_and_config_reads_go_through_privacy_checked_open(tmp_path, monkeypatch):
    """load_service must not read the token/config through plain unchecked IO."""
    import dev_install
    calls = []
    import fresh_review.platform_private as pp
    orig = pp.open_private
    def spy(path, flags, mask=0o077):
        calls.append(str(path))
        return orig(path, flags, mask)
    monkeypatch.setattr('fresh_review.platform_private.open_private', spy)
    from PIL import Image
    img = tmp_path / 'scene.png'; Image.new('RGB', (64, 64), 'gray').save(img)
    state = tmp_path / 'state'
    dev_install.create_state(str(state), images=[str(img)], cors_origins=['http://localhost:5173'])
    service, token, origins = dev_install.load_service(str(state / 'dev-config.json'))
    assert any(p.endswith('access-token.txt') for p in calls), calls
    assert any(p.endswith('dev-config.json') for p in calls), calls
    assert 32 <= len(token) <= 256
