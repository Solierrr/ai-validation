"""
Agente auditor de CNPJ.

Analisa os CNAEs (atividades econômicas) de uma empresa e determina
se ela é compatível com o setor de energia solar/elétrica/engenharia.
Usa LLM com structured output para retornar a decisão.
"""

import logging
from typing import Any, Dict

from src.api.cnpj_schemas import CompanyLLMAuditOutput
from src.core.llm import get_llm, invoke_llm_with_retry

logger = logging.getLogger(__name__)

# ─── Prompt do sistema para o agente auditor de CNPJ ─────────────────────────
CNPJ_AUDIT_PROMPT = """Você é um auditor corporativo especializado no mercado de energia e engenharia no Brasil.
Sua missão é determinar se a empresa analisada possui autorização/ramo de atividade compatível para atuar na venda, projeto, instalação, manutenção ou suporte de sistemas de energia solar fotovoltaica e elétrica.

DADOS DA EMPRESA (EXTRAÍDOS DA RECEITA FEDERAL):
- Razão Social: {razao_social}
- Nome Fantasia: {nome_fantasia}
- CNAE Principal: {cnae_principal_codigo} - {cnae_principal_descricao}
- CNAEs Secundários:
{lista_cnaes_secundarios}

REGRAS DE AVALIAÇÃO:
1. APROVE (is_compatible = true) se a empresa possuir pelo menos UMA atividade relacionada a:
   - Energia Solar, Fotovoltaica ou Fontes Renováveis.
   - Engenharia (Elétrica, Civil, Mecânica ou Geral).
   - Instalações, Montagens, Manutenção Elétrica ou Hidráulica.
   - Comércio (Atacadista ou Varejista) de Materiais Elétricos, Equipamentos Eletrônicos, Máquinas ou Ferramentas.
   - Serviços de Arquitetura, Climatização, Refrigeração ou Obras de Alvenaria/Telhado.
   - Treinamentos Técnicos ou Desenvolvimento Profissional.

2. REJEITE (is_compatible = false) se a empresa for exclusivamente de ramos sem correlação técnica, tais como:
   - Alimentação (Lanchonetes, Restaurantes, Padarias, Bares).
   - Saúde, Odontologia e Farmácias.
   - Vestuário, Calçados e Beleza.
   - Transporte de Passageiros, Pet Shops, Supermercados ou Consultorias Jurídicas/Contábeis puras.

RESPOSTA ESPERADA (JSON STRICT):
{{
  "is_compatible": boolean,
  "category_label": string,
  "justification": string
}}"""


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
