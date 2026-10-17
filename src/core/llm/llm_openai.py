"""
Factory do cliente OpenAI (fallback com Vision).
"""

from ai_lib.llm import LeasedChatModel, get_chat_model

from src.core.config.settings import get_settings
from src.core.llm.keys import key_client


def get_openai_llm() -> LeasedChatModel:
    """Cria o cliente OpenAI; chave em OPENAI_API_KEY e modelo em LLM_MODEL_OPENAI (ex.: gpt-6-luna)."""
    return get_chat_model(
        "openai",
        temperature=get_settings().LLM_TEMPERATURE,
        client=key_client(),
        timeout=60,
    )
