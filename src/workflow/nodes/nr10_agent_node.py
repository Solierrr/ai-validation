"""
Nó do agente especialista NR-10 (Segurança em Instalações Elétricas) na pipeline LangGraph.

Responsável por analisar a imagem do certificado NR-10 usando LLM Vision
e extrair dados estruturados como nome do aluno, carga horária, etc.
"""

import base64
import logging
from typing import Any, Dict

import httpx
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.agents.specialist.nr10_agent.nr10_agent_prompt import NR10_SYSTEM_PROMPT
from src.core.llm.llm_gemini import get_llm
from src.core.llm.llm_retry import invoke_llm_with_retry

logger = logging.getLogger(__name__)


# ─── Schema de saída estruturada ─────────────────────────────────────────────
# O LLM é forçado a retornar neste formato exato (Pydantic valida o output).
class NRAgentOutput(BaseModel):
    """Schema de saída do agente NR-10."""

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


def nr10_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nó do agente NR-10 na pipeline LangGraph.

    Fluxo:
    1. Tenta usar imagem cacheada do security guardrail (evita re-download).
    2. Se cache não disponível, faz download da URL.
    3. Envia imagem ao Gemini Vision com prompt de validação NR-10.
    4. Retorna dados extraídos de forma estruturada.
    """
    # ─── Obter imagem (cache ou download) ────────────────────────────────────
    # Primeiro tenta usar o cache salvo pelo security guardrail no state
    b64_data = state.get("cert_nr10_b64")
    mime_type = state.get("cert_nr10_mime")

    # Se não há cache, faz o download (fallback)
    if not b64_data:
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(state["cert_nr10_url"])
                response.raise_for_status()

            content_type = response.headers.get("content-type", "image/jpeg")
            mime_type = content_type.split(";")[0].strip()
            b64_data = base64.b64encode(response.content).decode("utf-8")
        except Exception as e:
            # Se falhar o download, retorna erro sem chamar o LLM
            logger.error("Failed to download NR-10 certificate: %s", e)
            return {
                "nr10_result": {
                    "valid": False,
                    "error_code": "ILLEGIBLE_DOCUMENT",
                    "error_reason": f"Não foi possível baixar a imagem do certificado NR-10: {e}",
                    "student_name": None,
                    "institution_name": None,
                    "workload_hours": None,
                    "issue_date": None,
                    "has_required_structure": False,
                }
            }

    # ─── Preparar e invocar o LLM Vision ─────────────────────────────────────
    # Injeta a data atual no prompt para que o LLM calcule expiração
    system_prompt = NR10_SYSTEM_PROMPT.format(current_date=state["current_date"])

    llm = get_llm()
    # with_structured_output força o retorno no formato NRAgentOutput
    structured_llm = llm.with_structured_output(NRAgentOutput)

    # Monta mensagem multimodal: texto instrucional + imagem em base64
    message = HumanMessage(
        content=[
            {"type": "text", "text": "Analise o certificado NR-10 a seguir:"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
            },
        ]
    )

    try:
        # Invoca com retry e fallback entre API keys
        # allow_groq_fallback=False porque envia imagens (Groq não suporta Vision)
        result: NRAgentOutput = invoke_llm_with_retry(
            structured_llm,
            [
                {"role": "system", "content": system_prompt},
                message,
            ],
            output_schema=NRAgentOutput,
            allow_groq_fallback=False,
        )
    except Exception as e:
        # Após 3 falhas, retorna erro estruturado
        logger.error("NR-10 agent LLM call failed: %s", e)
        return {
            "nr10_result": {
                "valid": False,
                "error_code": "ILLEGIBLE_DOCUMENT",
                "error_reason": f"Erro ao processar o certificado NR-10: {e}",
                "student_name": None,
                "institution_name": None,
                "workload_hours": None,
                "issue_date": None,
                "has_required_structure": False,
            }
        }

    # Converte o Pydantic model para dict e salva no state
    return {
        "nr10_result": result.model_dump(),
    }
