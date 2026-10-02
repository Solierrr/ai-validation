"""
Factory do cliente Gemini (LLM principal).
"""

from ai_lib.llm import LeasedChatModel, get_chat_model

from src.core.config.settings import get_settings
from src.core.llm.registry import registry_client


def get_llm() -> LeasedChatModel:
    """Cria o Gemini configurado; a chave é pedida ao corretor a cada chamada."""
    settings = get_settings()
    return get_chat_model(
        "gemini",
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        purpose="vision",
        client=registry_client(),
        timeout=60,
    )
