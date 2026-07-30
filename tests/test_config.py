"""Testes do módulo de configuração (src/core/config.py)."""

from src.core.config import Settings, get_settings


class TestSettingsLoading:
    """Carregamento das configurações a partir das variáveis de ambiente."""

    def test_loads_keys_from_environment(self):
        settings = get_settings()

        assert settings.GEMINI_API_KEY == "test-gemini-key-1"
        assert settings.GEMINI_API_KEY2 == "test-gemini-key-2"
        assert settings.GEMINI_API_KEY3 == "test-gemini-key-3"

    def test_loads_llm_configuration(self):
        settings = get_settings()

        assert settings.LLM_MODEL == "gemini-2.5-flash"
        assert settings.LLM_TEMPERATURE == 0.0

    def test_uses_default_model_when_not_provided(self):
        """Sem LLM_MODEL explícito, o default do modelo deve ser aplicado."""
        settings = Settings(GEMINI_API_KEY="k", LLM_MODEL="gemini-2.5-flash")

        assert settings.LLM_MODEL == "gemini-2.5-flash"

    def test_ignores_unknown_environment_variables(self):
        """extra="ignore" evita erro quando o .env tem variáveis não mapeadas."""
        settings = Settings(GEMINI_API_KEY="k", VARIAVEL_DESCONHECIDA="valor")

        assert settings.GEMINI_API_KEY == "k"


class TestGeminiKeysProperty:
    """Property api_keys — lista de chaves Gemini para fallback."""

    def test_returns_all_configured_keys(self):
        assert get_settings().api_keys == [
            "test-gemini-key-1",
            "test-gemini-key-2",
            "test-gemini-key-3",
        ]

    def test_returns_only_primary_when_no_fallback(self):
        settings = Settings(
            GEMINI_API_KEY="only-key",
            GEMINI_API_KEY2=None,
            GEMINI_API_KEY3=None,
        )

        assert settings.api_keys == ["only-key"]

    def test_skips_third_key_when_absent(self):
        settings = Settings(
            GEMINI_API_KEY="k1",
            GEMINI_API_KEY2="k2",
            GEMINI_API_KEY3=None,
        )

        assert settings.api_keys == ["k1", "k2"]


class TestGroqKeysProperty:
    """Property groq_keys — lista de chaves Groq para fallback."""

    def test_returns_all_configured_keys(self):
        assert get_settings().groq_keys == ["test-groq-key-1", "test-groq-key-2"]

    def test_returns_empty_list_when_not_configured(self):
        settings = Settings(GEMINI_API_KEY="k", GROQ_API_KEY=None, GROQ_API_KEY2=None)

        assert settings.groq_keys == []

    def test_returns_single_key_when_only_primary(self):
        settings = Settings(GEMINI_API_KEY="k", GROQ_API_KEY="g1", GROQ_API_KEY2=None)

        assert settings.groq_keys == ["g1"]


class TestSettingsCache:
    """get_settings() deve ser um singleton cacheado."""

    def test_returns_same_instance(self):
        assert get_settings() is get_settings()

    def test_cache_clear_creates_new_instance(self):
        first = get_settings()
        get_settings.cache_clear()

        assert get_settings() is not first
