<p align="center">
  <img src="./assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

<p align="center">
  <img src="./assets/readme/stacks/python.png" width="100" hspace="8" alt="Python" title="Python">
  <img src="./assets/readme/stacks/pydantic.png" width="100" hspace="8" alt="Pydantic" title="Pydantic">
  <img src="./assets/readme/stacks/langchain.png" width="100" hspace="8" alt="LangChain" title="LangChain">
  <img src="./assets/readme/stacks/gemini.png" width="100" hspace="8" alt="Gemini" title="Gemini">
  <img src="./assets/readme/stacks/groq.png" width="100" hspace="8" alt="Groq" title="Groq">
</p>

# Validação de documentos e empresas

[![License](https://img.shields.io/github/license/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/blob/main/LICENSE)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/commits)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/pulls)
[![Release](https://img.shields.io/github/v/release/Solierrr/ai-validation)](https://github.com/Solierrr/ai-validation/releases)

Este serviço confere documentos enviados por profissionais e dados de empresas parceiras. Ele lê imagens de certificados de segurança em instalações elétricas e trabalho em altura, compara os nomes dos alunos e verifica os critérios de aceitação implementados. Também consulta a situação cadastral de uma empresa e avalia se suas atividades têm relação com o setor de energia solar e elétrica.

Os clientes enviam duas imagens acessíveis por endereço ou um CNPJ e recebem um resultado com justificativa. FastAPI organiza as chamadas e valida o JWT da pessoa. LangGraph conduz a análise dos certificados, enquanto uma etapa de consolidação aplica as verificações finais. Modelos de linguagem ajudam a extrair e classificar informações, e BrasilAPI fornece os dados cadastrais das empresas.

## Aprofunde-se no Projeto!

- [OVERVIEW.md](./docs/OVERVIEW.md), capacidades e regras de aceitação.
- [ARCHITECTURE.md](./docs/ARCHITECTURE.md), camadas e integrações.
- [RUNNING.md](./docs/RUNNING.md), ambiente local e testes.
- [API.md](./docs/API.md), autenticação, contrato e exemplos.
- [DEPLOY.md](./docs/DEPLOY.md), ambientes e publicação.
- [STATUS.md](./docs/STATUS.md), limitações e divergências.
- [Fluxos](./flows/), certificados, empresas e depuração.
- [PENDENCIAS.md](./PENDENCIAS.md), confirmações para o responsável.

## Contribuindo

- [CONTRIBUTING.md](https://github.com/Solierrr/.github/blob/main/.github/CONTRIBUTING.md), convenções de contribuição.
- [CODE_OF_CONDUCT.md](https://github.com/Solierrr/.github/blob/main/CODE_OF_CONDUCT.md), código de conduta.
- [SECURITY.md](https://github.com/Solierrr/.github/blob/main/SECURITY.md), reporte de vulnerabilidade.
