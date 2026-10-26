"""Modo debug da validação: roda o fluxo e devolve as etapas que ele percorreu.

Só para uso interno: sempre ativo, mas restrito aos admins de `DEBUG_ADMIN_SUBS` e
fora do OpenAPI. Duas rotas: certificados (grafo LangGraph) e CNPJ (que não é grafo: a
execução inteira vira uma única etapa). Nada é gravado; imagens em base64 e a query
string das URLs nunca saem."""

import asyncio
import logging
import re
from datetime import date
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field, field_validator

from src.api.routes.cnpj_routes import run_cnpj_validation
from src.api.schemas.certificate_schemas import (
    CertificateValidationRequest,
)
from src.api.schemas.cnpj_schemas import CNPJValidationRequest, CNPJValidationResponse
from src.core.config.settings import get_settings
from src.core.security.jwt import decode_user_id
from src.workflow.debug_replay import ReplayError, check_replayable, run_single_node
from src.workflow.debug_runs import DebugRunStore, estimate_size, thread_id
from src.workflow.graph.graph import build_graph
from src.workflow.observability.debug_tracker import DebugTracker, mask_pii
from src.workflow.observability.prompt_override import PromptOverride

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"], include_in_schema=False)
bearer_scheme = HTTPBearer(auto_error=False)

DEBUG_ALLOWED_ENVIRONMENTS = frozenset({"LOCAL", "DEV", "QA", "PROD"})
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


debug_graph = build_graph(InMemorySaver())
debug_runs = DebugRunStore(debug_graph)

CNPJ_NODE = "cnpj_validation"
CNPJ_EDITABLE = ("system", "human")


class PromptMessage(BaseModel):
    type: str = Field(max_length=32)
    content: str


class PromptOverrideItem(BaseModel):
    call: int = Field(ge=0, le=50)
    prompt: list[PromptMessage]


class _CustomRun(BaseModel):
    stop_after_node: Literal[True] = True
    prompts: Annotated[list[PromptOverrideItem], Field(max_length=50)] = Field(
        default_factory=list
    )

    @field_validator("prompts")
    @classmethod
    def _calls_unicas(cls, items):
        if len({item.call for item in items}) != len(items):
            raise ValueError("Chamada de LLM repetida em prompts")
        return items


class CertificateCustomRun(_CustomRun):
    run_id: str = Field(pattern=_UUID.pattern)
    node: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    occurrence: int = Field(0, ge=0, le=50)


class CnpjCustomRun(_CustomRun):
    node: Literal["cnpj_validation"] = CNPJ_NODE


class DebugCertificateRequest(CertificateValidationRequest):
    custom: CertificateCustomRun | None = None


class DebugCNPJRequest(CNPJValidationRequest):
    custom: CnpjCustomRun | None = None


class DebugCertificateResponse(BaseModel):
    status: str | None = None
    reason: str | None = None
    error_code: str | None = None
    extracted_data: Any = None
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


def _failure(
    status_code: int, detail: str, collector: DebugTracker, **extra: Any
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": mask_pii(detail[:1000])[:500],
            "debug": {**collector.snapshot(), **extra},
        },
    )


def _finish(collector: DebugTracker) -> dict:
    debug = collector.snapshot()
    debug["environment"] = get_settings().ENVIRONMENT
    debug["persisted"] = False
    return debug


def _overrides(custom: _CustomRun, types: tuple[str, ...]) -> dict[int, dict[int, str]]:
    return {
        item.call: {
            position: message.content
            for position, message in enumerate(item.prompt)
            if message.type in types
        }
        for item in custom.prompts
    }


def _audit(sub: str, custom: _CustomRun) -> None:
    logger.info(
        "Execução personalizada de nó (sub=%s, nó=%s, prompts=%s)",
        sub,
        custom.node,
        len(custom.prompts),
    )


async def _stored_size(config: dict) -> int:
    try:
        snapshot = await debug_graph.aget_state(config)
        return estimate_size(
            snapshot.values if isinstance(snapshot.values, dict) else {}
        )
    except Exception:
        logger.warning("Não foi possível medir a execução de debug", exc_info=True)
        return 0


