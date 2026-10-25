"""
Rotas de saúde do serviço.

/health indica que o processo está vivo; /ready indica que está pronto para atender.
O serviço não tem banco nem cache, e os provedores de LLM e a BrasilAPI ficam fora do pronto
(o LLM tem fallback entre provedores e a BrasilAPI é consultada só na validação de CNPJ).
"""

from fastapi import APIRouter

from src.api.schemas.health_schemas import HealthResponse
from src.version import VERSION

router = APIRouter(tags=["Saúde"])


@router.get(
    "/health",
    response_model=HealthResponse,
    response_model_exclude_none=True,
    summary="Indica se o processo está vivo",
    operation_id="getHealth",
    openapi_extra={"security": []},
)
async def health() -> HealthResponse:
    return HealthResponse(status="UP", version=VERSION)


@router.get(
    "/ready",
    response_model=HealthResponse,
    response_model_exclude_none=True,
    summary="Indica se o serviço está pronto para atender",
    operation_id="getReady",
    openapi_extra={"security": []},
)
async def ready() -> HealthResponse:
    return HealthResponse(status="UP")
