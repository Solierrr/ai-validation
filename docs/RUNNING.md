<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Execução local

Usar Python 3.14 ou superior, compatível com a dependência compartilhada declarada, pip, make e shell. O Dockerfile usa `python:latest`, portanto não fixa uma versão. O guia comum está em [execução Python](https://github.com/Solierrr/docs-warehouse/blob/main/readme/running/PYTHON.md).

## Preparação

Executar na raiz do checkout do serviço.

```bash
make doctor
make vault
make install
make dev
```

O servidor local usa a porta 8000, e o `make vault` consulta apenas a pasta `/llm`, por isso as configurações de acesso, as URLs e as origens também precisam estar no ambiente ou no `.env`.

| Nome | Uso |
|---|---|
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY` | Credenciais dos modelos, com formatos adicionais aceitos pela biblioteca |
| `LLM_PROVIDER_ORDER` e `LLM_MODEL_<PROVEDOR>` | Alternativas e modelos dos adaptadores |
| `LLM_MODEL`, `LLM_TEMPERATURE` | Configuração local do modelo principal |
| `JWT_JWKS_URL`, `JWT_ISSUER`, `AUTH_REQUIRED` | Verificação da pessoa |
| `SERVICE_KEY_API_CORE` | Chave reconhecida pelo helper de serviços, sem rota profissional nesta main |
| `CORS_ALLOWED_ORIGINS` | Origens permitidas no navegador |
| `DOCS_ENABLED` | Exposição de Swagger e contrato |
| `ENVIRONMENT`, `DEBUG_ADMIN_SUBS` | Ambiente e lista de administradores de debug |

Uma chave de serviço não vazia com menos de 32 caracteres impede a partida, mesmo sem uma rota que a consuma. Valores de credenciais não são parte da documentação.

## Conferir e testar

O Swagger local está em `http://localhost:8000/docs` quando habilitado. Obter o JWT pelo fluxo normal de acesso e usar o exemplo de [API.md](./API.md).

```bash
make test
make lint
make build
make openapi
```

Os alvos executam pytest com cobertura, Ruff, compileall e o exportador. O lint cobre `main.py`, `src/workflow` e `src/core/llm`, sem equivaler a lint completo da árvore. Os testes incluem rotas, consolidação, autenticação, modelos e replay.

Sem JWKS configurado, as rotas protegidas retornam 503, e uma falha no download da imagem pode aparecer como documento reprovado. O CORS precisa permitir a origem do cliente, e erros de quota podem esgotar as chaves e os provedores de imagem disponíveis.

Fontes em [Makefile](https://github.com/Solierrr/ai-validation/blob/main/Makefile), [dependências](https://github.com/Solierrr/ai-validation/blob/main/requirements.txt) e [exportação](https://github.com/Solierrr/ai-validation/blob/main/scripts/export_openapi.py).
