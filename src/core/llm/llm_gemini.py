"""
Factory do cliente Gemini (LLM principal).
"""

import os

from ai_lib.llm import LeasedChatModel, get_chat_model

from src.core.config.settings import get_settings
from src.core.llm.keys import key_client


def get_llm() -> LeasedChatModel:
    """Cria o cliente Gemini; a chave vem de GEMINI_API_KEY."""
    settings = get_settings()
    return get_chat_model(
        "gemini",
        model=os.getenv("LLM_MODEL_GEMINI") or settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        client=key_client(),
        timeout=60,
    )
