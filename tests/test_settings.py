"""Testes do módulo de configuração (src/core/config/settings.py)."""

import pytest
from pydantic import ValidationError

from src.core.config.settings import Settings, get_settings


class TestSettingsLoading:
    """Carregamento das configurações a partir das variáveis de ambiente."""

    def test_loads_registry_configuration_from_environment(self):
        settings = get_settings()

        assert settings.REGISTRY_URL == "http://registry.test"
        assert settings.REGISTRY_CONSUMER_TOKEN == "test-consumer-token"

    def test_loads_llm_configuration(self):
        settings = get_settings()

        assert settings.LLM_MODEL == "gemini-2.5-flash"
        assert settings.LLM_TEMPERATURE == 0.0

    def test_uses_default_model_when_not_provided(self):
        """Sem LLM_MODEL explícito, o default do modelo deve ser aplicado."""
        settings = Settings(REGISTRY_URL="u", REGISTRY_CONSUMER_TOKEN="t")

        assert settings.LLM_MODEL == "gemini-2.5-flash"

    def test_ignores_unknown_environment_variables(self):
        """extra="ignore" evita erro quando o .env tem variáveis não mapeadas."""
        settings = Settings(
            REGISTRY_URL="u", REGISTRY_CONSUMER_TOKEN="t", VARIAVEL_DESCONHECIDA="valor"
        )

        assert settings.REGISTRY_URL == "u"

    def test_registry_configuration_is_required(self, monkeypatch):
        monkeypatch.delenv("REGISTRY_URL")
        monkeypatch.delenv("REGISTRY_CONSUMER_TOKEN")

        with pytest.raises(ValidationError):
            Settings(_env_file=None)


class TestSettingsCache:
    """get_settings() deve ser um singleton cacheado."""

    def test_returns_same_instance(self):
        assert get_settings() is get_settings()

    def test_cache_clear_creates_new_instance(self):
        first = get_settings()
        get_settings.cache_clear()

        assert get_settings() is not first


class TestRegistryUrlAlias:
    """A URL do registry também é aceita com o nome usado no Infisical."""

    def test_accepts_the_infisical_name(self):
        settings = Settings(
            _env_file=None,
            GOOGLE_REGISTRY_URL="http://registry.test",
            REGISTRY_CONSUMER_TOKEN="t",
        )

        assert settings.REGISTRY_URL == "http://registry.test"
