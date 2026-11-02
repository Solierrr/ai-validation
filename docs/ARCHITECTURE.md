<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Arquitetura

Serviço FastAPI com schemas Pydantic e um grafo LangGraph para certificados. O fluxo de empresas consulta BrasilAPI e um agente de texto. O código lê configurações de ambiente e reutiliza a biblioteca de modelos, sem banco de negócio próprio.

```mermaid
flowchart LR
  C[Cliente] -->|HTTP e JWT| A[FastAPI]
  A -->|HTTP público JWKS| J[Serviço de acesso]
  A --> G[Grafo de certificados]
  G -->|HTTPS público| I[Imagens dos documentos]
  G --> L[Adaptadores de modelos]
  A --> E[Validação de empresa]
  E -->|HTTPS público| B[BrasilAPI]
  E --> L
  L -->|HTTPS e chave do provedor| P[Provedores de modelos]
  A --> D[Debug administrativo em memória]
```

## Organização

| Caminho | Responsabilidade |
|---|---|
| `main.py` | Bootstrap, CORS, limites, erros, rotas e geração do OpenAPI |
| `src/api/` | Schemas, autenticação, rotas e respostas de erro |
| `src/workflow/` | Grafo, estado, extração, consolidação e depuração |
| `src/agents/specialist/` | Prompts e agente de empresa |
| `src/core/llm/` | Clientes e fallback de modelos |
| `src/core/config/` | Settings cacheadas |
| `src/services/` | Consulta BrasilAPI |
| `tests/` | Testes de rotas, nós, segurança e integrações isoladas |

## Integrações e autenticação

| Relação | Protocolo | Autenticação |
|---|---|---|
| Clientes chamam validação | HTTP JSON | JWT de usuário por padrão |
| Verificação de assinatura | HTTP JWKS | Chave pública, assinatura RS256 |
| Download de certificados | HTTP ou HTTPS | URL acessível, sem envio do JWT ao armazenamento |
| Consulta de CNPJ | HTTPS BrasilAPI | Sem credencial no cliente implementado |
| Modelos | HTTPS pelos adaptadores | Chaves de provedor do ambiente |
| Cadastro central pretende validar profissional | HTTP | Contrato ausente nesta main, sem integração ativa comprovada |

A dependência `require_access_token` protege os dois routers de negócio, e como `AUTH_REQUIRED` vem ligado por padrão, a falta de JWKS configurado responde 503. A validação exige `exp` e `sub`, aceita apenas RS256 e recusa `token_type` diferente de `access`, tratando o token como access quando o campo não existe, e confere o issuer quando ele está configurado.

A função `require_caller` e a variável `SERVICE_KEY_API_CORE` já existem, mas nenhuma rota de validação desta main usa essa dependência. O padrão definido para chamadas entre serviços é a `X-Service-Key` de cada chamador, e a rota profissional deve adotá-lo.

## Execução e dados

O grafo público é compilado sem checkpointer. Ele baixa as duas imagens, aplica segurança, executa os especialistas e consolida. Base64 e MIME são reutilizados no estado durante a solicitação. Falhas capturadas na leitura ou nos nós podem gerar reprovação de documento, enquanto exceções não tratadas viram erro HTTP.

O download segue redirecionamentos e usa timeout de 30 segundos, sem limite de bytes nem restrição de origem no código. A origem definida para os documentos é o Cloudinary, e a restrição a essa origem está pendente.

O fallback externo só avança por erro reconhecido como rate limit. Chamadas de imagem excluem o provedor marcado como apenas texto. A biblioteca compartilhada também administra rodízio de chaves. Dependências instaladas não comprovam uso de PostgreSQL, MongoDB ou índice vetorial.

## Observabilidade, health e versão

Os logs saem em JSON, e o debug administrativo mostra as etapas e permite uma reexecução controlada, como descreve o [fluxo de depuração](../flows/DEBUG_REPLAY.md). O serviço não guarda dados de negócio, e tanto os limites quanto o debug valem só para a instância em execução.

