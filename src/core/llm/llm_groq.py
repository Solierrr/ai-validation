"""
Factory do cliente Groq (fallback do Gemini).
"""

import os

from ai_lib.llm import LeasedChatModel, get_chat_model

from src.core.config.settings import get_settings
from src.core.llm.keys import key_client

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def get_groq_llm() -> LeasedChatModel:
    """Cria o cliente Groq; a chave vem de GROQ_API_KEY."""
    return get_chat_model(
        "groq",
        model=os.getenv("LLM_MODEL_GROQ") or DEFAULT_GROQ_MODEL,
        temperature=get_settings().LLM_TEMPERATURE,
        client=key_client(),
        timeout=60,
    )
