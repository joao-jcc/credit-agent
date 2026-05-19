"""
app/agent/nodes/close_deal.py

Salva o acordo fechado no PostgreSQL e confirma para o cliente.
"""

import uuid
from langchain_core.messages import AIMessage
from app.agent.state import AgentState
from app.agent.tools.db_tools import save_agreement


async def close_deal_node(state: AgentState) -> dict:
    offer = state["selected_offer"]
    customer = state["customer_data"]
    debt = float(customer["debt_amount"])

    discount = offer["discount_pct"] / 100
    agreed_amount = debt * (1 - discount)
    installments = offer["installments"]
    installment_value = agreed_amount / installments

    agreement_id = str(uuid.uuid4())

    # Salva no banco
    await save_agreement({
        "id": agreement_id,
        "customer_id": customer["id"],
        "session_id": state["session_id"],
        "original_debt": debt,
        "agreed_amount": agreed_amount,
        "installments": installments,
        "discount_pct": offer["discount_pct"],
    })

    # Formata valores para exibição
    def fmt(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    if installments == 1:
        payment_detail = f"Pagamento único de **{fmt(agreed_amount)}**"
    else:
        payment_detail = f"**{installments}x** de **{fmt(installment_value)}** (total: {fmt(agreed_amount)})"

    reply = AIMessage(content=(
        f"🎉 **Acordo fechado com sucesso!**\n\n"
        f"📄 **Resumo do seu acordo:**\n"
        f"• Dívida original: {fmt(debt)}\n"
        f"• Desconto aplicado: {offer['discount_pct']}%\n"
        f"• {payment_detail}\n"
        f"• Número do acordo: `{agreement_id[:8].upper()}`\n\n"
        "Você receberá um boleto/link de pagamento no seu e-mail cadastrado. "
        "Parabéns por dar esse passo! 💪"
    ))

    return {
        "messages": [reply],
        "deal_closed": True,
        "agreement_id": agreement_id,
        "current_node": "close_deal",
    }
