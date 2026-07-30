"""
Configuração compartilhada dos testes (fixtures e variáveis de ambiente).

IMPORTANTE: as variáveis de ambiente são definidas no topo deste módulo,
antes de qualquer import de `src`. Isso garante que os testes rodem em
qualquer ambiente (inclusive no CI, onde não existe arquivo .env) e que
as chaves reais do desenvolvedor nunca sejam usadas nos testes.
"""

import os

# ─── Variáveis de ambiente determinísticas para os testes ────────────────────
# Variáveis de ambiente têm precedência sobre o arquivo .env no pydantic-settings,
# então esses valores fake sobrescrevem qualquer .env presente localmente.
os.environ["GEMINI_API_KEY"] = "test-gemini-key-1"
os.environ["GEMINI_API_KEY2"] = "test-gemini-key-2"
os.environ["GEMINI_API_KEY3"] = "test-gemini-key-3"
os.environ["GROQ_API_KEY"] = "test-groq-key-1"
os.environ["GROQ_API_KEY2"] = "test-groq-key-2"
os.environ["LLM_MODEL"] = "gemini-2.5-flash"
os.environ["LLM_TEMPERATURE"] = "0.0"

import pytest  # noqa: E402

from src.core.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """
    Limpa o cache do get_settings() antes e depois de cada teste.

    get_settings() usa @lru_cache, então sem essa limpeza um teste que
    altera configurações vazaria o estado para os testes seguintes.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ─── Fixtures de dados de certificados ───────────────────────────────────────


@pytest.fixture
def valid_nr10_result():
    """Resultado válido do agente NR-10 (40h, dentro da validade)."""
    return {
        "valid": True,
        "error_code": None,
        "error_reason": None,
        "student_name": "Carlos Eduardo da Silva",
        "institution_name": "SENAI SP",
        "workload_hours": 40,
        "issue_date": "2026-01-15",
        "has_required_structure": True,
    }


@pytest.fixture
def valid_nr35_result():
    """Resultado válido do agente NR-35 (8h, dentro da validade)."""
    return {
        "valid": True,
        "error_code": None,
        "error_reason": None,
        "student_name": "Carlos Eduardo da Silva",
        "institution_name": "Engehall Treinamentos",
        "workload_hours": 8,
        "issue_date": "2026-02-10",
        "has_required_structure": True,
    }


@pytest.fixture
def approved_state(valid_nr10_result, valid_nr35_result):
    """Estado completo que deve resultar em ACCEPT na consolidação."""
    return {
        "is_safe": True,
        "current_date": "2026-07-15",
        "nr10_result": valid_nr10_result,
        "nr35_result": valid_nr35_result,
    }


# ─── Fixtures de dados de CNPJ ───────────────────────────────────────────────


@pytest.fixture
def company_data():
    """Payload típico da BrasilAPI para uma empresa ativa do setor elétrico."""
    return {
        "razao_social": "SOLAR ENERGY ENGENHARIA E INSTALACOES LTDA",
        "nome_fantasia": "SOLAR ENERGY",
        "descricao_situacao_cadastral": "ATIVA",
        "cnae_fiscal": 4321500,
        "cnae_fiscal_descricao": "Instalacao e manutencao eletrica",
        "cnaes_secundarios": [
            {"codigo": 7112000, "descricao": "Servicos de engenharia"},
        ],
    }


# ─── Fixtures da API ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """
    Desliga o rate limiting durante os testes.

    O slowapi guarda o contador em memória e o TestClient sempre usa o mesmo
    IP, então sem isso os últimos testes de cada endpoint receberiam HTTP 429.
    O teste dedicado de rate limit religa o limiter explicitamente.
    """
    from src.api import cnpj_routes, routes

    routes.limiter.enabled = False
    cnpj_routes.limiter.enabled = False
    yield
    routes.limiter.enabled = True
    cnpj_routes.limiter.enabled = True


@pytest.fixture
def client():
    """Cliente HTTP de teste da aplicação FastAPI."""
    from fastapi.testclient import TestClient

    from src.main import app

    return TestClient(app)
