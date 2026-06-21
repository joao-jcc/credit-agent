"""
app/agent/nodes/fetch_offers.py

Carrega ofertas de renegociação do arquivo JSON e as apresenta ao cliente.
Em produção, este nó fará uma chamada a uma API externa.
"""

from langchain_core.messages import AIMessage
from app.agent.state import AgentState
from app.agent.tools.offer_tools import load_offers_for_debt


def _format_offer(debt_amount: float, offer: dict, index: int) -> str:
    discounted = debt_amount * (1 - offer["discount_pct"] / 100)
    discounted_fmt = f"R$ {discounted:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    installment_value = discounted / offer["installments"]
    installment_fmt = f"R$ {installment_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    if offer["installments"] == 1:
        detail = f"Pagamento único de **{discounted_fmt}**"
    else:
        detail = f"**{offer['installments']}x** de **{installment_fmt}** (total: {discounted_fmt})"

    return (
        f"**Opção {index} — {offer['name']}** ({offer['discount_pct']}% de desconto)\n"
        f"  {detail}\n"
        f"  _{offer['description']}_"
    )


async def fetch_offers_node(state: AgentState) -> dict:
    debt_amount = float(state["customer_data"]["debt_amount"])
    overdue_days = int(state["customer_data"].get("overdue_days", 0))
    offers = await load_offers_for_debt(debt_amount, overdue_days)

    # Apresenta apenas a primeira oferta (mais vantajosa) para começar a negociação
    first_offer = _format_offer(debt_amount, offers[0], 1)

    reply = AIMessage(content=(
        f"Ótima notícia! Temos uma oferta especial para você hoje:\n\n"
        f"{first_offer}\n\n"
        "O que acha dessa condição?"
    ))

    return {
        "messages": [reply],
        "available_offers": offers,
        "current_node": "fetch_offers",
    }
