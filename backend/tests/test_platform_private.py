import os,sys,stat
import pytest
from fresh_review.platform_private import (
    parse_icacls, IcaclsParseError, is_private_posix, is_private_windows_proposed, _dacl_private)

SELF = {'desktop-1\\aadi', 's-1-5-21-1000'}

EN_ICACLS_PRIVATE='''C:\\Users\\aadi\\vigilens-key.txt NT AUTHORITY\\SYSTEM:(I)(F)
                            BUILTIN\\Administrators:(I)(F)
                            DESKTOP-1\\aadi:(I)(F)

Successfully processed 1 files; Failed processing 0 files
'''
EN_ICACLS_SID_SELF='''C:\\Users\\aadi\\vigilens-key.txt S-1-5-21-1000:(I)(F)

Successfully processed 1 files; Failed processing 0 files
'''
EN_ICACLS_WORLD='''C:\\shared\\key.txt Everyone:(I)(F)
                      BUILTIN\\Users:(R)

Successfully processed 1 files; Failed processing 0 files
'''
EN_ICACLS_DENY='''C:\\k.txt DESKTOP-1\\aadi:(DENY)(W)

Successfully processed 1 files; Failed processing 0 files
'''
EN_ICACLS_GARBLED='''??? unexpected locale line
'''
EN_ICACLS_NO_SUMMARY='''C:\\k.txt DESKTOP-1\\aadi:(I)(F)
'''
EN_ICACLS_EXTRA_LINE='''C:\\k.txt DESKTOP-1\\aadi:(I)(F)

Successfully processed 1 files; Failed processing 0 files
mystery trailing content
'''

def test_icacls_parser_extracts_aces_deterministically():
    aces = parse_icacls(EN_ICACLS_PRIVATE, path='C:\\Users\\aadi\\vigilens-key.txt')
    assert [p for p,_ in aces] == ['NT AUTHORITY\\SYSTEM','BUILTIN\\Administrators','DESKTOP-1\\aadi']

def test_icacls_parser_fails_closed_on_any_unrecognized_shape():
    for bad in (EN_ICACLS_GARBLED, EN_ICACLS_NO_SUMMARY, EN_ICACLS_EXTRA_LINE, '',
                'Successfully processed 0 files; Failed processing 0 files'):
        with pytest.raises(IcaclsParseError):
            parse_icacls(bad, path='C:\\k.txt')

def test_dacl_policy_exact_identity_only():
    # exact full-principal match; look-alikes and tails do NOT pass
    aces = parse_icacls(EN_ICACLS_PRIVATE, path='C:\\Users\\aadi\\vigilens-key.txt')
    assert _dacl_private(aces, SELF) is True
    assert _dacl_private([('OTHERDOMAIN\\aadi','(I)(F)')], SELF) is False
    assert _dacl_private([('aadi','(I)(F)')], SELF) is False           # bare name != DOMAIN\name
    assert _dacl_private([('S-1-5-21-1000-extra','(F)')], SELF) is False  # no startswith
    assert _dacl_private(parse_icacls(EN_ICACLS_SID_SELF, path='C:\\Users\\aadi\\vigilens-key.txt'), SELF) is True
    assert _dacl_private(parse_icacls(EN_ICACLS_DENY, path='C:\\k'), SELF) is False

def test_windows_check_refuses_world_garbled_and_bad_status():
    assert is_private_windows_proposed('C:\\Users\\aadi\\vigilens-key.txt', icacls_output=EN_ICACLS_PRIVATE, allowed_self=SELF) is True
    assert is_private_windows_proposed('C:\\Users\\aadi\\vigilens-key.txt', icacls_output=EN_ICACLS_WORLD, allowed_self=SELF) is False
    assert is_private_windows_proposed('C:\\Users\\aadi\\vigilens-key.txt', icacls_output=EN_ICACLS_GARBLED, allowed_self=SELF) is False
    assert is_private_windows_proposed('C:\\Users\\aadi\\vigilens-key.txt', icacls_output='', allowed_self=SELF) is False
    assert is_private_windows_proposed('C:\\Users\\aadi\\vigilens-key.txt', icacls_output=EN_ICACLS_PRIVATE,
                                       icacls_returncode=1, allowed_self=SELF) is False

def test_posix_semantics_unchanged(tmp_path):
    p = tmp_path/'k.txt'; p.write_text('k')
    p.chmod(0o600); assert is_private_posix(p) is True
    p.chmod(0o644); assert is_private_posix(p) is False
    link = tmp_path/'l'; link.symlink_to(p)
    assert is_private_posix(link) is False
