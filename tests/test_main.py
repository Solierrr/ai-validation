"""Testes da aplicação FastAPI (main.py)."""

from main import app


class TestHealthCheck:
    """Endpoint usado por load balancers e probes de liveness/readiness."""

    def test_returns_healthy(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestAppMetadata:
    """Metadados expostos na documentação OpenAPI."""

    def test_has_title_and_version(self):
        assert app.title == "AI Validation Platform"
        assert app.version == "1.1.0"

    def test_openapi_exposes_both_validation_endpoints(self, client):
        paths = client.get("/openapi.json").json()["paths"]

        assert "/api/v1/certificates/validate" in paths
        assert "/api/v1/companies/validate-cnpj" in paths
        assert "/health" in paths

    def test_swagger_ui_is_available(self, client):
        assert client.get("/docs").status_code == 200


class TestCorsMiddleware:
    """CORS limitado às origens de CORS_ALLOWED_ORIGINS, sem credenciais."""

    def test_echoes_allowed_origin(self, client):
        response = client.get("/health", headers={"Origin": "https://app.exemplo.com"})

        assert response.headers["access-control-allow-origin"] == "https://app.exemplo.com"
        assert "access-control-allow-credentials" not in response.headers

    def test_does_not_echo_unknown_origin(self, client):
        response = client.get("/health", headers={"Origin": "https://outro-site.com"})

        assert "access-control-allow-origin" not in response.headers

    def test_allows_preflight_request_with_authorization(self, client):
        response = client.options(
            "/api/v1/companies/validate-cnpj",
            headers={
                "Origin": "https://app.exemplo.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://app.exemplo.com"

    def test_rejects_preflight_from_unknown_origin(self, client):
        response = client.options(
            "/api/v1/companies/validate-cnpj",
            headers={
                "Origin": "https://outro-site.com",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_cors_origins_splits_by_comma_and_ignores_blanks(self):
        from main import cors_origins

        assert cors_origins(" https://a.com ,, https://b.com,") == [
            "https://a.com",
            "https://b.com",
        ]
        assert cors_origins("") == []

    def test_default_origins_are_local_only(self):
        from main import cors_origins
        from src.core.config.settings import Settings

        assert cors_origins(Settings.model_fields["CORS_ALLOWED_ORIGINS"].default) == [
            "http://localhost:5173",
            "http://localhost:3000",
        ]


class TestRateLimiterWiring:
    """O limiter precisa estar registrado no app para o slowapi funcionar."""

    def test_limiter_is_attached_to_app_state(self):
        assert app.state.limiter is not None
