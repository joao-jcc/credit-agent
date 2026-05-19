# Arquitetura do Credit Negotiation Agent

Guia completo para entender como o projeto funciona: do request HTTP até o LLM e o banco de dados.

---

## Visão geral

O sistema é um agente conversacional que conduz uma negociação de dívida de cartão de crédito. O usuário conversa via chat, e um grafo de estados (LangGraph) decide o que fazer a cada mensagem — autenticar, buscar dívida, apresentar ofertas, negociar e fechar o acordo.

```
Usuário (browser)
      │  HTTP POST /api/chat/message
      ▼
  FastAPI (chat.py)
      │  ainvoke / aupdate_state
      ▼
  LangGraph (graph.py)
      │  executa nós sequencialmente
      ▼
  Nós (nodes/)  ◄──► LLM (OpenAI GPT-4o)
      │               ◄──► PostgreSQL
      ▼
  Estado atualizado → resposta ao usuário
```

---

## 1. O Estado (AgentState)

O estado é um dicionário tipado (`TypedDict`) que **flui por todos os nós** do grafo. Cada nó lê o estado e retorna apenas os campos que modificou.

```python
# app/agent/state.py

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # histórico completo
    customer_name: str        # nome coletado na autenticação
    cpf: str                  # CPF em dígitos puros (ex: "12345678900")
    authenticated: bool       # True após nome + CPF válidos
    customer_data: dict       # dados do banco: id, debt_amount, overdue_days
    available_offers: list    # as 3 ofertas carregadas do JSON
    selected_offer: dict      # oferta quewhadis o cliente aceitou
    negotiation_rounds: int   # quantas rodadas de negociação já ocorreram
    negotiation_status: str   # "accepted" | "rejected" | "countered" | ""
    deal_closed: bool         # True se o acordo foi salvo no banco
    agreement_id: str         # UUID do acordo
    session_id: str           # UUID da sessão HTTP
    current_node: str         # nome do nó atual (para debug)
    error_message: str        # erros internos
```

### Como o campo `messages` funciona

O campo `messages` usa o reducer `add_messages` do LangGraph. Isso significa que, ao invés de substituir a lista, cada nó **concatena** suas mensagens ao histórico. O histório completo fica disponível para todos os nós.

Tipos de mensagem usados:
- `AIMessage` — resposta do agente
- `HumanMessage` — mensagem do usuário
- `SystemMessage` — instrução de sistema para o LLM (não aparece no chat)

---

## 2. O Grafo (LangGraph)

O grafo é montado em `app/agent/graph.py` usando `StateGraph`. Cada nó é uma função `async def` que recebe o estado e retorna um dict parcial.

### Fluxo completo

```
START
  └─► greeting
        └─► [interrupt] ◄── API pausa aqui e aguarda input do usuário
              └─► authentication ──► (loop se faltar dados)
                    │
                    ├─► farewell ──► END   (CPF não encontrado)
                    │
                    └─► fetch_customer
                          └─► fetch_offers
                                └─► [interrupt] ◄── API pausa e aguarda input
                                      └─► negotiation
                                            │
                                            ├─► close_deal ──► farewell ──► END  (aceitou)
                                            │
                                            ├─► [interrupt] ◄── nova rodada       (contraoferta)
                                            │
                                            └─► farewell ──► END                  (rejeitou tudo)
```

### Como o interrupt funciona

O grafo é compilado com `interrupt_before=["authentication", "negotiation"]`:

```python
compiled_graph = build_graph().compile(
    checkpointer=MemorySaver(),
    interrupt_before=["authentication", "negotiation"],
)
```

Isso faz o grafo **pausar automaticamente** antes desses dois nós e devolver o controle à API. O estado é salvo pelo `MemorySaver` (em memória). Na próxima chamada, o grafo retoma do ponto onde parou.

**Sequência de chamadas:**

| Chamada HTTP | O que o grafo faz | Pausa em |
|---|---|---|
| `POST /start` | roda `greeting` | antes de `authentication` |
| `POST /message` (nome/CPF) | roda `authentication` → (se autenticado) `fetch_customer` → `fetch_offers` | antes de `negotiation` |
| `POST /message` (resposta à oferta) | roda `negotiation` → (se aceito) `close_deal` → `farewell` | antes de `negotiation` novamente ou END |

### Funções roteadoras (edges condicionais)

As transições condicionais são funções que leem o estado e retornam o nome do próximo nó:

```python
def route_after_authentication(state) -> str:
    if state["authenticated"]:
        return "fetch_customer"
    return "authentication"          # loop: pede dados de novo

def route_after_fetch_customer(state) -> str:
    if state["customer_data"]:
        return "fetch_offers"
    return "farewell"                # CPF não encontrado

def route_after_negotiation(state) -> str:
    if state["selected_offer"]:
        return "close_deal"          # cliente aceitou
    if state.get("negotiation_status") == "rejected":
        return "farewell"            # cliente recusou todas as ofertas
    return "negotiation"             # continua negociando (interrupt vai pausar)
```

