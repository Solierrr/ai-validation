"""Testes do módulo de configuração (src/core/config/settings.py)."""

from src.core.config.settings import Settings, get_settings


class TestSettingsLoading:
    """Carregamento das configurações a partir das variáveis de ambiente."""

    def test_loads_llm_configuration(self):
        settings = get_settings()

        assert settings.LLM_MODEL == "gemini-2.5-flash"
        assert settings.LLM_TEMPERATURE == 0.0

    def test_uses_default_model_when_not_provided(self):
        """Sem LLM_MODEL explícito, o default do modelo deve ser aplicado."""
        settings = Settings(LLM_MODEL="gemini-2.5-flash")

        assert settings.LLM_MODEL == "gemini-2.5-flash"

    def test_ignores_unknown_environment_variables(self):
        """extra="ignore" evita erro quando o .env tem variáveis não mapeadas (como as chaves)."""
        settings = Settings(VARIAVEL_DESCONHECIDA="valor", GEMINI_API_KEY="k")

        assert settings.LLM_TEMPERATURE == 0.0


class TestSettingsCache:
    """get_settings() deve ser um singleton cacheado."""

    def test_returns_same_instance(self):
        assert get_settings() is get_settings()

    def test_cache_clear_creates_new_instance(self):
        first = get_settings()
        get_settings.cache_clear()

        assert get_settings() is not first
