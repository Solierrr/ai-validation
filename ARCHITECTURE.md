# Arquitetura do Repositório

O `ai-validation` segue uma arquitetura em camadas dentro de `src/`, separando claramente a superfície HTTP (rotas e schemas), a orquestração dos fluxos de IA (agents e workflow) e as integrações com serviços externos (LLM providers e BrasilAPI). A validação de certificados é modelada como um grafo de estados com o LangGraph, onde cada nó é um agente especializado (guardrail de segurança, extração NR-10, extração NR-35) e a decisão final é tomada por um nó puramente determinístico, sem chamada a LLM, o que facilita testar e auditar a regra de negócio isoladamente da parte probabilística. Já a validação de CNPJ é um fluxo mais linear dentro da própria rota, que sanitiza a entrada, consulta a Receita Federal via BrasilAPI e delega a um único agente a análise semântica dos CNAEs. Configuração é centralizada via `pydantic-settings` lendo um `.env`, e logging estruturado em JSON é configurado no bootstrap da aplicação para observabilidade em produção.

<p>
  <a href="https://github.com/syvixor/skills-icons">
    <img src="https://skills.syvixor.com/api/icons?i=python,fastapi,pydantic,langchain,pytest" height="48" alt="Arquitetura">
  </a>
</p>

- **Arquitetura em camadas (layered)**, `api/` expõe rotas e schemas HTTP, `workflow/` e `agents/` concentram a lógica de orquestração e IA, `services/` isola integrações externas (BrasilAPI) e `core/` centraliza configuração, logging e clientes LLM — cada camada só conhece a camada abaixo dela.
- **Orquestração via LangGraph (StateGraph)**, o fluxo de certificados NR-10/NR-35 é modelado como um grafo (`src/workflow/graph/graph.py`) com estado tipado compartilhado (`src/workflow/state/state.py`), nós especializados (`src/workflow/nodes/`) e roteamento condicional (`src/workflow/edges/`) — o guardrail de segurança decide se o fluxo segue para os agentes de extração ou pula direto para a consolidação.
- **Separação entre decisão probabilística e determinística**, os agentes de IA (`src/agents/specialist/`) apenas extraem e classificam dados via LLM Vision/texto com saída estruturada em Pydantic; a decisão final de aceitar ou rejeitar (`src/workflow/nodes/consolidation_node.py`) é lógica pura em Python (checagem de validade, carga horária mínima, fuzzy match de nome com RapidFuzz), sem nenhuma chamada a LLM — isso deixa a regra de negócio testável sem depender de mock de IA.
- **Fail-safe por padrão**, qualquer falha não tratada na pipeline (download de imagem, chamada ao LLM, exceção inesperada) resulta em rejeição (`REJECTED`/`INVALID`) e nunca em aprovação silenciosa; erros são mapeados para códigos padronizados (`error_code`) documentados em `docs/API.md`.
- **Múltiplos provedores de LLM com fallback**, `src/core/llm/` encapsula clientes para Gemini (`llm_gemini.py`) e Groq (`llm_groq.py`), com lógica de retry (`llm_retry.py`) e suporte a múltiplas chaves de API por provedor (`GEMINI_API_KEY`, `GEMINI_API_KEY2`, `GEMINI_API_KEY3`, `GROQ_API_KEY`, `GROQ_API_KEY2`) para contornar limites de cota.
- **Rate limiting e CORS na borda**, configurados em `main.py` via `slowapi` (limite por IP e por rota) e `CORSMiddleware`, antes de qualquer requisição alcançar as rotas de negócio.
- **Cobertura e qualidade via CI**, `pytest` com `pytest-asyncio` e `pytest-cov` gera `coverage.xml`, consumido pelo SonarQube (`sonar-project.properties`) nos workflows de `.github/workflows/`, com `sonar.sources=src` e `sonar.tests=tests` separando código de produção e de teste.

```Tree do Repositório
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── qa-sync.yml
│       ├── quality.yml
│       ├── release.yml
│       ├── repo-cleanup.yml
│       └── sonarqube.yml
├── docs/
│   ├── AGENT_WORKFLOW.md
│   ├── API.md
│   └── CNPJ_WORKFLOW.md
├── src/
│   ├── agents/
│   │   └── specialist/
│   │       ├── cnpj_agent/
│   │       ├── nr10_agent/
│   │       ├── nr35_agent/
│   │       └── security_guardrail/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── certificate_routes.py
│   │   │   └── cnpj_routes.py
│   │   └── schemas/
│   │       ├── certificate_schemas.py
│   │       └── cnpj_schemas.py
│   ├── core/
│   │   ├── config/
│   │   │   └── settings.py
│   │   ├── llm/
│   │   │   ├── llm_gemini.py
│   │   │   ├── llm_groq.py
│   │   │   └── llm_retry.py
│   │   └── logging/
│   │       └── logging_config.py
│   ├── services/
│   │   └── brasil_api.py
│   └── workflow/
│       ├── edges/
│       │   └── validation_edges.py
│       ├── graph/
│       │   └── graph.py
│       ├── nodes/
│       │   ├── consolidation_node.py
│       │   ├── nr10_agent_node.py
│       │   ├── nr35_agent_node.py
│       │   └── security_guardrail_node.py
│       └── state/
│           └── state.py
├── tests/
│   ├── agents/
│   ├── api/
│   ├── workflow/
│   ├── integrations/
│   └── tools/
├── main.py
├── Dockerfile
├── pytest.ini
├── requirements.txt
├── sonar-project.properties
├── README.md
├── ARCHITECTURE.md
├── RUNNING.md
└── LICENSE
```
