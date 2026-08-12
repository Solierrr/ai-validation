"""
Nó do agente especialista NR-35 (Trabalho em Altura) na pipeline LangGraph.

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

from src.agents.specialist.nr35_agent.nr35_agent_prompt import NR35_SYSTEM_PROMPT
from src.core.llm.llm_gemini import get_llm
from src.core.llm.llm_retry import invoke_llm_with_retry

logger = logging.getLogger(__name__)


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
