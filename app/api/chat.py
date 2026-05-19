"""
app/api/chat.py

Endpoints FastAPI que expõem o agente LangGraph como uma API REST.

O estado da sessão é mantido pelo MemorySaver do LangGraph (via thread_id).
Em produção, trocar por SqliteSaver ou RedisSaver para persistência entre réplicas.
"""

import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from app.agent.graph import compiled_graph
from app.agent.state import create_initial_state

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Apenas para rastrear sessões válidas — o estado fica no MemorySaver do grafo
_session_ids: set[str] = set()


# ── Schemas ───────────────────────────────────────────────────────────────────

class StartResponse(BaseModel):
    session_id: str
    message: str


class MessageRequest(BaseModel):
    session_id: str
    message: str


class MessageResponse(BaseModel):
    session_id: str
    message: str
    current_step: str
    deal_closed: bool
    agreement_id: str | None = None


class StatusResponse(BaseModel):
    session_id: str
    current_step: str
    authenticated: bool
    deal_closed: bool
    negotiation_rounds: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _last_ai_message(messages: list) -> str:
    return next(
        (m.content for m in reversed(messages)
         if hasattr(m, "content") and not isinstance(m, HumanMessage)),
        ""
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartResponse)
async def start_session():
    """Inicia uma nova sessão de negociação."""
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    initial_state = create_initial_state(session_id)

    # Roda o grafo até o primeiro interrupt (antes de authentication)
    await compiled_graph.ainvoke(initial_state, config=config)

    state = await compiled_graph.aget_state(config)
    _session_ids.add(session_id)

    return StartResponse(
        session_id=session_id,
        message=_last_ai_message(state.values.get("messages", [])),
    )


@router.post("/message", response_model=MessageResponse)
async def send_message(body: MessageRequest):
    """Recebe uma mensagem do usuário e avança o grafo."""
    if body.session_id not in _session_ids:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    config = {"configurable": {"thread_id": body.session_id}}

    # Injeta a mensagem do usuário no estado e retoma o grafo
    await compiled_graph.aupdate_state(
        config,
        {"messages": [HumanMessage(content=body.message)]},
    )
    await compiled_graph.ainvoke(None, config=config)

    state = await compiled_graph.aget_state(config)
    values = state.values

    return MessageResponse(
        session_id=body.session_id,
        message=_last_ai_message(values.get("messages", [])),
        current_step=values.get("current_node", "unknown"),
        deal_closed=values.get("deal_closed", False),
        agreement_id=values.get("agreement_id") or None,
    )


@router.get("/{session_id}/status", response_model=StatusResponse)
async def get_status(session_id: str):
    """Retorna o estado atual da sessão."""
    if session_id not in _session_ids:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    config = {"configurable": {"thread_id": session_id}}
    state = await compiled_graph.aget_state(config)
    values = state.values

    return StatusResponse(
        session_id=session_id,
        current_step=values.get("current_node", "unknown"),
        authenticated=values.get("authenticated", False),
        deal_closed=values.get("deal_closed", False),
        negotiation_rounds=values.get("negotiation_rounds", 0),
    )
