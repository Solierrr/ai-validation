"""Testes da exigência do access token nas rotas de validação (src/api/auth.py)."""

import pytest

ENDPOINTS = [
    "/api/v1/companies/validate-cnpj",
    "/api/v1/certificates/validate",
]
BODIES = {
    "/api/v1/companies/validate-cnpj": {"cnpj": "123"},
    "/api/v1/certificates/validate": {
        "cert_nr10_url": "https://exemplo.com/nr10.jpg",
        "cert_nr35_url": "https://exemplo.com/nr35.jpg",
    },
}
JWKS = "https://auth.exemplo.com/.well-known/jwks.json"


@pytest.fixture
def auth_required(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("JWT_JWKS_URL", JWKS)
    monkeypatch.setenv("JWT_ISSUER", "solaria-auth")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_requires_bearer_token(client, auth_required, endpoint):
    response = client.post(endpoint, json=BODIES[endpoint])

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_rejects_invalid_token(client, auth_required, monkeypatch, endpoint):
    monkeypatch.setattr("src.api.auth.is_valid_access_token", lambda *a, **k: False)

    response = client.post(
        endpoint, json=BODIES[endpoint], headers={"Authorization": "Bearer invalido"}
    )

    assert response.status_code == 401


def test_accepts_valid_token(client, auth_required, monkeypatch):
    received = {}

    def fake_valid(token, *, jwks_url, issuer):
        received.update(token=token, jwks_url=jwks_url, issuer=issuer)
        return True

    monkeypatch.setattr("src.api.auth.is_valid_access_token", fake_valid)

    response = client.post(
        "/api/v1/companies/validate-cnpj",
        json={"cnpj": "123"},
        headers={"Authorization": "Bearer token-valido"},
    )

    assert response.status_code == 200
    assert response.json()["error_code"] == "INVALID_CNPJ_FORMAT"
    assert received == {
        "token": "token-valido",
        "jwks_url": JWKS,
        "issuer": "solaria-auth",
    }


def test_fails_closed_when_jwks_is_not_configured(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.delenv("JWT_JWKS_URL", raising=False)

    response = client.post(
        "/api/v1/companies/validate-cnpj",
        json={"cnpj": "123"},
        headers={"Authorization": "Bearer qualquer"},
    )

    assert response.status_code == 503


def test_auth_can_be_disabled_explicitly(client):
    response = client.post("/api/v1/companies/validate-cnpj", json={"cnpj": "123"})

    assert response.status_code == 200


def test_unauthorized_response_carries_cors_headers(client, auth_required):
    response = client.post(
        "/api/v1/companies/validate-cnpj",
        json={"cnpj": "123"},
        headers={"Origin": "https://app.exemplo.com"},
    )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://app.exemplo.com"


def test_health_stays_public(client, auth_required):
    assert client.get("/health").status_code == 200
