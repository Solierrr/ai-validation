"""
Cliente do corretor de chaves do google-registry.
"""

from functools import lru_cache

from ai_lib.registry import RegistryClient

from src.core.config.settings import get_settings


@lru_cache(maxsize=1)
def registry_client() -> RegistryClient:
    """Cria (uma vez) o cliente do corretor com a URL e o token das settings."""
    settings = get_settings()
    return RegistryClient(settings.REGISTRY_URL, settings.REGISTRY_CONSUMER_TOKEN)
