"""
Ponto de entrada da aplicação FastAPI — AI Certificate Validator.

Este módulo configura:
- Logging estruturado (JSON) para observabilidade em produção.
- Rate limiting por IP para proteger contra abuso.
- Middleware CORS para permitir chamadas cross-origin.
- Registro das rotas da API.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.routes.certificate_routes import router
from src.api.routes.cnpj_routes import router as cnpj_router
from src.core.logging.logging_config import configure_logging

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
app = FastAPI(
    title="AI Validation Platform",
    description=(
        "Multi-agent platform for AI-powered validations: "
        "NR-10/NR-35 safety certificates and CNPJ company compatibility."
    ),
    version="1.1.0",
)

# Registra o limiter no estado da app (exigência do slowapi)
app.state.limiter = limiter
# Handler customizado que retorna HTTP 429 quando o limite é excedido
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── CORS Middleware ─────────────────────────────────────────────────────────
# Permite requisições de qualquer origem (ideal para dev; restringir em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restringir para domínios autorizados em produção
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rotas ───────────────────────────────────────────────────────────────────
# Rotas de validação de certificados NR-10/NR-35 (prefixo /api/v1)
app.include_router(router)
# Rotas de validação de CNPJ de empresas parceiras (prefixo /api/v1)
app.include_router(cnpj_router)


@app.get("/health", tags=["system"])
async def health_check():
    """
    Endpoint de health check para monitoramento.

    Retorna {"status": "healthy"} se o serviço está rodando.
    Usado por load balancers e ferramentas de monitoramento.
    """
    return {"status": "healthy"}
