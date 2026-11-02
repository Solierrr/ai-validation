"""
Ponto de entrada da aplicação FastAPI — AI Certificate Validator.

Este módulo configura:
- Logging estruturado (JSON) para observabilidade em produção.
- Rate limiting por IP para proteger contra abuso.
- Middleware CORS para permitir chamadas cross-origin.
- Registro das rotas da API.
- Contrato de erro (application/problem+json) e contrato OpenAPI.
"""

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.errors import problem, register_error_handlers
from src.api.routes.certificate_routes import router
from src.api.routes.cnpj_routes import router as cnpj_router
from src.api.routes.debug_routes import router as debug_router
from src.api.routes.health_routes import router as health_router
from src.core.config.settings import get_settings
from src.core.logging.logging_config import configure_logging
from src.otel_setup import configure_otel
from src.version import VERSION

# Carrega variáveis de ambiente do arquivo .env para o os.environ
load_dotenv()

# ─── Logging Estruturado (JSON) ─────────────────────────────────────────────
# Cada linha de log é emitida como JSON, facilitando integração com ferramentas
# de observabilidade (CloudWatch, Datadog, ELK, etc.)
configure_logging()

# ─── Rate Limiting ───────────────────────────────────────────────────────────
# Limita requisições por IP para evitar abuso e proteger a cota da API do Gemini.
# Configuração do limite está no decorator do endpoint (10/minuto).
limiter = Limiter(key_func=get_remote_address)

# ─── Aplicação FastAPI ───────────────────────────────────────────────────────
# Lê as configurações na partida: uma chave de serviço curta impede o serviço de subir.
settings = get_settings()

app = FastAPI(
    title="Solaria — ai-validation",
    description=(
        "Confere documentos enviados por profissionais e empresas parceiras: lê certificados de "
        "treinamento em segurança para instalações elétricas (NR-10) e para trabalho em altura (NR-35) "
        "e verifica a validade, a carga horária e o nome do aluno, e confirma se o CNPJ de uma empresa "
        "parceira está ativo e se a atividade registrada é compatível com o setor de energia solar e "
        "elétrica. Documento reprovado é resultado da validação (status), não erro. As rotas de "
        "validação são públicas e limitadas por IP."
    ),
    version=VERSION,
    contact={"name": "Solaria", "url": "https://github.com/Solierrr"},
    license_info={
        "name": "CC0-1.0",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
    servers=[
        {"url": "https://ai-validation-jjb7.onrender.com", "description": "QA"},
        {"url": "http://localhost:8000", "description": "Local"},
    ],
    openapi_tags=[
        {
            "name": "Certificados",
            "description": "Validação dos certificados NR-10 e NR-35 de profissionais",
        },
        {"name": "Empresas", "description": "Validação do CNPJ de empresas parceiras"},
        {"name": "Saúde", "description": "Estado do serviço (vivo e pronto)"},
    ],
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    redoc_url=None,
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "tryItOutEnabled": True,
        "tagsSorter": "alpha",
        "operationsSorter": "alpha",
    },
)

# Registra o limiter no estado da app (exigência do slowapi)
app.state.limiter = limiter

# Todo erro HTTP sai no contrato de erro (application/problem+json)
register_error_handlers(app)


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded):
    """Responde HTTP 429 quando o limite por IP é excedido, mantendo os cabeçalhos do slowapi."""
    response = problem(
        request, 429, "RATE_LIMITED", f"Limite de requisições atingido: {exc.detail}."
    )
    return request.app.state.limiter._inject_headers(
        response, request.state.view_rate_limit
    )


def cors_origins(raw: str) -> list[str]:
    """Converte a lista separada por vírgula de CORS_ALLOWED_ORIGINS em origens."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


# ─── CORS Middleware ─────────────────────────────────────────────────────────
# Só as origens de CORS_ALLOWED_ORIGINS chamam a API pelo navegador. A autenticação
# vai no header Authorization, sem cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(get_settings().CORS_ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ─── Rotas ───────────────────────────────────────────────────────────────────
# Rotas de validação de certificados NR-10/NR-35 (prefixo /api/v1)
app.include_router(router)
# Rotas de validação de CNPJ de empresas parceiras (prefixo /api/v1)
app.include_router(cnpj_router)
# Rotas de saúde (/health e /ready)
app.include_router(health_router)
# Rotas de debug (só para administradores; fora do OpenAPI)
app.include_router(debug_router)


# ─── Contrato OpenAPI ────────────────────────────────────────────────────────
PROBLEM_JSON = {
    "application/problem+json": {
        "schema": {"$ref": "#/components/schemas/ProblemDetail"}
    }
}


def build_openapi(include_internal: bool) -> dict:
    """
    Gera o contrato OpenAPI do serviço.

    O contrato servido em /openapi.json não inclui as rotas /internal/; o exportado
    (scripts/export_openapi.py) inclui, com o esquema serviceKey.
    """
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        servers=app.servers,
        contact=app.contact,
        license_info=app.license_info,
    )
    if not include_internal:
        schema["paths"] = {
            p: v for p, v in schema["paths"].items() if not p.startswith("/internal/")
        }

    # Toda resposta 4xx/5xx usa o ProblemDetail do contrato de erro; toda operação documenta o 500
    for path in schema["paths"].values():
        for operation in path.values():
            responses = operation["responses"]
            responses.setdefault("500", {"description": "Erro interno inesperado"})
            for code, response in responses.items():
                if code.startswith(("4", "5")):
                    response["content"] = PROBLEM_JSON
                    if code == "422":
                        response["description"] = "Corpo da requisição inválido"

    components = schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    for unused in ("HTTPValidationError", "ValidationError"):
        schemas.pop(unused, None)
    components.setdefault("securitySchemes", {})["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT RS256 emitido pelo api-auth",
    }
    schema["security"] = [{"bearerAuth": []}]

    used_tags = {
        tag
        for path in schema["paths"].values()
        for op in path.values()
        for tag in op.get("tags", [])
    }
    schema["tags"] = [tag for tag in schema.get("tags", []) if tag["name"] in used_tags]
    return schema


def public_openapi() -> dict:
    if app.openapi_schema is None:
        app.openapi_schema = build_openapi(include_internal=False)
    return app.openapi_schema


app.openapi = public_openapi

configure_otel(app, "ai-validation")