---

## 3. Os Nós

### `greeting` — sem LLM

Mensagem fixa de boas-vindas. Não usa LLM pois é texto estático.

```python
# Retorna apenas:
{"messages": [AIMessage(...)], "current_node": "greeting"}
```

---

### `authentication` — LLM para extração de dados

Usa `gpt-4o-mini` para extrair nome e CPF do que o usuário digitou, de forma natural.

**Prompt (extração):**
```
Analise a mensagem do usuário e extraia nome e CPF se presentes.
Retorne APENAS um JSON válido no formato:
{"nome": "string ou null", "cpf": "apenas dígitos ou null"}
```

**Lógica após a extração:**

| Situação | Resposta | `authenticated` |
|---|---|---|
| Tem nome + CPF com 11 dígitos | "Perfeito! Vou verificar..." | `True` |
| Tem nome, falta CPF | "Obrigado! Agora preciso do seu CPF..." | `False` |
| Falta nome | "Pode me informar seu nome completo?" | `False` |

Quando `authenticated == False`, o roteador devolve para `authentication` — mas como há `interrupt_before=["authentication"]`, o grafo pausa e a API aguarda a próxima mensagem do usuário.

---

### `fetch_customer` — consulta SQL direta

Sem LLM. Executa uma query no PostgreSQL:

```sql
SELECT id, name, cpf, debt_amount, overdue_days
FROM customers
WHERE cpf = :cpf
LIMIT 1
```

Se não encontrar → `customer_data = {}` → roteador envia para `farewell`.

Se encontrar → popula `customer_data` com os dados do banco.

---

### `fetch_offers` — carrega JSON + apresenta 1ª oferta

Sem LLM. Carrega `data/offers.json` (com cache via `@lru_cache`) e **apresenta apenas a primeira oferta** (à vista, maior desconto) para iniciar a negociação.

As 3 ofertas ficam em `available_offers` para serem reveladas progressivamente pelo nó `negotiation`.

---

### `negotiation` — LLM para negociação + revelação progressiva

Usa `gpt-4o` (modelo mais capaz) para interpretar a resposta do cliente.

**Revelação progressiva de ofertas:**

```
Rodada 0 (fetch_offers já apresentou): LLM vê apenas oferta 1 (à vista 50%)
Rodada 1 (cliente recusou):            LLM vê ofertas 1 e 2 (+ 6x 30%)
Rodada 2 (cliente recusou de novo):    LLM vê todas (+ 12x 15%)
```

A próxima oferta é exibida automaticamente no texto de resposta, sem depender do LLM para formatá-la.

**Prompt (system):**
```
Você é um negociador de dívidas simpático e empático da empresa FinanceX.

Regras:
- Você SOMENTE pode oferecer as opções listadas em "Ofertas desbloqueadas"
- Se o cliente não aceitar e ainda houver ofertas, use status "countered"
  (a próxima oferta aparecerá automaticamente na próxima rodada)
- Se o cliente aceitar, marque status "accepted" e informe o id da oferta
- Se o cliente rejeitar todas, use status "rejected"

Formato de resposta (JSON puro):
{
  "reply": "mensagem para o cliente",
  "accepted_offer_id": "id ou null",
  "status": "accepted | countered | rejected"
}

Ofertas desbloqueadas: [...]
Valor original da dívida: R$ X
Rodada atual: N
```

**O que o nó retorna:**

| Campo | Valor |
|---|---|
| `messages` | resposta do LLM (+ próxima oferta se houver) |
| `selected_offer` | oferta aceita (ou `{}`) |
| `negotiation_rounds` | incrementado em +1 |
| `negotiation_status` | `"accepted"` / `"countered"` / `"rejected"` |

**Fallback:** se o LLM retorna `status: "accepted"` mas sem `accepted_offer_id` válido, o nó usa a última oferta desbloqueada (a mais flexível disponível).

---

### `close_deal` — salva no banco, sem LLM

Calcula os valores finais e faz um `INSERT` na tabela `agreements`:

```sql
INSERT INTO agreements
    (id, customer_id, session_id, original_debt, agreed_amount,
     installments, discount_pct, created_at)
VALUES (...)
```

Retorna uma mensagem de confirmação com o resumo do acordo e um número de protocolo (primeiros 8 chars do UUID).

---

### `farewell` — sem LLM

Mensagem de encerramento baseada no desfecho:

| Condição | Mensagem |
|---|---|
| `deal_closed == True` | "Foi um prazer! Você receberá o boleto por e-mail." |
| `customer_data == {}` | "Não encontramos seu CPF. Ligue 0800-XXX-XXXX." |
| Sem acordo | "Entendemos. Nossas ofertas continuam disponíveis." |

---

## 4. As Tools (Ferramentas)

