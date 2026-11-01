"""Regression record: a bare httpx.AsyncClient() parses proxy environment variables at
construction (trust_env=True), so a malformed ALL_PROXY or NO_PROXY/no_proxy value raises
httpx.InvalidURL before any application code runs. This is the environment sensitivity
behind the one-environment-only failure of
tests/test_local_ui_proxy.py::test_backend_receives_derived_display_value_never_the_cookie_value
(693 clean-shell passes; 692+1 in a shell carrying such a variable, exact error string
"Invalid port: ':1'" / "Invalid port: ':1]'"). Product validation is unaffected: with any
constructible client, create_proxy's short-display_secret check still raises ValueError.
No network: MockTransport only."""
import httpx
import pytest
from local_ui_proxy import create_proxy

TOKEN = 'synthetic-local-test-token-12345678901234567890'
NONCE = 'n' * 48
PROXY_VARS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
              'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')


@pytest.fixture
def clean_env(monkeypatch):
    for var in PROXY_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.mark.parametrize('var,value', [
    ('ALL_PROXY', 'http://[::1'),
    ('all_proxy', 'http://[::1'),
    ('HTTPS_PROXY', 'http://[::1'),
    ('NO_PROXY', '[::1]'),
    ('no_proxy', '[::1]'),
])
def test_bare_client_construction_fails_on_malformed_proxy_env(clean_env, var, value):
    clean_env.setenv(var, value)
    with pytest.raises(httpx.InvalidURL):
        httpx.AsyncClient()


def test_clean_env_bare_client_constructs(clean_env):
    httpx.AsyncClient()


def test_create_proxy_short_secret_validation_unchanged_under_malformed_env(clean_env):
    clean_env.setenv('NO_PROXY', '[::1]')
    backend = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)),
                                base_url='http://backend')
    with pytest.raises(ValueError):
        create_proxy(backend, TOKEN, launch_nonce=NONCE, display_secret=b'short')
