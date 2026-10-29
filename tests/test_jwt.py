"""Testes da validação do access token (src/core/security/jwt.py)."""

from unittest.mock import Mock

import jwt as pyjwt
import pytest

import src.core.security.jwt as jwt_module
from src.core.security.jwt import is_valid_access_token

JWKS = "https://auth.exemplo.com/.well-known/jwks.json"


@pytest.fixture(autouse=True)
def _reset_clients():
    jwt_module._clients.clear()
    yield
    jwt_module._clients.clear()


def _with_claims(monkeypatch, claims):
    jwk_client = Mock()
    jwk_client.get_signing_key_from_jwt.return_value = Mock(key="chave-publica-fake")
    monkeypatch.setattr(jwt_module, "_jwk_client", lambda url: jwk_client)
    monkeypatch.setattr(jwt_module.pyjwt, "decode", lambda *a, **k: claims)


def test_accepts_access_token(monkeypatch):
    _with_claims(monkeypatch, {"sub": "user-1", "token_type": "access"})

    assert is_valid_access_token("t", jwks_url=JWKS, issuer="solaria-auth") is True


def test_accepts_token_without_token_type(monkeypatch):
    _with_claims(monkeypatch, {"sub": "user-1"})

    assert is_valid_access_token("t", jwks_url=JWKS, issuer="solaria-auth") is True


def test_rejects_refresh_token(monkeypatch):
    _with_claims(monkeypatch, {"sub": "user-1", "token_type": "refresh"})

    assert is_valid_access_token("t", jwks_url=JWKS, issuer="solaria-auth") is False


def test_rejects_malformed_token(monkeypatch):
    jwk_client = Mock()
    jwk_client.get_signing_key_from_jwt.side_effect = pyjwt.exceptions.DecodeError("x")
    monkeypatch.setattr(jwt_module, "_jwk_client", lambda url: jwk_client)

    assert is_valid_access_token("lixo", jwks_url=JWKS, issuer="solaria-auth") is False


def test_rejects_when_jwks_is_down(monkeypatch):
    jwk_client = Mock()
    jwk_client.get_signing_key_from_jwt.side_effect = (
        pyjwt.exceptions.PyJWKClientConnectionError("fora do ar")
    )
    monkeypatch.setattr(jwt_module, "_jwk_client", lambda url: jwk_client)

    assert is_valid_access_token("t", jwks_url=JWKS, issuer="solaria-auth") is False


def test_requires_exp_and_sub_and_rs256(monkeypatch):
    jwk_client = Mock()
    jwk_client.get_signing_key_from_jwt.return_value = Mock(key="chave-publica-fake")
    monkeypatch.setattr(jwt_module, "_jwk_client", lambda url: jwk_client)
    captured = {}

    def decode(*args, **kwargs):
        captured.update(kwargs)
        return {"sub": "user-1"}

    monkeypatch.setattr(jwt_module.pyjwt, "decode", decode)

    is_valid_access_token("t", jwks_url=JWKS, issuer="solaria-auth")

    assert captured["algorithms"] == ["RS256"]
    assert captured["issuer"] == "solaria-auth"
    assert captured["options"] == {"require": ["exp", "sub"]}
