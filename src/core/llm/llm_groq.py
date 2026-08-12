"""
Factory do cliente Groq (fallback do Gemini).
"""

from langchain_groq import ChatGroq

from src.core.config.settings import get_settings


def get_groq_llm(api_key: str = None) -> ChatGroq:
    """Cria uma instância do Groq (Llama 3.3 70B) como fallback."""
    settings = get_settings()
    key = api_key or settings.GROQ_API_KEY
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=settings.LLM_TEMPERATURE,
        api_key=key,
        timeout=60,
    )
