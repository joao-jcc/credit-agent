"""
app/agent/state.py

Define o estado compartilhado que flui entre todos os nós do grafo.
No LangGraph, o estado é um TypedDict imutável — cada nó retorna
um dict parcial com apenas os campos que modificou.
"""

from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── Histórico de mensagens ────────────────────────────────────────────────
    # `add_messages` é um reducer especial do LangGraph: em vez de substituir
    # a lista, ele CONCATENA as novas mensagens às existentes.
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Dados coletados na autenticação ───────────────────────────────────────
    customer_name: str
    cpf: str
    authenticated: bool  # True após nome + CPF serem validados

    # ── Dados vindos do PostgreSQL ────────────────────────────────────────────
    customer_data: dict  # Ex: {"id": "uuid", "debt_amount": 5000.0, "overdue_days": 90}

    # ── Ofertas e negociação ──────────────────────────────────────────────────
    available_offers: list[dict]  # Ofertas carregadas do offers.json
    selected_offer: dict          # Oferta que o cliente aceitou
    negotiation_rounds: int       # Quantas rodadas de negociação já ocorreram
    debt_reason: str              # Motivo do endividamento extraído pela negociação

    # ── Resultado final ───────────────────────────────────────────────────────
    deal_closed: bool    # True se o acordo foi fechado com sucesso
    agreement_id: str    # UUID do acordo salvo na tabela `agreements`
    negotiation_status: str  # "accepted" | "rejected" | "countered" | ""

    # ── Controle interno ─────────────────────────────────────────────────────
    session_id: str      # UUID da sessão (vem da API)
    current_node: str    # Nome do nó atual (útil para debug e logging)
    error_message: str   # Mensagem de erro caso algo dê errado


# ── Estado inicial padrão ─────────────────────────────────────────────────────
# Use isso ao criar uma nova sessão via `graph.invoke(initial_state)`
def create_initial_state(session_id: str) -> AgentState:
    return AgentState(
        messages=[],
        customer_name="",
        cpf="",
        authenticated=False,
        customer_data={},
        available_offers=[],
        selected_offer={},
        negotiation_rounds=0,
        debt_reason="",
        deal_closed=False,
        agreement_id="",
        negotiation_status="",
        session_id=session_id,
        current_node="greeting",
        error_message="",
    )
