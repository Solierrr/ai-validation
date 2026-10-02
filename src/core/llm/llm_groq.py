"""
Factory do cliente Groq (fallback do Gemini).
"""

from ai_lib.llm import LeasedChatModel, get_chat_model

from src.core.config.settings import get_settings
from src.core.llm.registry import registry_client

GROQ_MODEL = "openai/gpt-oss-120b"


def get_groq_llm() -> LeasedChatModel:
    """Cria o Groq como fallback; a chave é pedida ao corretor a cada chamada."""
    settings = get_settings()
    return get_chat_model(
        "groq",
        model=GROQ_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        client=registry_client(),
        timeout=60,
    )
