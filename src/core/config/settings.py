"""
Módulo de configuração da aplicação.

Utiliza pydantic-settings para carregar variáveis de ambiente do arquivo .env
e disponibilizá-las de forma tipada e validada para o restante do projeto.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

SERVICE_KEY_MIN_LENGTH = 32


class Settings(BaseSettings):
    """
    Configurações da aplicação carregadas a partir de variáveis de ambiente.

    O fallback entre provedores (Gemini, Groq, OpenAI) segue LLM_PROVIDER_ORDER.
    """

    # As chaves de LLM (GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY) são lidas do ambiente pela
    # solaria-lib (src/core/llm/keys.py); uma chave por provedor.

    LLM_MODEL: str = (
        "gemini-2.5-flash"  # Modelo atual com Vision e boa relação custo/performance
    )
    LLM_TEMPERATURE: float = 0.0  # Temperatura 0 = output determinístico

    # Liga o Swagger (/docs) e o contrato (/openapi.json); desligado em PROD
    DOCS_ENABLED: bool = True

    # Chaves de serviço dos chamadores aceitos (cabeçalho X-Service-Key); vazia recusa o chamador
    SERVICE_KEY_API_CORE: str = ""

    @field_validator("SERVICE_KEY_API_CORE")
    @classmethod
    def _check_service_key_length(cls, value: str) -> str:
        if value and len(value) < SERVICE_KEY_MIN_LENGTH:
            raise ValueError(f"a chave de serviço precisa de ao menos {SERVICE_KEY_MIN_LENGTH} caracteres")
        return value

    @property
    def service_keys(self) -> dict[str, str]:
        """Mapa chamador -> chave esperada, a partir de SERVICE_KEY_<CHAMADOR>."""
        return {"api-core": self.SERVICE_KEY_API_CORE}
    ENVIRONMENT: str = "LOCAL"  # Defina em QA e PROD; o padrão é LOCAL

    DEBUG_ADMIN_SUBS: str = ""

    # Origens do navegador autorizadas a chamar a API (CORS), separadas por vírgula.
    # Em QA e PROD vêm do ambiente; o padrão cobre só o desenvolvimento local.
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Validação do access token do api-auth (RS256 via JWKS). Com AUTH_REQUIRED ativo
    # e sem JWT_JWKS_URL, as rotas de validação respondem 503 em vez de ficarem abertas.
    AUTH_REQUIRED: bool = True
    JWT_JWKS_URL: str | None = None
    JWT_ISSUER: str | None = None

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
