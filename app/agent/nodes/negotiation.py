"""
app/agent/nodes/negotiation.py

Nó central do loop de negociação.

O LLM interpreta a resposta do cliente e decide:
1. Cliente aceitou uma oferta → status "accepted" + selected_offer preenchido
2. Cliente ainda não aceitou → status "countered"; o nó defende a oferta atual.
   Somente após `rounds_per_offer` defesas sem aceitação o índice avança para a próxima.
   A revelação da nova oferta ocorre na rodada seguinte (nunca na mesma mensagem de defesa).
3. Cliente recusou categoricamente → status "farewell" (encerra sem acordo)

O prompt de sistema vive em app/agent/prompts.py (NEGOTIATION_SYSTEM).
"""

import json
from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agent.state import AgentState
from app.agent.prompts import NEGOTIATION_SYSTEM
from app.settings import settings


llm = ChatOpenAI(model="gpt-4o", temperature=0.3)


def _format_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")



async def negotiation_node(state: AgentState) -> dict:
    debt_amount = float(state["customer_data"]["debt_amount"])
    rounds = state["negotiation_rounds"]
    all_offers = state["available_offers"]
    known_debt_reason = state.get("debt_reason", "")

    # A oferta em discussão é controlada por current_offer_index (desacoplado das rodadas).
    offer_index = state.get("current_offer_index", 0)
    rounds_in_offer = state.get("rounds_in_offer", 0)

    # Ofertas já reveladas ao cliente (o LLM só pode falar dessas)
    revealed_offers = all_offers[: offer_index + 1]

    system = SystemMessage(content=NEGOTIATION_SYSTEM.format(
        agent_name=settings.agent_name,
        company_name=settings.company_name,
        offers=json.dumps(revealed_offers, ensure_ascii=False),
        round=rounds + 1,
        debt_amount=debt_amount,
        debt_reason=known_debt_reason or "desconhecido",
    ))

    recent_messages = state["messages"][-settings.history_window:]
    response = await llm.ainvoke([system] + recent_messages)

    try:
        data = json.loads(response.content)
    except json.JSONDecodeError:
        data = {
            "reply": response.content,
            "accepted_offer_id": None,
            "status": "countered",
            "debt_reason": "",
        }

    status = data.get("status", "countered")
    next_round = rounds + 1

    # Valores de controle de oferta (atualizados conforme defesa/avanço)
    new_offer_index = offer_index
    new_rounds_in_offer = rounds_in_offer

    reply_text = data["reply"]

    # Cliente ainda não aceitou: primeiro defendemos a oferta atual; só avançamos
    # para a próxima após defender ao menos `rounds_per_offer` vezes.
    # Quando o limite de defesas é atingido, apenas desbloqueamos a próxima oferta
    # para a rodada seguinte — a mensagem atual continua sendo só a defesa.
    # Na próxima invocação, o LLM verá a nova oferta em "revealed_offers" e a
    # apresentará de forma natural, sem misturar defesa e revelação numa mesma mensagem.
    if status == "countered":
        new_rounds_in_offer = rounds_in_offer + 1
        has_more_offers = offer_index + 1 < len(all_offers)
        should_advance = (
            new_rounds_in_offer >= settings.rounds_per_offer and has_more_offers
        )

        if should_advance:
            new_offer_index = offer_index + 1
            new_rounds_in_offer = 0
            # reply_text permanece como está (só defesa); a próxima oferta
            # será revelada pelo LLM na rodada seguinte.

    reply = AIMessage(content=reply_text)

    # Encontra a oferta aceita
    selected_offer = {}
    if data.get("accepted_offer_id"):
        selected_offer = next(
            (o for o in all_offers if o["id"] == data["accepted_offer_id"]),
            {}
        )
    # Fallback: se o LLM marcou "accepted" sem ID válido, usa a oferta atual
    if status == "accepted" and not selected_offer:
        selected_offer = all_offers[offer_index]

    result = {
        "messages": [reply],
        "selected_offer": selected_offer,
        "negotiation_rounds": next_round,
        "current_offer_index": new_offer_index,
        "rounds_in_offer": new_rounds_in_offer,
        "negotiation_status": status,
        "current_node": "negotiation",
    }

    # Persiste o motivo do endividamento quando o LLM o identificar
    new_debt_reason = (data.get("debt_reason") or "").strip()
    if new_debt_reason:
        result["debt_reason"] = new_debt_reason

    return result
