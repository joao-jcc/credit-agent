"""
app/agent/graph.py

Monta e compila o grafo de negociação com LangGraph.

Conceitos-chave:
- StateGraph: grafo onde cada nó lê e escreve no AgentState
- add_node: registra uma função como nó
- add_edge: transição incondicional A → B
- add_conditional_edges: transição baseada no retorno de uma função roteadora
- compile: retorna um `CompiledGraph` que pode ser invocado via .invoke() ou .stream()
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.state import AgentState
from app.settings import settings
from app.agent.nodes.greeting import greeting_node
from app.agent.nodes.authentication import authentication_node
from app.agent.nodes.fetch_customer import fetch_customer_node
from app.agent.nodes.fetch_offers import fetch_offers_node
from app.agent.nodes.negotiation import negotiation_node
from app.agent.nodes.close_deal import close_deal_node
from app.agent.nodes.farewell import farewell_node


# ── Funções roteadoras (decidem qual nó vem a seguir) ─────────────────────────

def route_after_authentication(state: AgentState) -> str:
    """Após autenticação: segue para busca de cliente ou fica no mesmo nó."""
    if state["authenticated"]:
        return "fetch_customer"
    # Usuário ainda não forneceu nome e CPF válidos: permanece no nó
    return "authentication"


def route_after_fetch_customer(state: AgentState) -> str:
    """Após buscar o cliente: segue para ofertas ou encerra se não encontrado."""
    if state["customer_data"]:
        return "fetch_offers"
    return "farewell"  # CPF não encontrado na base


def route_after_negotiation(state: AgentState) -> str:
    """
    Após cada rodada de negociação:
    - Aceitou oferta → fecha o acordo
    - LLM sinalizou "rejected"/"farewell" → encerra sem acordo
    - Atingiu o limite de rodadas → encerra sem acordo
    - Caso contrário → continua negociando
    """
    if state["selected_offer"]:
        return "close_deal"

    if state.get("negotiation_status") in ("rejected", "farewell"):
        return "farewell"

    if state["negotiation_rounds"] >= settings.max_negotiation_rounds:
        return "farewell"

    return "negotiation"


# ── Montagem do grafo ─────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Registra os nós
    graph.add_node("greeting", greeting_node)
    graph.add_node("authentication", authentication_node)
    graph.add_node("fetch_customer", fetch_customer_node)
    graph.add_node("fetch_offers", fetch_offers_node)
    graph.add_node("negotiation", negotiation_node)
    graph.add_node("close_deal", close_deal_node)
    graph.add_node("farewell", farewell_node)

    # Edges fixas
    graph.add_edge(START, "greeting")
    graph.add_edge("greeting", "authentication")
    graph.add_edge("fetch_offers", "negotiation")
    graph.add_edge("close_deal", "farewell")
    graph.add_edge("farewell", END)

    # Edges condicionais
    graph.add_conditional_edges(
        "authentication",
        route_after_authentication,
        {
            "fetch_customer": "fetch_customer",
            "authentication": "authentication",
        },
    )

    graph.add_conditional_edges(
        "fetch_customer",
        route_after_fetch_customer,
        {
            "fetch_offers": "fetch_offers",
            "farewell": "farewell",
        },
    )

    graph.add_conditional_edges(
        "negotiation",
        route_after_negotiation,
        {
            "close_deal": "close_deal",
            "negotiation": "negotiation",
            "farewell": "farewell",
        },
    )

    return graph


# Instância compilada — importada pelo resto da aplicação
# interrupt_before pausa o grafo antes dos nós que precisam de input do usuário
_memory = MemorySaver()
compiled_graph = build_graph().compile(
    checkpointer=_memory,
    interrupt_before=["authentication", "negotiation"],
)