@router.post("/certificates/validate", response_model=DebugCertificateResponse)
async def debug_validate_certificates(
    payload: DebugCertificateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    sub = await _authorize(credentials)
    if payload.custom is not None:
        return await _replay_certificate_node(sub, payload.custom)

    collector = DebugTracker()
    run_id = str(uuid4())
    config = {
        "configurable": {"thread_id": thread_id(sub, run_id)},
        "callbacks": [collector],
        "metadata": {"source": "debug", "run_id": run_id},
    }
    initial_state = {
        "cert_nr10_url": str(payload.cert_nr10_url),
        "cert_nr35_url": str(payload.cert_nr35_url),
        "current_date": date.today().isoformat(),
    }
    try:
        result = await debug_graph.ainvoke(initial_state, config=config)
    except Exception as error:
        logger.exception("Falha na execução de debug dos certificados")
        await debug_runs.add(sub, run_id, await _stored_size(config))
        return _failure(
            500, f"{type(error).__name__}: {error}", collector, run_id=run_id, turn=0
        )
    await debug_runs.add(sub, run_id, estimate_size(result))
    debug = _finish(collector)
    debug["run_id"] = run_id
    debug["turn"] = 0
    return DebugCertificateResponse(
        status=result.get("status", "REJECTED"),
        reason=result.get("reason", "Erro desconhecido na validação."),
        error_code=result.get("error_code"),
        extracted_data=result.get("extracted_data"),
        debug=debug,
    )


async def _replay_certificate_node(sub: str, custom: CertificateCustomRun):
    _audit(sub, custom)
    collector = DebugTracker()
    if not await debug_runs.exists(sub, custom.run_id):
        return JSONResponse(
            status_code=404,
            content={
                "detail": "Essa execução expirou ou não existe nesta instância. "
                "Rode a validação de novo."
            },
        )
    try:
        check_replayable(custom.node)
        _, next_nodes, applied = await run_single_node(
            debug_graph,
            thread_id(sub, custom.run_id),
            turn=0,
            node=custom.node,
            occurrence=custom.occurrence,
            overrides=_overrides(custom, ("system",)),
            callbacks=[collector],
            metadata={"source": "debug-replay", "run_id": custom.run_id},
            tags=[get_settings().ENVIRONMENT.lower()],
        )
    except ReplayError as error:
        return JSONResponse(status_code=error.status, content={"detail": error.detail})
    except Exception as error:
        logger.exception("Falha na execução personalizada do nó %s", custom.node)
        return _failure(500, f"{type(error).__name__}: {error}", collector)
    debug = _finish(collector)
    debug["custom"] = {
        "run_id": custom.run_id,
        "node": custom.node,
        "turn": 0,
        "occurrence": custom.occurrence,
        "stopped": True,
        "overrides_applied": applied,
        "next": list(next_nodes),
    }
    return DebugCertificateResponse(debug=debug)


@router.post("/companies/validate-cnpj", response_model=DebugCNPJResponse)
async def debug_validate_cnpj(
    payload: DebugCNPJRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    sub = await _authorize(credentials)
    custom = payload.custom
    collector = DebugTracker(editable_types=CNPJ_EDITABLE)
    callbacks = [collector]
    override = None
    if custom is not None:
        _audit(sub, custom)
        override = PromptOverride(
            CNPJ_NODE,
            _overrides(custom, CNPJ_EDITABLE),
            types=CNPJ_EDITABLE,
            repeat_first=True,
        )
        callbacks = [override, collector]
    step = RunnableLambda(run_cnpj_validation, name=CNPJ_NODE)
    try:
        response = await step.ainvoke(
            CNPJValidationRequest(cnpj=payload.cnpj),
            config={
                "callbacks": callbacks,
                "run_name": CNPJ_NODE,
                "metadata": {"langgraph_node": CNPJ_NODE},
            },
        )
    except HTTPException as error:
        return _failure(error.status_code, str(error.detail), collector)
    except Exception as error:
        logger.exception("Falha na execução de debug do CNPJ")
        return _failure(500, f"{type(error).__name__}: {error}", collector)
    debug = _finish(collector)
    debug["turn"] = 0
    if custom is not None:
        debug["custom"] = {
            "node": CNPJ_NODE,
            "turn": 0,
            "occurrence": 0,
            "stopped": True,
            "overrides_applied": override.applied,
            "next": [],
        }
    return DebugCNPJResponse(**response.model_dump(), debug=debug)
