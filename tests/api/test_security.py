"""Testes da autenticação entre serviços (src/api/security.py)."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.errors import register_error_handlers
from src.api.security import require_caller

API_CORE_KEY = "a" * 32


@pytest.fixture
def service_client(monkeypatch):
    """App mínimo com uma rota por chamador aceito."""
    monkeypatch.setenv("SERVICE_KEY_API_CORE", API_CORE_KEY)
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/internal/core-only", dependencies=[Depends(require_caller("api-core"))])
    async def core_only():
        return {"ok": True}

    @app.get(
        "/internal/other-caller",
        dependencies=[Depends(require_caller("ai-geographic"))],
    )
    async def other_caller():
        return {"ok": True}

    return TestClient(app)


class TestRequireCaller:
    """Chave por chamador, comparação em tempo constante e autorização por rota."""

    def test_accepts_the_caller_key(self, service_client):
        response = service_client.get(
            "/internal/core-only", headers={"X-Service-Key": API_CORE_KEY}
        )

        assert response.status_code == 200

    def test_rejects_a_missing_key(self, service_client):
        response = service_client.get("/internal/core-only")

        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["errorCode"] == "UNAUTHENTICATED"

    def test_rejects_a_wrong_key(self, service_client):
        response = service_client.get(
            "/internal/core-only", headers={"X-Service-Key": "b" * 32}
        )

        assert response.status_code == 401

    def test_forbids_a_caller_the_route_does_not_accept(self, service_client):
        response = service_client.get(
            "/internal/other-caller", headers={"X-Service-Key": API_CORE_KEY}
        )

        assert response.status_code == 403
        assert response.json()["errorCode"] == "FORBIDDEN"

    def test_refuses_everything_without_configured_keys(
        self, service_client, monkeypatch
    ):
        from src.core.config.settings import get_settings

        monkeypatch.setenv("SERVICE_KEY_API_CORE", "")
        get_settings.cache_clear()

        response = service_client.get(
            "/internal/core-only", headers={"X-Service-Key": API_CORE_KEY}
        )

        assert response.status_code == 401
