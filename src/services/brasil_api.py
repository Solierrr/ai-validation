"""
Serviço de consulta à BrasilAPI para enriquecimento de dados de CNPJ.

Consulta a API pública https://brasilapi.com.br/api/cnpj/v1/{cnpj}
e retorna os dados cadastrais da empresa (razão social, nome fantasia,
situação cadastral, CNAEs, etc.)

Inclui retry automático para lidar com rate limiting (429).
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# URL base da BrasilAPI para consulta de CNPJ
BRASIL_API_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"

# Máximo de tentativas em caso de rate limit (429)
MAX_RETRIES = 3


async def fetch_cnpj_data(cnpj: str) -> Optional[Dict[str, Any]]:
    """
    Consulta os dados cadastrais de um CNPJ na BrasilAPI.

    Inclui retry automático se a API retornar 429 (Too Many Requests).

    Args:
        cnpj: CNPJ sanitizado (apenas 14 dígitos numéricos).

    Returns:
        Dict com dados da empresa se encontrado, None se não encontrado.

    Raises:
        httpx.HTTPStatusError: Para erros não tratados (500, etc.)
    """
    url = BRASIL_API_URL.format(cnpj=cnpj)

    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(MAX_RETRIES):
            response = await client.get(url)

            # CNPJ não encontrado ou inválido na base da Receita
            if response.status_code in (400, 404):
                return None

            # Rate limited — espera e tenta novamente
            if response.status_code == 429:
                wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s
                logger.warning("BrasilAPI rate limited (429). Retrying in %ds...", wait_time)
                await asyncio.sleep(wait_time)
                continue

            # Outros erros (500, etc.)
            response.raise_for_status()

            return response.json()

    # Se esgotou todas as tentativas por rate limit
    response.raise_for_status()
    return None
