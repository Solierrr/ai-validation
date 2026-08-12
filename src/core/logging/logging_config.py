"""
Configuração de logging estruturado (JSON) para observabilidade em produção.
"""

import logging
import sys

from pythonjsonlogger import json as jsonlogger


def configure_logging() -> None:
    """
    Configura o logging raiz para emitir cada linha como JSON.

    Facilita integração com ferramentas de observabilidade
    (CloudWatch, Datadog, ELK, etc.)
    """
    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(
        jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            # Renomeia campos para um padrão mais legível em ferramentas de log
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
        )
    )

    logging.basicConfig(
        level=logging.INFO,
        handlers=[log_handler],
    )
