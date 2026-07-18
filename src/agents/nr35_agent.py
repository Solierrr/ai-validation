"""
Agente especialista NR-35 (Trabalho em Altura).

Responsável por analisar a imagem do certificado NR-35 usando LLM Vision
e extrair dados estruturados como nome do aluno, carga horária, etc.
Estrutura idêntica ao NR-10 agent, com regras específicas da NR-35.
"""

import base64
import logging
from typing import Any, Dict

import httpx
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.core.llm import get_llm, invoke_llm_with_retry

logger = logging.getLogger(__name__)


# ─── Prompt do sistema para o agente NR-35 ───────────────────────────────────
# Diferenças em relação ao NR-10:
# - Carga horária mínima: 8h (NR-10 é 20h)
# - Conteúdo: deve ser sobre NR-35 ou Trabalho em Altura
NR35_SYSTEM_PROMPT = """Você é um auditor especialista em regulamentação de segurança do trabalho focado na norma NR-35.
Analise a imagem da NR-35 com base na data de referência do sistema: {current_date}.

ESTRUTURA MÍNIMA OBRIGATÓRIA:
1. Cabeçalho/Título claro (ex: "Certificado", "Atestado de Conclusão").
2. Nome completo do aluno/técnico.
3. Nome da instituição/emissor (com CNPJ, logo ou assinatura).
4. Carga Horária expressa em horas.
5. Data de emissão ou conclusão.
6. Assinatura do instrutor/responsável técnico ou selo da instituição.

REGRAS ESPECÍFICAS DE NR-35:
- O curso deve ser explicitamente sobre NR-35 ou Trabalho em Altura.
- A data de emissão não pode ter mais de 24 meses em relação a {current_date}.
- CARGA HORÁRIA MÍNIMA: O valor extraído de horas DEVE ser de no mínimo 8h. Cargas horárias inferiores a 8h são INVÁLIDAS.

RETORNO ESPERADO (JSON STRICT):
{{
  "valid": boolean,
  "error_code": string | null,
  "error_reason": string | null,
  "student_name": string | null,
  "institution_name": string | null,
  "workload_hours": number | null,
  "issue_date": "YYYY-MM-DD" | null,
  "has_required_structure": boolean
}}"""


# ─── Schema de saída estruturada ─────────────────────────────────────────────
class NR35AgentOutput(BaseModel):
    """Schema de saída do agente NR-35."""

    valid: bool = Field(description="Indica se o certificado atende a todos os critérios")
    error_code: str | None = Field(
        default=None,
        description="Código de erro (ex: INSUFFICIENT_WORKLOAD, EXPIRED_CERTIFICATE, MISSING_STRUCTURE)",
    )
    error_reason: str | None = Field(
        default=None,
        description="Descrição do motivo da rejeição",
    )
    student_name: str | None = Field(
        default=None,
        description="Nome completo do aluno/técnico extraído do certificado",
    )
    institution_name: str | None = Field(
        default=None,
        description="Nome da instituição emissora",
    )
    workload_hours: int | None = Field(
        default=None,
        description="Número de horas da carga horária (apenas o número)",
    )
    issue_date: str | None = Field(
        default=None,
        description="Data de emissão no formato YYYY-MM-DD",
    )
    has_required_structure: bool = Field(
        description="Se possui a estrutura mínima de 6 pontos obrigatórios",
    )


def nr35_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nó do agente NR-35 na pipeline LangGraph.

    Fluxo idêntico ao NR-10 agent:
    1. Tenta usar imagem cacheada do security guardrail.
    2. Se cache não disponível, faz download da URL.
    3. Envia imagem ao Gemini Vision com prompt de validação NR-35.
    4. Retorna dados extraídos de forma estruturada.
    """
    # ─── Obter imagem (cache ou download) ────────────────────────────────────
    b64_data = state.get("cert_nr35_b64")
    mime_type = state.get("cert_nr35_mime")

    if not b64_data:
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(state["cert_nr35_url"])
                response.raise_for_status()

            content_type = response.headers.get("content-type", "image/jpeg")
            mime_type = content_type.split(";")[0].strip()
            b64_data = base64.b64encode(response.content).decode("utf-8")
        except Exception as e:
            logger.error("Failed to download NR-35 certificate: %s", e)
            return {
                "nr35_result": {
                    "valid": False,
                    "error_code": "ILLEGIBLE_DOCUMENT",
                    "error_reason": f"Não foi possível baixar a imagem do certificado NR-35: {e}",
                    "student_name": None,
                    "institution_name": None,
                    "workload_hours": None,
                    "issue_date": None,
                    "has_required_structure": False,
                }
            }

    # ─── Preparar e invocar o LLM Vision ─────────────────────────────────────
    system_prompt = NR35_SYSTEM_PROMPT.format(current_date=state["current_date"])

    llm = get_llm()
    structured_llm = llm.with_structured_output(NR35AgentOutput)

    message = HumanMessage(
        content=[
            {"type": "text", "text": "Analise o certificado NR-35 a seguir:"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
            },
        ]
    )

    try:
        # allow_groq_fallback=False porque envia imagens (Groq não suporta Vision)
        result: NR35AgentOutput = invoke_llm_with_retry(
            structured_llm,
            [
                {"role": "system", "content": system_prompt},
                message,
            ],
            output_schema=NR35AgentOutput,
            allow_groq_fallback=False,
        )
    except Exception as e:
        logger.error("NR-35 agent LLM call failed: %s", e)
        return {
            "nr35_result": {
                "valid": False,
                "error_code": "ILLEGIBLE_DOCUMENT",
                "error_reason": f"Erro ao processar o certificado NR-35: {e}",
                "student_name": None,
                "institution_name": None,
                "workload_hours": None,
                "issue_date": None,
                "has_required_structure": False,
            }
        }

    # Converte o Pydantic model para dict e salva no state
    return {
        "nr35_result": result.model_dump(),
    }
