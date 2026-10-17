"""
Invocação de LLM com fallback automático entre provedores.
"""

import logging

from ai_lib.llm import provider_order

from src.core.llm.keys import key_client
from src.core.llm.llm_groq import get_groq_llm
from src.core.llm.llm_openai import get_openai_llm

logger = logging.getLogger(__name__)

# Groq só suporta texto; Gemini e OpenAI aceitam imagens (Vision).
TEXT_ONLY_PROVIDERS = {"groq"}


def _is_rate_limit_error(error: Exception) -> bool:
    """Verifica se o erro é de rate limit (429)."""
    error_str = str(error)
    return "429" in error_str or "RESOURCE_EXHAUSTED" in error_str


def _fallback_providers(allow_groq_fallback: bool) -> list[str]:
    key_client()
    order = provider_order() or ["groq"]
    providers = [provider for provider in order if provider != "gemini"]
    if not allow_groq_fallback:
        providers = [provider for provider in providers if provider not in TEXT_ONLY_PROVIDERS]
    return providers


def _build_llm(provider: str):
    return {"groq": get_groq_llm, "openai": get_openai_llm}[provider]()


def invoke_llm_with_retry(structured_llm, messages, output_schema=None, allow_groq_fallback=True):
    """
    Invoca o LLM com fallback automático.

    Ordem de tentativas:
    1. Gemini (o `structured_llm` recebido)
    2. Os demais provedores de LLM_PROVIDER_ORDER, na ordem (Groq e/ou OpenAI)

    Só erros de rate limit (429) passam ao próximo provedor; os demais propagam.

    Args:
        structured_llm: LLM já configurado com .with_structured_output()
        messages: Lista de mensagens para enviar ao modelo.
        output_schema: Classe Pydantic do output (para recriar com outro provedor).
        allow_groq_fallback: Se False, não tenta provedores só de texto (usar para imagens).
    """
    try:
        return structured_llm.invoke(messages)
    except Exception as e:
        if not _is_rate_limit_error(e):
            raise
        logger.warning("Gemini atingiu rate limit.")

    for provider in _fallback_providers(allow_groq_fallback):
        try:
            logger.info("Tentando %s...", provider)
            llm = _build_llm(provider)
            candidate = llm.with_structured_output(output_schema) if output_schema else llm
            return candidate.invoke(messages)
        except Exception as err:
            if not _is_rate_limit_error(err):
                raise
            logger.warning("%s também atingiu rate limit.", provider)

    raise Exception(
        "Todos os provedores atingiram rate limit e não há fallback disponível. "
        "Tente novamente em alguns minutos."
    )
