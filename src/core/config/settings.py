"""
Módulo de configuração da aplicação.

Utiliza pydantic-settings para carregar variáveis de ambiente do arquivo .env
e disponibilizá-las de forma tipada e validada para o restante do projeto.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configurações da aplicação carregadas a partir de variáveis de ambiente.

    As chaves de LLM (Gemini e Groq) ficam apenas no google-registry; o
    serviço recebe a URL do registry e o token de consumidor.
    """

    REGISTRY_URL: str = Field(
        validation_alias=AliasChoices("REGISTRY_URL", "GOOGLE_REGISTRY_URL")
    )  # URL base do google-registry (obrigatória)
    REGISTRY_CONSUMER_TOKEN: (
        str  # Token de consumidor do corretor de chaves (obrigatório)
    )

    LLM_MODEL: str = (
        "gemini-2.5-flash"  # Modelo atual com Vision e boa relação custo/performance
    )
    LLM_TEMPERATURE: float = 0.0  # Temperatura 0 = output determinístico

    # Configuração do pydantic-settings: lê do arquivo .env na raiz do projeto
    # extra="ignore" permite ter variáveis extras no .env sem causar erro
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """
    Retorna uma instância singleton (cacheada) das configurações.

    O decorator @lru_cache garante que o .env é lido apenas uma vez,
    evitando I/O repetido e mantendo consistência durante a execução.
    """
    return Settings()
