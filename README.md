# Promptune

Backend de uma ferramenta para engenheiros de prompt que trabalham com agentes de IA: importe prompts em Markdown, peça melhorias em linguagem
natural, revise as alterações propostas e mantenha um histórico de versões.

## Como rodar

```bash
cp .env.example .env          # preencha LLM_API_KEY e JWT_SECRET
uv sync --extra groq          # pacote do provedor da LLM
docker compose up -d          # Postgres + RabbitMQ
uv run alembic upgrade head   # aplica as migrations
uv run fastapi dev            # API
uv run promptune-worker       # worker, em outro terminal
```

O painel de administração do RabbitMQ fica em http://localhost:15672
(usuário e senha padrão `app`/`app`, configuráveis por `RABBITMQ_USER` e
`RABBITMQ_PASSWORD`).

`uv run promptune-worker --once` consome no máximo uma mensagem da fila, processa e encerra.

### Escolhendo o modelo

O agente funciona com qualquer provedor suportado pelo LangChain. Instale o
pacote do provedor e configure o `.env`:

```bash
uv sync --extra openai        # extras disponíveis: openai, anthropic, groq (gratuito)
uv add langchain-<provedor>   # para outro provedor, ex.: langchain-google-genai
```

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=sk-...
LLM_BASE_URL=                 # opcional, para endpoints compatíveis com OpenAI
```

## Stack

![Python](https://img.shields.io/badge/Python_3.14-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=flat&logo=sqlalchemy&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat&logo=rabbitmq&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=flat&logo=langchain&logoColor=white)
![JWT](https://img.shields.io/badge/PyJWT-000000?style=flat&logo=jsonwebtokens&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?style=flat&logo=ruff&logoColor=black)
![SSE](https://img.shields.io/badge/SSE-555555?style=flat)

- **API:** FastAPI, com acompanhamento das runs via Server-Sent Events
- **Banco:** PostgreSQL com SQLAlchemy assíncrono
- **Fila:** RabbitMQ com aio-pika
- **LLM:** LangChain
- **Autenticação:** PyJWT
- **Lint:** Ruff

O código é organizado por domínios em `src/promptune/modules/` (`agent`, `prompt`,
`prompt_proposal`, `session`, `message`, `agent_run`, `auth`).

## Desafio arquitetural

Uma chamada à LLM leva de segundos a mais de um minuto, pode falhar de forma
transitória (rate limit, timeout, indisponibilidade do provedor) e é cara. Não
dá para segurar a requisição HTTP aberta enquanto ela acontece, e também não
dá para perder um pedido nem gravar uma resposta duas vezes. O desafio é aceitar
o pedido na hora, processá-lo fora da requisição e manter o estado sempre
consistente, mesmo quando o worker morre no meio, o broker cai ou a mesma
mensagem é entregue duas vezes.

A solução separa três responsabilidades:

- **Estado: PostgreSQL.** É a fonte da verdade de cada run (status, tentativas,
  erro e resultado). Um índice único parcial garante no máximo uma run ativa por
  sessão.
- **Entrega: RabbitMQ.** Transporta apenas o `run_id`. Ele não guarda estado e
  pode perder ou duplicar mensagens sem corromper o banco.
- **Acompanhamento: SSE.** O cliente acompanha a run por
  `GET /agent-runs/{id}/events`, alimentado pelo `LISTEN/NOTIFY` do Postgres,
  sem depender da fila.

### Fluxo de uma mensagem

1. `POST /sessions/{id}/messages` grava a mensagem e uma run `queued` na mesma
   transação, faz o commit e só então publica `{"run_id": ...}`. Publicar antes
   do commit faria o worker procurar uma run que ainda não existe.
2. Se a publicação falhar, a run é marcada como `failed` (`queue_unavailable`),
   a sessão é liberada e a API responde `503`. O usuário pode reenviar.
3. O worker assume a run pelo id com um único `UPDATE` atômico, que incrementa
   `attempt_count`. Runs já concluídas, canceladas ou de sessões inativas são
   ignoradas, o que torna entregas duplicadas inofensivas.
4. A LLM é chamada com um limite de tempo. O resultado só é gravado se a run
   ainda pertencer àquela tentativa (*fencing* por `attempt_count`). Se outra
   tentativa já assumiu, o resultado é descartado.
5. Só depois do commit o worker confirma (ack) a mensagem. Se ele morrer antes
   disso, o RabbitMQ reentrega a mensagem e outro worker continua.

A entrega é *pelo menos uma vez*: todo o processamento é idempotente em relação
ao `run_id`.

## Testes

```bash
uv run pytest                                   # testes unitários
uv run pytest tests/http tests/integration      # exigem Docker (testcontainers)
uv run ruff check                               # lint
```