O `/health` retorna o estado e a versão, e o `/ready` retorna só o estado, sem consultar a BrasilAPI, o JWKS ou os modelos, por isso uma resposta positiva não comprova que uma validação real será atendida.

A versão é lida de `version.txt`, hoje `3.1.0`, e a revisão analisada é a `7855fc9f`, de 2026-10-30. As fontes principais são o [bootstrap](https://github.com/Solierrr/ai-validation/blob/main/main.py), o [JWT](https://github.com/Solierrr/ai-validation/blob/main/src/core/security/jwt.py), o [grafo](https://github.com/Solierrr/ai-validation/blob/main/src/workflow/graph/graph.py), as [settings](https://github.com/Solierrr/ai-validation/blob/main/src/core/config/settings.py) e o [download](https://github.com/Solierrr/ai-validation/blob/main/src/workflow/nodes/security_guardrail_node.py).

## Diagrama de arquitetura

### Onde o serviço se encaixa

O `ai-validation` não conversa: recebe um documento ou um CNPJ, devolve um veredito e não guarda sessão. As rotas `/api/v1/*` exigem o access token JWT do usuário, emitido pelo `api-auth` e validado pelas chaves públicas (JWKS); o navegador pode chamá-las direto (há CORS). Por isso ele não participa do A2A. A decisão final é sempre código, nunca o modelo.

```mermaid
flowchart LR
    WEB["web-app"] -->|"REST + JWT do usuário"| API
    API -.->|"valida o JWT (JWKS)"| AUTH["api-auth"]

    subgraph VAL["ai-validation (FastAPI)"]
        API["POST /api/v1/certificates/validate<br/>POST /api/v1/companies/validate-cnpj"]
        WF["fluxo de certificados<br/>LangGraph"]
        CN["fluxo de CNPJ"]
    end

    API --> WF
    API --> CN
    WF -->|"imagem do certificado"| LLM["Gemini (visão)<br/>com retry e várias chaves"]
    CN -->|"CNAEs"| LLM
    CN -->|"consulta o CNPJ"| BR["BrasilAPI<br/>Receita Federal"]
    WF -->|"baixa a imagem"| IMG["URL da imagem<br/>enviada pelo cliente"]
```

### Fluxo de certificados NR-10 e NR-35

```mermaid
flowchart TD
    START([2 URLs de certificado]) --> SG["security_guardrail<br/>baixa as imagens e detecta<br/>injeção e documento ilegível (LLM visão)"]
    SG -->|"seguro"| N10["nr10_agent<br/>extrai e valida o NR-10 (LLM visão)"]
    SG -->|"inseguro"| CONS
    N10 --> N35["nr35_agent<br/>extrai e valida o NR-35 (LLM visão)"]
    N35 --> CONS["consolidation<br/>decisão final em código, sem LLM"]
    CONS --> OUT([ACCEPT ou REJECTED])
```

A `consolidation` aplica as regras na ordem: segurança, validade e prazo de cada certificado (mais de 24 meses rejeita), carga horária mínima (NR-10: 20 h, e o prompt cita 20 h de reciclagem ou 40 h de formação; NR-35: 8 h), nomes extraídos e semelhança de nome entre os dois documentos (abaixo de 85% rejeita). Qualquer falha não tratada também resulta em rejeição, nunca em aprovação silenciosa.

### Fluxo de CNPJ

```mermaid
flowchart TD
    A([CNPJ]) --> B["sanitiza e confere 14 dígitos"]
    B --> C["consulta a BrasilAPI"]
    C -->|"não existe"| X1([INVALID: não encontrado])
    C -->|"existe"| D{"ativo?"}
    D -->|"não"| X2([INVALID: inativo])
    D -->|"sim"| E["cnpj_agent<br/>analisa os CNAEs (LLM)"]
    E -->|"compatível com energia solar e elétrica"| OK([VALID])
    E -->|"incompatível"| X3([INVALID: categoria da empresa])
```
