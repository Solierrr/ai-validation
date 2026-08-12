"""
Nó do agente de segurança (Security Guardrail) na pipeline LangGraph.

Primeiro nó da pipeline — atua como barreira de segurança antes dos agentes
especialistas. Utiliza LLM Vision para detectar:
- Prompt injection (instruções ocultas para manipular a IA)
- Documentos ilegíveis (imagem em branco, selfie, arquivo corrompido)
- Edições digitais que tentam sobrescrever instruções do sistema

Se detectar risco, marca is_safe=False e a pipeline pula direto para
a consolidation (rejeição imediata, sem processar os certificados).

Também é responsável por fazer o download das imagens e cacheá-las
no state para que os agentes NR-10 e NR-35 não precisem baixar novamente.
"""

import logging
from typing import Any, Dict

import httpx
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.agents.specialist.security_guardrail.security_guardrail_prompt import (
    SECURITY_SYSTEM_PROMPT,
)
from src.core.llm.llm_gemini import get_llm
from src.core.llm.llm_retry import invoke_llm_with_retry

logger = logging.getLogger(__name__)


class GuardrailOutput(BaseModel):
    """Schema de saída estruturada do agente de segurança."""

    is_safe: bool = Field(description="Indica se as imagens são seguras e válidas")
    security_error_code: str | None = Field(
        default=None,
        description="Código de erro de segurança, se houver",
    )
    security_reason: str | None = Field(
        default=None,
        description="Razão da rejeição por segurança, se houver",
    )


def _download_image(url: str) -> tuple[str, str]:
    """
    Faz download de uma imagem a partir de uma URL.

    Args:
        url: URL pública da imagem do certificado.

    Returns:
        Tupla (base64_data, mime_type) para envio ao LLM Vision.

    Raises:
        httpx.HTTPStatusError: Se o download falhar (4xx/5xx).
        httpx.TimeoutException: Se exceder 30 segundos.
    """
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()

    # Extrai o MIME type do header Content-Type (ex: "image/jpeg; charset=utf-8" → "image/jpeg")
    content_type = response.headers.get("content-type", "image/jpeg")
    mime_type = content_type.split(";")[0].strip()

    # Converte bytes da imagem para base64 (formato esperado pelo Gemini Vision)
    import base64
    b64_data = base64.b64encode(response.content).decode("utf-8")
    return b64_data, mime_type


def security_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nó do security guardrail na pipeline LangGraph.

    Fluxo:
    1. Faz download das duas imagens (NR-10 e NR-35).
    2. Envia ambas ao Gemini Vision com o prompt de segurança.
    3. Retorna is_safe + cache das imagens em base64 no state.

    Se is_safe=False, a pipeline pula direto para consolidation.
    Se is_safe=True, as imagens cacheadas são reutilizadas pelos agentes.
    """
    # ─── Download das imagens ────────────────────────────────────────────────
    try:
        nr10_b64, nr10_mime = _download_image(state["cert_nr10_url"])
        nr35_b64, nr35_mime = _download_image(state["cert_nr35_url"])
    except Exception as e:
        logger.error("Failed to download certificate images: %s", e)
        return {
            "is_safe": False,
            "security_error_code": "ILLEGIBLE_DOCUMENT",
            "security_reason": f"Não foi possível baixar as imagens dos certificados: {e}",
            "cert_nr10_b64": None,
            "cert_nr10_mime": None,
            "cert_nr35_b64": None,
            "cert_nr35_mime": None,
        }

    # ─── Chamada ao LLM Vision para análise de segurança ─────────────────────
    llm = get_llm()
    # with_structured_output força o LLM a retornar no formato do GuardrailOutput
    structured_llm = llm.with_structured_output(GuardrailOutput)

    # Monta mensagem multimodal: texto + 2 imagens em base64
    message = HumanMessage(
        content=[
            {"type": "text", "text": "Certificado 1 (NR-10):"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{nr10_mime};base64,{nr10_b64}"},
            },
            {"type": "text", "text": "Certificado 2 (NR-35):"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{nr35_mime};base64,{nr35_b64}"},
            },
        ]
    )

    try:
        # Invoca o LLM com fallback entre API keys se der rate limit
        # allow_groq_fallback=False porque envia imagens (Groq não suporta Vision)
        result: GuardrailOutput = invoke_llm_with_retry(
            structured_llm,
            [
                {"role": "system", "content": SECURITY_SYSTEM_PROMPT},
                message,
            ],
            output_schema=GuardrailOutput,
            allow_groq_fallback=False,
        )
    except Exception as e:
        # Em caso de falha total do LLM, assume que não é seguro (fail-safe)
        logger.error("Security guardrail LLM call failed: %s", e)
        return {
            "is_safe": False,
            "security_error_code": "SECURITY_RISK",
            "security_reason": f"Erro ao processar verificação de segurança: {e}",
        }

    # Retorna resultado + cache das imagens para os próximos nós
    return {
        "is_safe": result.is_safe,
        "security_error_code": result.security_error_code,
        "security_reason": result.security_reason,
        # Cache: evita que NR-10 agent e NR-35 agent baixem as imagens novamente
        "cert_nr10_b64": nr10_b64,
        "cert_nr10_mime": nr10_mime,
        "cert_nr35_b64": nr35_b64,
        "cert_nr35_mime": nr35_mime,
    }
