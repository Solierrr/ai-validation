"""
Invocação de LLM com fallback automático entre múltiplas API keys/provedores.
"""

import logging

from src.core.config.settings import get_settings
from src.core.llm.llm_gemini import get_llm
from src.core.llm.llm_groq import get_groq_llm

logger = logging.getLogger(__name__)


def _is_rate_limit_error(error: Exception) -> bool:
    """Verifica se o erro é de rate limit (429)."""
    error_str = str(error)
    return "429" in error_str or "RESOURCE_EXHAUSTED" in error_str


def invoke_llm_with_retry(structured_llm, messages, output_schema=None, allow_groq_fallback=True):
    """
    Invoca o LLM com fallback automático.

    Ordem de tentativas:
    1. Gemini (key principal)
    2. Gemini (key 2, se configurada)
    3. Groq Llama 3.3 70B (apenas se allow_groq_fallback=True e mensagens são texto)

    Args:
        structured_llm: LLM já configurado com .with_structured_output()
        messages: Lista de mensagens para enviar ao modelo.
        output_schema: Classe Pydantic do output (para recriar com outra key/provider).
        allow_groq_fallback: Se False, não tenta Groq (usar para chamadas com imagens).
    """
    settings = get_settings()

    # ─── Tentativa 1: Gemini key principal ───────────────────────────────────
    try:
        return structured_llm.invoke(messages)
    except Exception as e:
        if not _is_rate_limit_error(e):
            raise
        logger.warning("Gemini key principal atingiu rate limit.")

    # ─── Tentativa 2: Gemini keys alternativas (sem retry, 1 tentativa cada) ─
    fallback_keys = settings.api_keys[1:]
    for i, key in enumerate(fallback_keys, start=2):
        try:
            logger.info("Tentando Gemini key %d...", i)
            fallback_llm = get_llm(api_key=key)
            if output_schema:
                fallback_structured = fallback_llm.with_structured_output(output_schema)
            else:
                fallback_structured = fallback_llm
            return fallback_structured.invoke(messages)
        except Exception as fallback_err:
            if not _is_rate_limit_error(fallback_err):
                raise
            logger.warning("Gemini key %d também atingiu rate limit.", i)

    # ─── Tentativa final: Groq (Llama 3.3 70B) ──────────────────────────────
    # Groq só suporta texto — não funciona com imagens (Vision)
    groq_keys = settings.groq_keys
    if allow_groq_fallback and groq_keys:
        for j, groq_key in enumerate(groq_keys, start=1):
            try:
                logger.info("Tentando Groq key %d...", j)
                groq_llm = get_groq_llm(api_key=groq_key)
                if output_schema:
                    groq_structured = groq_llm.with_structured_output(output_schema)
                else:
                    groq_structured = groq_llm
                return groq_structured.invoke(messages)
            except Exception as groq_err:
                if not _is_rate_limit_error(groq_err):
                    raise
                logger.warning("Groq key %d também atingiu rate limit.", j)

    # Nenhum fallback disponível
    raise Exception(
        "Todas as API keys atingiram rate limit e não há fallback disponível. "
        "Tente novamente em alguns minutos."
    )
