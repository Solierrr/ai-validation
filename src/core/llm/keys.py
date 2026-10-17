"""Chaves de LLM lidas do ambiente (Infisical): uma por provedor."""

from functools import lru_cache

from ai_lib.llm import EnvKeyClient
from dotenv import load_dotenv


@lru_cache(maxsize=1)
def key_client() -> EnvKeyClient:
    # Expõe o .env local em os.environ; em produção as variáveis já vêm do ambiente.
    load_dotenv(override=False)
    return EnvKeyClient()
