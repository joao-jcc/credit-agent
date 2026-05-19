# CLAUDE.md — Credit Negotiation Agent

Guia de referência para o Cursor e Claude Code entenderem e evoluírem este projeto.

---

## O que é este projeto

Agente conversacional de IA que conduz renegociações de dívida de cartão de crédito de forma autônoma.
O agente assume o papel de um atendente de cobrança: autentica o cliente, busca sua dívida, apresenta ofertas, negocia em loop e fecha (ou não) um acordo — tudo via chat.

Stack: **FastAPI + LangGraph + PostgreSQL + OpenAI GPT-4o**

---

## Estrutura de arquivos

```
credit-negotiation-agent/
├── CLAUDE.md                          # este arquivo
├── .env.example                       # variáveis necessárias — copie para .env
├── docker-compose.yml                 # sobe postgres + app
├── Dockerfile
├── pyproject.toml                     # dependências gerenciadas pelo uv
├── uv.lock                            # lockfile gerado automaticamente
│
├── app/
│   ├── main.py                        # entry point FastAPI, registra routers
│   ├── settings.py                    # configurações via pydantic-settings (lê .env)
│   │
│   ├── api/
│   │   └── chat.py                    # endpoints: POST /start  POST /message  GET /{id}/status
│   │
│   ├── agent/
│   │   ├── state.py                   # AgentState (TypedDict) — estado que flui entre os nós
│   │   ├── graph.py                   # monta e compila o StateGraph do LangGraph
│   │   │
│   │   ├── nodes/                     # cada nó é uma função async que recebe e retorna estado parcial
│   │   │   ├── greeting.py            # boas-vindas, pede o nome
│   │   │   ├── authentication.py      # coleta nome + CPF via LLM, valida formato
│   │   │   ├── fetch_customer.py      # busca dívida no PostgreSQL pelo CPF
│   │   │   ├── fetch_offers.py        # carrega ofertas do JSON, apresenta com valores calculados
│   │   │   ├── negotiation.py         # loop: interpreta resposta, aceite / contraproposta / recusa
│   │   │   ├── close_deal.py          # salva acordo no banco, gera protocolo
│   │   │   └── farewell.py            # encerramento (acordo fechado, CPF não encontrado, ou sem acordo)
│   │   │
│   │   └── tools/
│   │       ├── db_tools.py            # get_customer_by_cpf(), save_agreement()
│   │       └── offer_tools.py         # load_offers_for_debt() — lê offers.json com cache
│   │
│   └── db/
│       ├── connection.py              # engine async SQLAlchemy, AsyncSessionLocal, get_session()
│       └── models.py                  # ORM: Customer, Agreement
│
├── data/
│   ├── seed.sql                       # CREATE TABLE + 5 clientes fake
│   └── offers.json                    # 3 ofertas: à vista 50%, 6x 30%, 12x 15%
│
└── scripts/
    └── init_db.py                     # roda seed.sql no banco (alternativa ao docker entrypoint)
```

---

## Fluxo do grafo (LangGraph)

```
START
  └─► greeting          mensagem de boas-vindas, pede nome
        └─► authentication   coleta nome + CPF; fica em loop até ter os dois
              ├─► farewell            se CPF não encontrado no banco
              └─► fetch_customer      busca dívida no PostgreSQL
                    └─► fetch_offers  carrega e apresenta ofertas
                          └─► negotiation  ◄─────────────────────┐
                                ├─► close_deal  acordo aceito      │
                                │     └─► farewell ──► END         │
                                ├─► negotiation  contraproposta ───┘  (máx 3x)
                                └─► farewell     esgotou rodadas ──► END
```

**Regras das edges condicionais:**

- `authentication` → repete enquanto `authenticated == False`
- `fetch_customer` → vai para `farewell` se `customer_data` estiver vazio
- `negotiation` → vai para `close_deal` se `selected_offer` estiver preenchido; para `farewell` se `negotiation_rounds >= MAX_NEGOTIATION_ROUNDS`; caso contrário repete

---

## AgentState — campos e responsáveis

