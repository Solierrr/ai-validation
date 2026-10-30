"""Testes da aplicação FastAPI (main.py)."""

from pathlib import Path

from main import app
from src.version import VERSION


class TestHealthCheck:
    """Rotas de vivo (/health) e pronto (/ready)."""

    def test_health_returns_up_with_version(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "UP", "version": VERSION}

    def test_ready_returns_up(self, client):
        response = client.get("/ready")

        assert response.status_code == 200
        assert response.json() == {"status": "UP"}


class TestAppMetadata:
    """Metadados expostos na documentação OpenAPI."""

    def test_has_title_and_release_version(self):
        version_file = Path(__file__).resolve().parents[1] / "version.txt"

        assert app.title == "Solaria — ai-validation"
        assert app.version == VERSION
        assert VERSION == version_file.read_text(encoding="utf-8").strip()

    def test_openapi_exposes_validation_and_health_endpoints(self, client):
        paths = client.get("/openapi.json").json()["paths"]

        assert "/api/v1/certificates/validate" in paths
        assert "/api/v1/companies/validate-cnpj" in paths
        assert "/health" in paths
        assert "/ready" in paths

    def test_swagger_ui_is_available(self, client):
        assert client.get("/docs").status_code == 200


class TestOpenApiContract:
    """Contrato no padrão da organização (docs-warehouse, docs/standards/OPENAPI.md)."""

    def test_info_follows_the_standard(self, client):
        schema = client.get("/openapi.json").json()

        assert schema["info"]["contact"] == {"name": "Solaria", "url": "https://github.com/Solierrr"}
        assert schema["info"]["license"]["name"] == "CC0-1.0"
        assert schema["servers"][0]["description"] == "QA"

    def test_declares_bearer_auth_as_default(self, client):
        schema = client.get("/openapi.json").json()

        assert schema["security"] == [{"bearerAuth": []}]
        assert schema["components"]["securitySchemes"]["bearerAuth"]["bearerFormat"] == "JWT"

    def test_validation_routes_require_the_jwt_and_health_is_public(self, client):
        paths = client.get("/openapi.json").json()["paths"]

        assert paths["/api/v1/certificates/validate"]["post"]["security"] == [{"bearerAuth": []}]
        assert paths["/api/v1/companies/validate-cnpj"]["post"]["security"] == [{"bearerAuth": []}]
        assert paths["/health"]["get"]["security"] == []
        assert paths["/ready"]["get"]["security"] == []

    def test_every_error_response_uses_problem_detail(self, client):
        schema = client.get("/openapi.json").json()

        assert "ProblemDetail" in schema["components"]["schemas"]
        assert "HTTPValidationError" not in schema["components"]["schemas"]
        for path in schema["paths"].values():
            for operation in path.values():
                assert "500" in operation["responses"]
                for code, response in operation["responses"].items():
                    if code.startswith(("4", "5")):
                        assert list(response["content"]) == ["application/problem+json"]

    def test_internal_routes_are_hidden_only_from_the_served_contract(self):
        from fastapi import APIRouter, Depends

        from main import build_openapi
        from src.api.security import require_caller

        internal = APIRouter(tags=["Interno"])

        @internal.get("/internal/ping", summary="Ping interno", operation_id="internalPing")
        async def ping(caller: str = Depends(require_caller("api-core"))):
            return {"caller": caller}

        app.include_router(internal)
        try:
            exported = build_openapi(include_internal=True)
            served = build_openapi(include_internal=False)
        finally:
            app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/internal/ping"]

        assert exported["paths"]["/internal/ping"]["get"]["security"] == [{"serviceKey": []}]
        assert "/internal/ping" not in served["paths"]
        assert "Interno" not in [tag["name"] for tag in served["tags"]]


class TestErrorContract:
    """Todo erro HTTP sai como application/problem+json."""

    def test_unknown_route_returns_not_found(self, client):
        response = client.get("/nao-existe")
        body = response.json()

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"
        assert body["errorCode"] == "NOT_FOUND"
        assert body["title"] == "NOT_FOUND"
        assert body["type"] == "about:blank"
        assert body["instance"] == "/nao-existe"
        assert "timestamp" in body

    def test_invalid_body_returns_validation_failed(self, client):
        response = client.post("/api/v1/companies/validate-cnpj", json={})
        body = response.json()

        assert response.status_code == 422
        assert body["errorCode"] == "VALIDATION_FAILED"
        assert body["errors"][0]["field"] == "cnpj"


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
