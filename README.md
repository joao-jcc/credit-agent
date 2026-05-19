# 💳 Credit Negotiation Agent

Agente de IA para renegociação de dívidas de cartão de crédito usando **LangGraph + FastAPI + PostgreSQL**.

---

## Visão Geral

O agente conduz o cliente endividado por um fluxo conversacional estruturado:

```
Saudação → Autenticação → Busca de Dados → Apresentação de Ofertas → Loop de Negociação → Fechamento → Encerramento
```

Cada etapa é um **nó** no grafo do LangGraph. As transições são controladas por **edges condicionais** baseadas no estado da conversa.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Agente / Orquestração | LangGraph |
| LLM | OpenAI GPT-4o (ou Anthropic Claude) |
| API | FastAPI |
| Banco de Dados | PostgreSQL (asyncpg / SQLAlchemy async) |
| Ofertas | Arquivo JSON local (futuro: API externa) |
| Containerização | Docker + docker-compose |

---

## Estrutura do Projeto

```
credit-negotiation-agent/
├── app/
│   ├── main.py                   # Entry point FastAPI
│   ├── api/
│   │   └── chat.py               # Endpoints REST da conversa
│   ├── agent/
│   │   ├── graph.py              # Definição do grafo LangGraph
│   │   ├── state.py              # Definição do AgentState (TypedDict)
│   │   ├── nodes/
│   │   │   ├── greeting.py       # Nó: Saudação inicial
│   │   │   ├── authentication.py # Nó: Coleta e valida nome + CPF
│   │   │   ├── fetch_customer.py # Nó: Busca dados do cliente no PostgreSQL
│   │   │   ├── fetch_offers.py   # Nó: Busca ofertas no arquivo JSON
│   │   │   ├── negotiation.py    # Nó: Loop de negociação (aceite/contraproposta)
│   │   │   ├── close_deal.py     # Nó: Fecha o acordo e salva no banco
│   │   │   └── farewell.py       # Nó: Encerramento do atendimento
│   │   └── tools/
│   │       ├── db_tools.py       # Funções de acesso ao PostgreSQL
│   │       └── offer_tools.py    # Funções de leitura do arquivo de ofertas
│   ├── db/
│   │   ├── connection.py         # Configuração do SQLAlchemy async
│   │   └── models.py             # Modelos ORM (Customer, Agreement)
│   ├── models/                   # Modelos Pydantic de domínio
│   │   └── domain.py
│   └── schemas/                  # Schemas de request/response da API
│       └── chat.py
├── data/
│   ├── offers.json               # Ofertas de renegociação (mock)
│   └── seed.sql                  # Dados fake para o PostgreSQL
├── scripts/
│   └── init_db.py                # Script para criar tabelas e popular o banco
├── tests/
│   └── test_agent.py             # Testes básicos do fluxo
├── .env.example                  # Variáveis de ambiente necessárias
├── docker-compose.yml            # PostgreSQL + app
├── Dockerfile
└── requirements.txt
```

---

## Fluxo do Grafo (LangGraph)

```
[START]
   │
   ▼
[greeting]          → mensagem de boas-vindas
   │
   ▼
[authentication]    → coleta nome + CPF do usuário
   │
   ▼
[fetch_customer]    → busca dívidas no PostgreSQL por CPF
   │
   ├── cliente não encontrado → [farewell]
   │
   ▼
[fetch_offers]      → carrega ofertas do arquivo JSON filtradas pela dívida
   │
   ▼
[negotiation]  ◄────────────────────┐
   │                                │
   ├── usuário aceita oferta         │
   │       ▼                        │
   │   [close_deal]                 │
   │       ▼                        │
   │   [farewell] → [END]           │
   │                                │
   ├── usuário faz contraproposta ──►│ (loop, máx 3x)
   │
   └── máx tentativas esgotadas → [farewell]
```

---

## Estado do Agente (`AgentState`)

```python
class AgentState(TypedDict):
    messages: list[BaseMessage]       # Histórico completo da conversa
    customer_name: str                # Nome coletado na autenticação
    cpf: str                          # CPF coletado na autenticação
    authenticated: bool               # Flag de autenticação bem-sucedida
    customer_data: dict               # Dados do cliente vindos do PostgreSQL
    available_offers: list[dict]      # Ofertas carregadas do JSON
    selected_offer: dict              # Oferta escolhida/aceita
    negotiation_rounds: int           # Contador de rodadas de negociação
    deal_closed: bool                 # Flag de acordo fechado
    agreement_id: str                 # ID do acordo salvo no banco
    current_node: str                 # Nó atual (para debug)
```

---

## API Endpoints

### `POST /api/chat/start`
Inicia uma nova sessão de negociação.

**Response:**
```json
{
  "session_id": "uuid",
  "message": "Olá! Bem-vindo à central de renegociação..."
}
```

### `POST /api/chat/message`
Envia uma mensagem do usuário e recebe a resposta do agente.

**Request:**
```json
{
  "session_id": "uuid",
  "message": "Meu nome é João Silva"
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "message": "Obrigado, João! Agora preciso do seu CPF...",
  "current_step": "authentication",
  "deal_closed": false
}
```

### `GET /api/chat/{session_id}/status`
Retorna o estado atual da sessão.

---

## Banco de Dados

### Tabela `customers`
```sql
id          UUID PRIMARY KEY
name        VARCHAR
cpf         VARCHAR(11) UNIQUE
debt_amount DECIMAL         -- valor total da dívida
overdue_days INTEGER        -- dias em atraso
created_at  TIMESTAMP
```

### Tabela `agreements`
```sql
id              UUID PRIMARY KEY
customer_id     UUID REFERENCES customers(id)
session_id      UUID
original_debt   DECIMAL
agreed_amount   DECIMAL
installments    INTEGER
discount_pct    DECIMAL
created_at      TIMESTAMP
```

---

## Arquivo de Ofertas (`data/offers.json`)

```json
{
  "offers": [
    {
      "id": "offer_001",
      "name": "Pagamento à Vista",
      "discount_pct": 50,
      "installments": 1,
      "description": "Quite hoje com 50% de desconto"
    },
    {
      "id": "offer_002",
      "name": "Parcelamento em 6x",
      "discount_pct": 30,
      "installments": 6,
      "description": "Parcele em 6x com 30% de desconto"
    },
    {
      "id": "offer_003",
      "name": "Parcelamento em 12x",
      "discount_pct": 15,
      "installments": 12,
      "description": "Parcele em 12x com 15% de desconto"
    }
  ]
}
```

---

## Como Rodar

```bash
# 1. Clone e entre no projeto
git clone <repo>
cd credit-negotiation-agent

# 2. Copie o .env
cp .env.example .env
# Edite o .env com sua OPENAI_API_KEY e configs do banco

# 3. Suba o PostgreSQL
docker-compose up -d postgres

# 4. Instale dependências
pip install -r requirements.txt

# 5. Inicialize o banco com dados fake
python scripts/init_db.py

# 6. Rode a API
uvicorn app.main:app --reload

# 7. Teste
curl -X POST http://localhost:8000/api/chat/start
```

---

## Variáveis de Ambiente (`.env`)

```
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/negotiation_db
OFFERS_FILE_PATH=data/offers.json
MAX_NEGOTIATION_ROUNDS=3
```

---

## Próximos Passos (produção)

- [ ] Substituir busca de ofertas por chamada a API externa
- [ ] Adicionar autenticação JWT nos endpoints
- [ ] Persistir sessões no Redis (não em memória)
- [ ] Adicionar observabilidade com LangSmith
- [ ] Webhooks para notificar CRM ao fechar acordo
