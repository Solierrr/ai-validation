"""
Módulo de configuração da aplicação.

Utiliza pydantic-settings para carregar variáveis de ambiente do arquivo .env
e disponibilizá-las de forma tipada e validada para o restante do projeto.
"""

from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Configurações da aplicação carregadas a partir de variáveis de ambiente.

    Suporta múltiplas API keys do Gemini para fallback automático
    quando uma key atinge o rate limit.
    """

    GEMINI_API_KEY: str  # Chave principal (obrigatória)
    GEMINI_API_KEY2: Optional[str] = None  # Fallback Gemini 2
    GEMINI_API_KEY3: Optional[str] = None  # Fallback Gemini 3
    GROQ_API_KEY: Optional[str] = None  # Fallback Groq 1
    GROQ_API_KEY2: Optional[str] = None  # Fallback Groq 2

    LLM_MODEL: str = "gemini-2.5-flash"  # Modelo atual com Vision e boa relação custo/performance
    LLM_TEMPERATURE: float = 0.0  # Temperatura 0 = output determinístico

    # Configuração do pydantic-settings: lê do arquivo .env na raiz do projeto
    # extra="ignore" permite ter variáveis extras no .env sem causar erro
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def api_keys(self) -> list[str]:
        """Retorna lista de API keys Gemini disponíveis para fallback."""
        keys = [self.GEMINI_API_KEY]
        if self.GEMINI_API_KEY2:
            keys.append(self.GEMINI_API_KEY2)
        if self.GEMINI_API_KEY3:
            keys.append(self.GEMINI_API_KEY3)
        return keys

    @property
    def groq_keys(self) -> list[str]:
        """Retorna lista de API keys Groq disponíveis para fallback."""
        keys = []
        if self.GROQ_API_KEY:
            keys.append(self.GROQ_API_KEY)
        if self.GROQ_API_KEY2:
            keys.append(self.GROQ_API_KEY2)
        return keys


@lru_cache
def get_settings() -> Settings:
    """
    Retorna uma instância singleton (cacheada) das configurações.

    O decorator @lru_cache garante que o .env é lido apenas uma vez,
    evitando I/O repetido e mantendo consistência durante a execução.
    """
    return Settings()
