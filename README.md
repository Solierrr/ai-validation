# Finalidade do repositório

O `ai-validation` é o serviço de validação automatizada por IA da plataforma: uma API FastAPI que expõe dois fluxos independentes de análise. O primeiro valida certificados de treinamento NR-10 e NR-35 (segurança em instalações elétricas e trabalho em altura) enviados como imagem, usando uma pipeline multi-agente orquestrada por LangGraph com LLM Vision (Gemini) para extrair dados, checar prazo de validade, carga horária e cruzar o nome do aluno entre os dois documentos via fuzzy matching. O segundo valida se o CNPJ de uma empresa parceira (integradora/vendedora) está ativo na Receita Federal e se o ramo de atividade (CNAE) é compatível com o setor de energia solar e elétrica, usando um agente de IA para a análise semântica. Ambos os fluxos combinam consultas externas, LLM e regras de negócio determinísticas para reduzir falso positivo, sendo o sistema fail-safe por padrão.

<p>

[![License](https://img.shields.io/github/license/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/blob/main/LICENSE)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/commits)
[![GitHub Issues](https://img.shields.io/github/issues/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/pulls)
[![GitHub Contributors](https://img.shields.io/github/contributors/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/graphs/contributors)
[![Release](https://img.shields.io/github/v/release/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/releases)

</p>

<div align="center">

<p>
  <a href="https://github.com/syvixor/skills-icons">
    <img src="https://skills.syvixor.com/api/icons?i=python,fastapi,pydantic,langchain,githubactions,docker" height="48" alt="Stack do Projeto">
  </a>
</p>

<p>

[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?logo=langchain&logoColor=white)](https://www.langchain.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langgraph&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

</p>

</div>

## Aprofunde-se no Projeto!

- [ARCHITECTURE.md](./ARCHITECTURE.md), estrutura de pastas, camadas e padrões arquiteturais do serviço.
- [RUNNING.md](./RUNNING.md), como rodar o projeto localmente, incluindo impedimentos e variáveis de ambiente.
- [Deployment](https://github.com/Solierrr/.github/blob/main/.github/DEPLOYMENT.md), pipeline de deploy padronizado da organização (CI, release, ArgoCD).
- [docs/API.md](./docs/API.md), contrato completo dos endpoints, payloads e códigos de erro.
- [docs/AGENT_WORKFLOW.md](./docs/AGENT_WORKFLOW.md), detalhamento da pipeline multi-agente de validação de certificados.
- [docs/CNPJ_WORKFLOW.md](./docs/CNPJ_WORKFLOW.md), detalhamento do fluxo de validação de CNPJ.

## Contribuindo

- [CONTRIBUTING.md](https://github.com/Solierrr/.github/blob/main/.github/CONTRIBUTING.md), convenções de commit, branch e Pull Request.
- [CODE_OF_CONDUCT.md](https://github.com/Solierrr/.github/blob/main/.github/CODE_OF_CONDUCT.md), código de conduta do projeto.
- [SECURITY.md](https://github.com/Solierrr/.github/blob/main/.github/SECURITY.md), como reportar vulnerabilidades de segurança.