| Campo | Tipo | Quem escreve | Significado |
|---|---|---|---|
| `messages` | `list[BaseMessage]` | todos os nós | histórico completo (reducer `add_messages` concatena) |
| `customer_name` | `str` | authentication | nome coletado |
| `cpf` | `str` | authentication | CPF em dígitos puros |
| `authenticated` | `bool` | authentication | True quando tem nome + CPF válidos |
| `customer_data` | `dict` | fetch_customer | linha do banco: id, debt_amount, overdue_days |
| `available_offers` | `list[dict]` | fetch_offers | ofertas carregadas do JSON |
| `selected_offer` | `dict` | negotiation | oferta aceita pelo cliente |
| `negotiation_rounds` | `int` | negotiation | contador de rodadas |
| `deal_closed` | `bool` | close_deal | True se acordo foi salvo |
| `agreement_id` | `str` | close_deal | UUID do acordo no banco |
| `session_id` | `str` | API (chat.py) | UUID da sessão HTTP |
| `current_node` | `str` | cada nó | para debug e roteamento da resposta da API |

---

## API — endpoints

### `POST /api/chat/start`
Cria sessão, roda o grafo até o greeting e devolve a primeira mensagem.
```json
// response
{ "session_id": "uuid", "message": "Olá! Bem-vindo..." }
```

### `POST /api/chat/message`
Recebe mensagem do usuário, injeta no estado como `HumanMessage`, reinvoca o grafo.
```json
// request
{ "session_id": "uuid", "message": "Meu nome é João, CPF 123.456.789-00" }

// response
{ "session_id": "uuid", "message": "...", "current_step": "authentication", "deal_closed": false }
```

### `GET /api/chat/{session_id}/status`
Devolve snapshot do estado da sessão.

**Armazenamento de sessão:** dict em memória (`_sessions`). Em produção: Redis.

---

## Banco de dados

### Tabela `customers`
```sql
id           UUID PK
name         VARCHAR(200)
cpf          VARCHAR(11) UNIQUE
debt_amount  DECIMAL(12,2)
overdue_days INTEGER
email        VARCHAR(200)
phone        VARCHAR(20)
created_at   TIMESTAMP DEFAULT NOW()
```

### Tabela `agreements`
```sql
id            UUID PK
customer_id   UUID FK → customers.id
session_id    UUID
original_debt DECIMAL(12,2)
agreed_amount DECIMAL(12,2)
installments  INTEGER
discount_pct  DECIMAL(5,2)
created_at    TIMESTAMP DEFAULT NOW()
```

---

## Variáveis de ambiente (`.env`)

| Variável | Descrição | Exemplo |
|---|---|---|
| `OPENAI_API_KEY` | Chave da OpenAI | `sk-...` |
| `DATABASE_URL` | URL async do PostgreSQL | `postgresql+asyncpg://postgres:postgres@localhost:5432/negotiation_db` |
| `OFFERS_FILE_PATH` | Caminho do JSON de ofertas | `data/offers.json` |
| `MAX_NEGOTIATION_ROUNDS` | Máximo de rodadas antes de encerrar | `3` |

Todas lidas via `app/settings.py` (pydantic-settings). **Nunca hardcodar valores no código.**

---

## Como rodar localmente

```bash
# 1. Copiar .env
cp .env.example .env
# Preencher OPENAI_API_KEY

# 2. Subir o banco
docker-compose up -d postgres

# 3. Instalar dependências (uv cria o .venv automaticamente)
uv sync

# 4. Inicializar banco com dados fake
uv run python scripts/init_db.py

# 5. Rodar a API
uv run uvicorn app.main:app --reload

# 6. Testar
curl -X POST http://localhost:8000/api/chat/start
```

---

## Convenções do projeto

- Todos os nós são funções `async def node_name(state: AgentState) -> dict`
- Nós **nunca** retornam o estado completo — só os campos que modificaram
- O LLM é usado apenas para linguagem natural (extrair dados, gerar respostas de negociação). A lógica de fluxo fica nas edges condicionais do grafo, não no LLM
- Strings de prompt ficam como constantes no topo do arquivo do nó que as usa
- Acesso ao banco sempre via `async with get_session() as session` de `app/db/connection.py`
- Nunca importar `settings` diretamente nos nós — passar via estado ou via tools

---

## Próximos passos conhecidos

- [ ] Substituir armazenamento de sessão em memória por Redis
- [ ] Adicionar autenticação JWT nos endpoints
- [ ] Substituir `offer_tools.py` por chamada a API externa
- [ ] Integrar LangSmith para observabilidade do grafo
- [ ] Adicionar testes de integração do fluxo completo
