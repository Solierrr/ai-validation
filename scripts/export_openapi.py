"""
Exporta o contrato OpenAPI para openapi.yaml, com as rotas /internal/.

Uso: make openapi. Não depende de segredo: as chaves de LLM recebem valores fictícios
só para o import do app, sem nenhuma chamada externa.
"""

import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
    os.environ.setdefault(key, "export-placeholder")

from main import build_openapi

contract = yaml.safe_dump(
    build_openapi(include_internal=True), allow_unicode=True, sort_keys=False, width=120
)
contract = re.sub(
    r"^(  version: .+)$",
    r"\1 # x-release-please-version",
    contract,
    count=1,
    flags=re.MULTILINE,
)
(ROOT / "openapi.yaml").write_text(contract, encoding="utf-8", newline="\n")
