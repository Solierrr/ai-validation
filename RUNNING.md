# Rodando o Projeto Localmente

Este repositório é Python. O processo local é sempre o mesmo: clonar, criar um ambiente virtual, instalar as dependências do `requirements.txt` e subir a aplicação via `uvicorn`, apontando para o módulo `main:app`. Antes de iniciar, verifique a seção de impedimentos abaixo — o serviço depende de chave de API de LLM e de uma API externa mesmo em ambiente local.

<p>
  <a href="https://github.com/syvixor/skills-icons">
    <img src="https://skills.syvixor.com/api/icons?i=python,fastapi,pydantic,github" height="48" alt="Rodando o Projeto — Python">
  </a>
</p>

## Possíveis Impedimentos

- **Python instalado localmente**, o `Dockerfile` usa a imagem `python:latest` e o workflow de CI (`.github/workflows/ci.yml`) roda sob Python `3.14`; recomenda-se usar essa versão localmente para evitar divergência de comportamento entre libs.
- **google-registry (`REGISTRY_URL` e `REGISTRY_CONSUMER_TOKEN`)**, obrigatórios — os agentes de IA (validação de certificados e de CNPJ) pedem a chave do Gemini (e do Groq, no fallback) ao corretor de chaves do `google-registry` a cada chamada, via a lib `solaria-lib`. O serviço não guarda chaves de LLM; sem o registry acessível, os endpoints de validação falham ao processar.
- **Acesso à internet para a BrasilAPI**, o fluxo de validação de CNPJ consulta `https://brasilapi.com.br/api/cnpj/v1/{cnpj}` em tempo real; sem conectividade de saída, esse endpoint retorna erro 502.
- **Rate limiting ativo mesmo localmente**, o `slowapi` limita requisições por IP (10/min para certificados, 20/min para CNPJ) mesmo em ambiente de desenvolvimento — testes de carga local podem esbarrar nesse limite.

## Instalação do Projeto

### Iniciando o repositório com o Github

<p>
  <a href="https://github.com/syvixor/skills-icons">
    <img src="https://skills.syvixor.com/api/icons?i=github,vscode" height="48" alt="Frameworks">
  </a>
</p>

Clone o repositório e abra no VS Code.

```Comandos para clonar o repositório
git clone https://github.com/Solierrr/ai-validation.git
cd ./ai-validation
code . -r
```

### Instalando dependências necessárias para rodar o projeto localmente

<p>
  <a href="https://github.com/syvixor/skills-icons">
    <img src="https://skills.syvixor.com/api/icons?i=python" height="48" alt="Frameworks">
  </a>
</p>

Crie um ambiente virtual antes de instalar as dependências, para não poluir o Python global da máquina. Depois de instalar, copie o `.env.example` para `.env` e preencha `REGISTRY_URL` e `REGISTRY_CONSUMER_TOKEN` (obrigatórias) antes de subir o servidor.

```Comandos para instalação de dependências
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

A aplicação sobe em `http://localhost:8000`. O health check fica em `GET /health` e a documentação interativa (Swagger) em `http://localhost:8000/docs`.

### Rodando os testes

<p>
  <a href="https://github.com/syvixor/skills-icons">
    <img src="https://skills.syvixor.com/api/icons?i=pytest,python" height="48" alt="Testes">
  </a>
</p>

Os testes usam `pytest` com `pytest-asyncio` (modo automático) e geram relatório de cobertura em `coverage.xml`, consumido depois pelo SonarQube. A configuração já está em `pytest.ini`, então basta rodar:

```Comandos para rodar os testes
pytest
```

### Rodando via Docker

<p>
  <a href="https://github.com/syvixor/skills-icons">
    <img src="https://skills.syvixor.com/api/icons?i=docker" height="48" alt="Docker">
  </a>
</p>

O `Dockerfile` do repositório instala as dependências e expõe a porta `8000`, subindo diretamente com `uvicorn main:app --host 0.0.0.0 --port 8000`. Não há build multi-stage neste repositório — a imagem final roda diretamente sobre `python:latest`.

```Comandos para rodar via Docker
docker build -t ai-validation .
docker run --env-file .env -p 8000:8000 ai-validation
```

## Telemetria (OpenTelemetry)

O serviço envia traces, métricas e logs por OTLP pelo wrapper `opentelemetry-instrument` (auto-instrumentação de FastAPI e `logging`), sem código na aplicação. Ele só é usado quando `OTEL_SDK_DISABLED=false`; sem isso o serviço sobe como antes. Para ver a telemetria localmente, use o Grafana local pelo `make up OBS=1` (ver `docs-warehouse/helps/TRY-LOCAL.md`).

```text
OTEL_SDK_DISABLED=false
OTEL_SERVICE_NAME=ai-validation
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_RESOURCE_ATTRIBUTES=service.namespace=solaria,deployment.environment=local
OTEL_PYTHON_LOG_CORRELATION=true
```
