"""Testes da aplicação FastAPI (src/main.py)."""

from src.main import app


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
    """CORS liberado para facilitar o consumo pelo front-end."""

    def test_echoes_allowed_origin(self, client):
        response = client.get("/health", headers={"Origin": "https://meuapp.com"})

        assert response.headers["access-control-allow-origin"] == "https://meuapp.com"

    def test_allows_preflight_request(self, client):
        response = client.options(
            "/api/v1/companies/validate-cnpj",
            headers={
                "Origin": "https://meuapp.com",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 200


class TestRateLimiterWiring:
    """O limiter precisa estar registrado no app para o slowapi funcionar."""

    def test_limiter_is_attached_to_app_state(self):
        assert app.state.limiter is not None
