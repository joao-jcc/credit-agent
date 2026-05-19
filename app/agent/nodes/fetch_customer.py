"""
app/agent/nodes/fetch_customer.py

Busca os dados do cliente no PostgreSQL usando o CPF autenticado.
"""

from langchain_core.messages import AIMessage
from app.agent.state import AgentState
from app.agent.tools.db_tools import get_customer_by_cpf


async def fetch_customer_node(state: AgentState) -> dict:
    customer = await get_customer_by_cpf(state["cpf"])

    if not customer:
        reply = AIMessage(content=(
            "Hmm, não encontrei nenhuma dívida associada ao seu CPF em nossa base. "
            "Por favor, entre em contato com nossa central para mais informações."
        ))
        return {
            "messages": [reply],
            "customer_data": {},
            "current_node": "fetch_customer",
        }

    debt_formatted = f"R$ {float(customer['debt_amount']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    reply = AIMessage(content=(
        f"Localizei sua dívida, **{state['customer_name']}**.\n\n"
        f"📋 **Resumo da sua situação:**\n"
        f"• Valor da dívida: **{debt_formatted}**\n"
        f"• Dias em atraso: **{customer['overdue_days']} dias**\n\n"
        "Temos condições especiais para você regularizar isso hoje. "
        "Deixa eu buscar as melhores ofertas disponíveis..."
    ))

    return {
        "messages": [reply],
        "customer_data": customer,
        "current_node": "fetch_customer",
    }
