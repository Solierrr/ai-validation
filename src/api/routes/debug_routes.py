"""Modo debug da validação: roda o fluxo e devolve as etapas que ele percorreu.

Só para uso interno: sempre ativo, mas restrito aos admins de `DEBUG_ADMIN_SUBS` e
fora do OpenAPI. Duas rotas: certificados (grafo LangGraph) e CNPJ (que não é grafo: a
execução inteira vira uma única etapa). Nada é gravado; imagens em base64 e a query
string das URLs nunca saem."""

import asyncio
import logging
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.runnables import RunnableLambda
from pydantic import Field

from src.api.routes.cnpj_routes import run_cnpj_validation
from src.api.schemas.certificate_schemas import (
    CertificateValidationRequest,
    CertificateValidationResponse,
)
from src.api.schemas.cnpj_schemas import CNPJValidationRequest, CNPJValidationResponse
from src.core.config.settings import get_settings
from src.core.security.jwt import decode_user_id
from src.workflow.graph.graph import compiled_graph
from src.workflow.observability.debug_tracker import DebugTracker, mask_pii

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"], include_in_schema=False)
bearer_scheme = HTTPBearer(auto_error=False)

DEBUG_ALLOWED_ENVIRONMENTS = frozenset({"LOCAL", "DEV", "QA", "PROD"})
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class DebugCertificateResponse(CertificateValidationResponse):
    debug: dict = Field(default_factory=dict)


class DebugCNPJResponse(CNPJValidationResponse):
    debug: dict = Field(default_factory=dict)


def debug_admin_subs() -> set[str]:
    subs = {part.strip().lower() for part in get_settings().DEBUG_ADMIN_SUBS.split(",")}
    return {sub for sub in subs if _UUID.match(sub)}


def debug_enabled() -> bool:
    """A rota só existe em ambiente permitido e com ao menos um admin configurado."""
    environment = get_settings().ENVIRONMENT.strip().upper()
    return environment in DEBUG_ALLOWED_ENVIRONMENTS and bool(debug_admin_subs())


async def _authorize(credentials: HTTPAuthorizationCredentials | None) -> str:
    """Devolve o `sub` de um admin; falha fechado em qualquer dúvida."""
    if not debug_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    if credentials is None:
        raise HTTPException(
            status_code=401, detail="Authorization header deve ser 'Bearer <token>'"
        )
    sub = await asyncio.to_thread(decode_user_id, credentials.credentials)
    if not sub:
        raise HTTPException(status_code=401, detail="Token inválido")
    if sub.lower() not in debug_admin_subs():
        raise HTTPException(status_code=403, detail="Sem permissão para o modo debug")
    logger.info(
        "Execução de debug (sub=%s, ambiente=%s)",
        sub.lower(),
        get_settings().ENVIRONMENT,
    )
    return sub.lower()


def _failure(status_code: int, detail: str, collector: DebugTracker) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": mask_pii(detail[:1000])[:500],
            "debug": collector.snapshot(),
        },
    )


def _finish(collector: DebugTracker) -> dict:
    debug = collector.snapshot()
    debug["environment"] = get_settings().ENVIRONMENT
    debug["persisted"] = False
    return debug


@router.post("/certificates/validate", response_model=DebugCertificateResponse)
async def debug_validate_certificates(
    payload: CertificateValidationRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    await _authorize(credentials)
    collector = DebugTracker()
    initial_state = {
        "cert_nr10_url": str(payload.cert_nr10_url),
        "cert_nr35_url": str(payload.cert_nr35_url),
        "current_date": date.today().isoformat(),
    }
    try:
        result = await compiled_graph.ainvoke(
            initial_state, config={"callbacks": [collector]}
        )
    except Exception as error:
        logger.exception("Falha na execução de debug dos certificados")
        return _failure(500, f"{type(error).__name__}: {error}", collector)
    return DebugCertificateResponse(
        status=result.get("status", "REJECTED"),
        reason=result.get("reason", "Erro desconhecido na validação."),
        error_code=result.get("error_code"),
        extracted_data=result.get("extracted_data"),
        debug=_finish(collector),
    )


@router.post("/companies/validate-cnpj", response_model=DebugCNPJResponse)
async def debug_validate_cnpj(
    payload: CNPJValidationRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    await _authorize(credentials)
    collector = DebugTracker()
    step = RunnableLambda(run_cnpj_validation, name="cnpj_validation")
    try:
        response = await step.ainvoke(
            payload,
            config={
                "callbacks": [collector],
                "run_name": "cnpj_validation",
                "metadata": {"langgraph_node": "cnpj_validation"},
            },
        )
    except HTTPException as error:
        return _failure(error.status_code, str(error.detail), collector)
    except Exception as error:
        logger.exception("Falha na execução de debug do CNPJ")
        return _failure(500, f"{type(error).__name__}: {error}", collector)
    return DebugCNPJResponse(**response.model_dump(), debug=_finish(collector))
