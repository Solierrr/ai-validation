"""
Agente auditor de CNPJ.

Analisa os CNAEs (atividades econômicas) de uma empresa e determina
se ela é compatível com o setor de energia solar/elétrica/engenharia.
Usa LLM com structured output para retornar a decisão.
"""

import logging
from typing import Any, Dict

from src.agents.specialist.cnpj_agent.cnpj_agent_prompt import CNPJ_AUDIT_PROMPT
from src.api.schemas.cnpj_schemas import CompanyLLMAuditOutput
from src.core.llm.llm_gemini import get_llm
from src.core.llm.llm_retry import invoke_llm_with_retry

logger = logging.getLogger(__name__)


def _format_cnaes_secundarios(cnaes: list) -> str:
    """Formata a lista de CNAEs secundários para o prompt."""
    if not cnaes:
        return "  (Nenhum CNAE secundário registrado)"
    lines = []
    for cnae in cnaes:
        codigo = cnae.get("codigo", "N/A")
        descricao = cnae.get("descricao", "Descrição não disponível")
        lines.append(f"  - {codigo} - {descricao}")
    return "\n".join(lines)


def analyze_company(company_data: Dict[str, Any]) -> CompanyLLMAuditOutput:
    """
    Analisa os CNAEs de uma empresa usando o LLM.

    Args:
        company_data: Dict com dados da BrasilAPI (razao_social, cnaes, etc.)

    Returns:
        CompanyLLMAuditOutput com is_compatible, category_label e justification.
    """
    # Extrai dados relevantes da resposta da BrasilAPI
    razao_social = company_data.get("razao_social", "Não informada")
    nome_fantasia = company_data.get("nome_fantasia") or "Não informado"

    # CNAE principal
    cnae_fiscal = company_data.get("cnae_fiscal", "")
    cnae_fiscal_descricao = company_data.get("cnae_fiscal_descricao", "")

    # CNAEs secundários (lista de dicts com "codigo" e "descricao")
    cnaes_secundarios = company_data.get("cnaes_secundarios", [])
    lista_formatada = _format_cnaes_secundarios(cnaes_secundarios)

    # Monta o prompt com os dados da empresa
    prompt = CNPJ_AUDIT_PROMPT.format(
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        cnae_principal_codigo=cnae_fiscal,
        cnae_principal_descricao=cnae_fiscal_descricao,
        lista_cnaes_secundarios=lista_formatada,
    )

    # Invoca o LLM com structured output e retry
    llm = get_llm()
    structured_llm = llm.with_structured_output(CompanyLLMAuditOutput)

    result: CompanyLLMAuditOutput = invoke_llm_with_retry(
        structured_llm,
        [{"role": "user", "content": prompt}],
        output_schema=CompanyLLMAuditOutput,
    )

    return result
