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

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.auth import require_access_token
from src.api.errors import ApiError
from src.api.schemas.cnpj_schemas import CNPJValidationRequest, CNPJValidationResponse
from src.api.schemas.problem_schemas import problem_responses
from src.agents.specialist.cnpj_agent.cnpj_agent import analyze_company
from src.services.brasil_api import fetch_cnpj_data

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/api/v1", tags=["Empresas"], dependencies=[Depends(require_access_token)]
)



def _sanitize_cnpj(cnpj: str) -> str:
    """Remove tudo que não é dígito do CNPJ."""
    return re.sub(r"\D", "", cnpj)


@router.post(
    "/companies/validate-cnpj",
    response_model=CNPJValidationResponse,
    summary="Valida o CNPJ de uma empresa parceira",
    description=(
        "Recebe um CNPJ, consulta os dados da Receita Federal pela BrasilAPI e usa um agente "
        "de IA para avaliar se as atividades da empresa são compatíveis com o setor de energia "
        "solar e elétrica. CNPJ reprovado é resultado (status INVALID com error_code), não erro "
        "HTTP. Exige o JWT do usuário, emitido pelo api-auth, e é limitada a 20 requisições por minuto por IP."
    ),
    operation_id="validateCnpj",
    responses=problem_responses(401, 422, 429, 500, 502),
    openapi_extra={
        "x-error-codes": [
            "VALIDATION_FAILED",
            "RATE_LIMITED",
            "INTERNAL_ERROR",
            "DEPENDENCY_UNAVAILABLE",
        ],
    },
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
    return await run_cnpj_validation(payload)


async def run_cnpj_validation(
    payload: CNPJValidationRequest,
) -> CNPJValidationResponse:
    """Executa o fluxo de validação; compartilhado com a rota de debug."""
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
        raise ApiError(502, "DEPENDENCY_UNAVAILABLE", "Erro ao consultar dados do CNPJ na Receita Federal.") from e

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
        raise ApiError(500, "INTERNAL_ERROR", "Erro interno na análise de compatibilidade da empresa.") from e

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
