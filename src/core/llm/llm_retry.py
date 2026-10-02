"""
Invocação de LLM com fallback para o Groq quando as chaves Gemini se esgotam.

O rodízio entre chaves do mesmo provedor é feito pelo google-registry: cada
chamada do LLM pede uma chave ao corretor, avisa o resultado e, em rate limit,
repete com outra chave.
"""

import logging

from ai_lib.llm import classify_key_failure
from ai_lib.registry import RegistryKeysUnavailable

from src.core.llm.llm_groq import get_groq_llm

logger = logging.getLogger(__name__)


def _is_key_exhausted_error(error: Exception) -> bool:
    """Verifica se as chaves do provedor se esgotaram (rate limit ou nenhuma disponível)."""
    if isinstance(error, RegistryKeysUnavailable):
        return True
    failure = classify_key_failure(error)
    return failure is not None and failure.outcome == "rate_limited"


def invoke_llm_with_retry(
    structured_llm, messages, output_schema=None, allow_groq_fallback=True
):
    """
    Invoca o LLM com fallback para o Groq.

    Ordem de tentativas:
    1. Gemini (chave entregue pelo corretor, com rodízio de chaves interno)
    2. Groq (apenas se allow_groq_fallback=True, output_schema informado e
       as chaves Gemini se esgotaram)

    Args:
        structured_llm: LLM já configurado com .with_structured_output()
        messages: Lista de mensagens para enviar ao modelo.
        output_schema: Classe Pydantic do output (para recriar no Groq).
        allow_groq_fallback: Se False, não tenta Groq (usar para chamadas com imagens).
    """
    try:
        return structured_llm.invoke(messages)
    except Exception as error:
        if not (
            allow_groq_fallback and output_schema and _is_key_exhausted_error(error)
        ):
            raise
        logger.warning("Chaves Gemini esgotadas, tentando Groq.")

    return get_groq_llm().with_structured_output(output_schema).invoke(messages)
