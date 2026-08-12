"""
Rota de validação de CNPJ para empresas parceiras.

Endpoint POST /api/v1/companies/validate-cnpj que:
1. Sanitiza o CNPJ (remove pontuação)
2. Consulta a BrasilAPI para obter dados cadastrais
3. Verifica se o CNPJ está ativo
4. Usa agente de IA para avaliar compatibilidade dos CNAEs
"""

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.schemas.cnpj_schemas import CNPJValidationRequest, CNPJValidationResponse
from src.agents.specialist.cnpj_agent.cnpj_agent import analyze_company
from src.services.brasil_api import fetch_cnpj_data

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/v1", tags=["companies"])


def _sanitize_cnpj(cnpj: str) -> str:
    """Remove tudo que não é dígito do CNPJ."""
    return re.sub(r"\D", "", cnpj)


@router.post(
    "/companies/validate-cnpj",
    response_model=CNPJValidationResponse,
    summary="Validate company CNPJ for partner registration",
    description=(
        "Receives a CNPJ, queries the Brazilian Federal Revenue database, "
        "and uses an AI agent to determine if the company's economic "
        "activities are compatible with the solar/electrical sector."
    ),
)
@limiter.limit("20/minute")
async def validate_cnpj(
    request: Request,
    payload: CNPJValidationRequest,
) -> CNPJValidationResponse:
    """
    Endpoint de validação de CNPJ.

    Fluxo:
    1. Sanitiza o CNPJ (remove pontos, traços, barras).
    2. Valida se tem 14 dígitos.
    3. Consulta BrasilAPI para dados cadastrais.
    4. Verifica se está ativo na Receita Federal.
    5. Envia CNAEs ao agente de IA para análise de compatibilidade.
    6. Retorna VALID ou INVALID com detalhes.
    """
    # ─── 1. Sanitização ──────────────────────────────────────────────────────
    cnpj_clean = _sanitize_cnpj(payload.cnpj)

    # Valida formato: deve ter exatamente 14 dígitos
    if len(cnpj_clean) != 14:
        return CNPJValidationResponse(
            status="INVALID",
            cnpj=cnpj_clean,
            is_active=False,
            error_code="INVALID_CNPJ_FORMAT",
            reason="O CNPJ fornecido não possui 14 dígitos válidos após a limpeza dos caracteres.",
        )

    # ─── 2. Consulta BrasilAPI ───────────────────────────────────────────────
    try:
        company_data = await fetch_cnpj_data(cnpj_clean)
    except Exception as e:
        logger.error("BrasilAPI request failed for CNPJ %s: %s", cnpj_clean, e)
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar dados do CNPJ na Receita Federal: {e}",
        )

    # CNPJ não encontrado
    if company_data is None:
        return CNPJValidationResponse(
            status="INVALID",
            cnpj=cnpj_clean,
            is_active=False,
            error_code="CNPJ_NOT_FOUND",
            reason="O CNPJ informado não foi localizado na base de dados da Receita Federal.",
        )

    # Extrai dados básicos
    company_name = company_data.get("razao_social")
    trade_name = company_data.get("nome_fantasia") or None
    situacao = (company_data.get("descricao_situacao_cadastral") or "").upper()

    # ─── 3. Verifica situação cadastral ──────────────────────────────────────
    is_active = situacao == "ATIVA"

    if not is_active:
        return CNPJValidationResponse(
            status="INVALID",
            cnpj=cnpj_clean,
            company_name=company_name,
            trade_name=trade_name,
            is_active=False,
            error_code="CNPJ_INACTIVE",
            reason=f"O CNPJ informado não está ativo na Receita Federal (Situação: {situacao}).",
        )

    # ─── 4. Análise de compatibilidade via agente de IA ──────────────────────
    try:
        audit_result = analyze_company(company_data)
    except Exception as e:
        logger.error("CNPJ agent failed for %s: %s", cnpj_clean, e)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno na análise de compatibilidade: {e}",
        )

    # ─── 5. Monta resposta final ─────────────────────────────────────────────
    if audit_result.is_compatible:
        return CNPJValidationResponse(
            status="VALID",
            cnpj=cnpj_clean,
            company_name=company_name,
            trade_name=trade_name,
            is_active=True,
            matched_category=audit_result.category_label,
            reason=audit_result.justification,
        )
    else:
        return CNPJValidationResponse(
            status="INVALID",
            cnpj=cnpj_clean,
            company_name=company_name,
            trade_name=trade_name,
            is_active=True,
            error_code="INVALID_COMPANY_CATEGORY",
            reason=audit_result.justification,
        )
