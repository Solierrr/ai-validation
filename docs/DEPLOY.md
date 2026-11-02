<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Ambientes e publicação

A imagem executa Uvicorn na porta 8000. O entrypoint obtém configuração por Universal Auth do Infisical quando as duas credenciais de cliente existem. Sem elas, inicia diretamente com o ambiente disponível.

| Ambiente | Endereço | Evidência |
|---|---|---|
| Local | `http://localhost:8000` | Bootstrap e entrypoint |
| QA | `https://ai-validation-jjb7.onrender.com` | Contrato e workflow de ambiente |
| PROD | `https://validation.solarianetwork.site` | Ingress de infraestrutura |

Esses endereços são declarados, sem afirmar disponibilidade de uma chamada real. Os processos comuns estão em [QA no Render](https://github.com/Solierrr/docs-warehouse/blob/main/readme/deploy/QA_RENDER.md), [produção](https://github.com/Solierrr/docs-warehouse/blob/main/readme/deploy/PROD_GKE_ARGOCD.md) e [release e deploy](https://github.com/Solierrr/docs-warehouse/blob/main/docs/flows/RELEASE_AND_DEPLOY.md).

## Configuração específica

O Dockerfile usa base `python:latest` e instala dependências sem lock de versões. O entrypoint usa `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET` e `INFISICAL_ENV` para carregar a raiz do ambiente. Não consultar ou copiar valores de secrets para a documentação.

O workflow de ambiente consulta `/ready` em QA. Em produção, ele verifica o cluster, sem validar a resposta HTTP deste serviço. O manifesto de infraestrutura consultado na revisão `2f053a24` tem uma réplica, imagem `latest`, secret `ai-validation-secrets` e ambas as sondas em `/health`. A sonda de pronto ainda não usa `/ready`.

Os ambientes de QA e de produção estão publicados, e o debug também é admitido em PROD quando há administrador configurado, por isso desligar o Swagger não desliga o debug.

Fontes em [Dockerfile](https://github.com/Solierrr/ai-validation/blob/main/Dockerfile), [entrypoint](https://github.com/Solierrr/ai-validation/blob/main/entrypoint.sh), [workflow de ambiente](https://github.com/Solierrr/ai-validation/blob/main/.github/workflows/environment-status.yml), [deployment](https://github.com/Solierrr/infra-gitops/blob/main/services/ai-validation/deployment.yaml) e [ingress](https://github.com/Solierrr/infra-gitops/blob/main/services/ai-validation/ingress.yaml).
