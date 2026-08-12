"""
Factory do cliente Gemini (LLM principal).
"""

from langchain_google_genai import ChatGoogleGenerativeAI

from src.core.config.settings import get_settings


def get_llm(api_key: str = None) -> ChatGoogleGenerativeAI:
    """Cria uma instância do Gemini configurada."""
    settings = get_settings()
    key = api_key or settings.GEMINI_API_KEY
    return ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        google_api_key=key,
        timeout=60,
    )