As tools são funções utilitárias chamadas pelos nós — não são "tools" do LLM (o LLM não as chama diretamente).

### `db_tools.py`

| Função | O que faz |
|---|---|
| `get_customer_by_cpf(cpf)` | Busca cliente no PostgreSQL. Retorna `dict` ou `None` |
| `save_agreement(data)` | Insere acordo na tabela `agreements` |

Ambas usam `async with get_session()` (SQLAlchemy async) e nunca expõem a conexão ao grafo diretamente.

### `offer_tools.py`

| Função | O que faz |
|---|---|
| `load_offers_for_debt(debt_amount)` | Carrega `data/offers.json` com `@lru_cache` — arquivo lido apenas uma vez |

---

## 5. A API (FastAPI)

### Gerenciamento de sessão

O estado da sessão é mantido pelo `MemorySaver` do LangGraph, identificado por `thread_id = session_id`. A API mantém apenas um `set` de IDs válidos para validar requisições.

```python
_session_ids: set[str] = set()
```

### Endpoints

#### `POST /api/chat/start`

```
1. Gera um UUID como session_id
2. Cria o estado inicial (todos os campos em branco/default)
3. Chama ainvoke(initial_state, config={"configurable": {"thread_id": session_id}})
4. O grafo roda greeting e pausa antes de authentication
5. Retorna a mensagem de greeting
```

#### `POST /api/chat/message`

```
1. Valida que a sessão existe
2. Injeta a mensagem do usuário no estado via aupdate_state()
3. Chama ainvoke(None, config) — retoma de onde parou
4. O grafo roda o próximo nó e pausa no próximo interrupt (ou termina)
5. Retorna a última AIMessage do histórico
```

#### `GET /api/chat/{session_id}/status`

```
1. Chama aget_state(config) para ler o estado atual do MemorySaver
2. Retorna: current_step, authenticated, deal_closed, negotiation_rounds
```

---

## 6. Banco de Dados

### Tabela `customers` (seed)

| CPF | Nome | Dívida | Atraso |
|---|---|---|---|
| 12345678901 | João Silva | R$ 3.200 | 45 dias |
| 98765432100 | Maria Santos | R$ 8.750 | 120 dias |
| 11122233344 | Carlos Oliveira | R$ 1.500 | 30 dias |
| 55566677788 | Ana Pereira | R$ 12.000 | 200 dias |
| 99988877766 | Pedro Costa | R$ 2.300 | 60 dias |

### Tabela `agreements`

Preenchida pelo nó `close_deal` quando o cliente aceita uma oferta.

---

## 7. As Ofertas

Definidas em `data/offers.json` e apresentadas **progressivamente**:

| Ordem de revelação | ID | Nome | Desconto | Parcelas |
|---|---|---|---|---|
| 1ª (sempre mostrada) | offer_001 | À Vista | 50% | 1x |
| 2ª (se recusar) | offer_002 | Parcelamento 6x | 30% | 6x |
| 3ª (se recusar de novo) | offer_003 | Parcelamento 12x | 15% | 12x |

---

## 8. Variáveis de Ambiente

| Variável | Onde é usada | Exemplo |
|---|---|---|
| `OPENAI_API_KEY` | `authentication.py`, `negotiation.py` | `sk-...` |
| `DATABASE_URL` | `app/db/connection.py` | `postgresql+asyncpg://...` |
| `OFFERS_FILE_PATH` | `offer_tools.py` | `data/offers.json` |
| `MAX_NEGOTIATION_ROUNDS` | não usado atualmente (lógica migrou para `negotiation_status`) | `3` |

---

## 9. Fluxo de uma conversa completa

```
Usuário: [abre o chat]
  → POST /start
  → grafo: greeting → [pause]
  ← "Olá! Bem-vindo à central de renegociação..."

Usuário: "Pedro Costa"
  → POST /message
  → grafo: authentication (extrai nome, falta CPF) → [pause]
  ← "Obrigado, Pedro! Preciso do seu CPF."

Usuário: "99988877766"
  → POST /message
  → grafo: authentication (authenticated=True)
         → fetch_customer (busca no banco, encontra Pedro)
         → fetch_offers (carrega JSON, revela oferta 1)
         → [pause]
  ← "Temos uma oferta: À Vista com 50% de desconto — R$ 1.150,00"

Usuário: "Não consigo pagar à vista"
  → POST /message
  → grafo: negotiation (rounds=0, vê só oferta 1, LLM→countered)
         → revela oferta 2 no texto
         → [pause]
  ← "Entendo! Posso oferecer 6x de R$ 268,39 com 30% de desconto."

Usuário: "Aceito o parcelamento em 6x"
  → POST /message
  → grafo: negotiation (rounds=1, LLM→accepted, selected_offer=offer_002)
         → close_deal (salva no banco)
         → farewell
         → END
  ← "Acordo fechado! Número: A1B2C3D4. Você receberá o boleto por e-mail."
```
