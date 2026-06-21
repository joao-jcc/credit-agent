"""
app/agent/nodes/negotiation.py

Nó central do loop de negociação.

O LLM interpreta a resposta do cliente e decide:
1. Cliente aceitou uma oferta → status "accepted" + selected_offer preenchido
2. Cliente não aceitou e há mais condições → status "countered" (revela a próxima)
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

    # Desbloqueia ofertas progressivamente: rodada 0 → 1ª oferta, rodada 1 → 2ª, etc.
    unlocked_offers = all_offers[: rounds + 1]

    system = SystemMessage(content=NEGOTIATION_SYSTEM.format(
        agent_name=settings.agent_name,
        company_name=settings.company_name,
        offers=json.dumps(unlocked_offers, ensure_ascii=False),
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
    has_more_offers = next_round < len(all_offers)

    # Revela a próxima condição apenas quando o cliente continua negociando
    if status == "countered" and has_more_offers:
        next_offer = all_offers[next_round]
        disc = debt_amount * (1 - next_offer["discount_pct"] / 100)
        disc_fmt = _format_brl(disc)
        inst_val = disc / next_offer["installments"]
        inst_fmt = _format_brl(inst_val)

        if next_offer["installments"] == 1:
            detail = f"pagamento único de **{disc_fmt}**"
        else:
            detail = f"**{next_offer['installments']}x** de **{inst_fmt}** (total: {disc_fmt})"

        reply_text = (
            f"{data['reply']}\n\n"
            f"Posso oferecer uma condição melhor: **{next_offer['name']}** "
            f"com {next_offer['discount_pct']}% de desconto — {detail}. O que acha?"
        )
    else:
        reply_text = data["reply"]

    reply = AIMessage(content=reply_text)

    # Encontra a oferta aceita
    selected_offer = {}
    if data.get("accepted_offer_id"):
        selected_offer = next(
            (o for o in all_offers if o["id"] == data["accepted_offer_id"]),
            {}
        )
    # Fallback: se o LLM marcou "accepted" sem ID válido, usa a última oferta desbloqueada
    if status == "accepted" and not selected_offer:
        selected_offer = unlocked_offers[-1]

    result = {
        "messages": [reply],
        "selected_offer": selected_offer,
        "negotiation_rounds": next_round,
        "negotiation_status": status,
        "current_node": "negotiation",
    }

    # Persiste o motivo do endividamento quando o LLM o identificar
    new_debt_reason = (data.get("debt_reason") or "").strip()
    if new_debt_reason:
        result["debt_reason"] = new_debt_reason

    return result
