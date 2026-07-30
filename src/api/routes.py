"""
Rotas da API de validação de certificados.

Define o endpoint principal POST /api/v1/certificates/validate que recebe
URLs de certificados NR-10 e NR-35 e executa a pipeline multi-agente.
"""

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.schemas import CertificateValidationRequest, CertificateValidationResponse
from src.workflow.graph import compiled_graph

logger = logging.getLogger(__name__)

# Rate limiter local para aplicar limites específicos por endpoint
limiter = Limiter(key_func=get_remote_address)

# Router com prefixo /api/v1 — todas as rotas aqui ficam sob esse path
router = APIRouter(prefix="/api/v1", tags=["certificates"])


@router.post(
    "/certificates/validate",
    response_model=CertificateValidationResponse,
    summary="Validate NR-10 and NR-35 certificates",
    description=(
        "Receives URLs for NR-10 and NR-35 certificate images, "
        "runs the multi-agent validation pipeline, and returns "
        "an ACCEPT or REJECTED decision."
    ),
)
@limiter.limit("10/minute")  # Máximo 10 validações por minuto por IP
async def validate_certificates(
    request: Request,  # Request do Starlette (necessário para o rate limiter)
    payload: CertificateValidationRequest,  # Body JSON com as URLs dos certificados
) -> CertificateValidationResponse:
    """
    Endpoint principal de validação de certificados.

    Fluxo:
    1. Recebe as URLs das imagens dos certificados NR-10 e NR-35.
    2. Injeta a data atual (current_date) automaticamente no state.
    3. Executa a pipeline LangGraph (security → NR-10 → NR-35 → consolidation).
    4. Retorna ACCEPT ou REJECTED com explicação e dados extraídos.
    """
    # Monta o estado inicial para a pipeline LangGraph
    initial_state = {
        "cert_nr10_url": str(payload.cert_nr10_url),  # Converte HttpUrl para string
        "cert_nr35_url": str(payload.cert_nr35_url),
        "current_date": date.today().isoformat(),  # Data de referência (YYYY-MM-DD)
    }

    try:
        # Executa a pipeline de validação de forma assíncrona
        result = await compiled_graph.ainvoke(initial_state)
    except Exception as e:
        # Loga o traceback completo e retorna erro genérico ao cliente
        logger.exception("Certificate validation pipeline failed")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno na pipeline de validação: {e}",
        )

    # Monta a resposta a partir do resultado da pipeline
    return CertificateValidationResponse(
        status=result.get("status", "REJECTED"),  # Default: REJECTED (fail-safe)
        reason=result.get("reason", "Erro desconhecido na validação."),
        error_code=result.get("error_code"),
        extracted_data=result.get("extracted_data"),
    )
