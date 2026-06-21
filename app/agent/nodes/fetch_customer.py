"""
app/agent/nodes/fetch_customer.py

Busca os dados do cliente no PostgreSQL usando o CPF autenticado e apresenta
a situação de forma empática (via LLM). Lê apenas colunas existentes; o nome do
produto vem de settings (não há coluna de produto no banco).
"""

from langchain_core.messages import AIMessage
from app.agent.state import AgentState
from app.agent.tools.db_tools import get_customer_by_cpf
from app.agent.prompts import compose_reply, TASK_DEBT_FOUND
from app.settings import settings


def _first_name(full_name: str) -> str:
    return (full_name or "").strip().split(" ")[0]


def _format_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def fetch_customer_node(state: AgentState) -> dict:
    customer = await get_customer_by_cpf(state["cpf"])

    if not customer:
        # farewell_node é o único emissor da mensagem de "não encontrado"
        return {
            "customer_data": {},
            "current_node": "fetch_customer",
        }

    first_name = _first_name(state.get("customer_name", ""))
    debt_amount = float(customer["debt_amount"])
    debt_formatted = _format_brl(debt_amount)

    reply_text = await compose_reply(
        scenario="Apresentando a situação ao cliente logo após a autenticação.",
        task=TASK_DEBT_FOUND,
        context={
            "user_name": first_name,
            "product": settings.product_name,
            "debt_amount": debt_formatted,
            "overdue_days": customer["overdue_days"],
        },
        messages=state.get("messages"),
        fallback=(
            f"Localizei uma pendência no seu {settings.product_name}, **{first_name}**.\n\n"
            f"• Valor: **{debt_formatted}**\n"
            f"• Em atraso há **{customer['overdue_days']} dias**\n\n"
            "Temos uma condição especial para regularizar isso hoje. "
            "Deixa eu buscar a melhor opção para você..."
        ),
    )

    return {
        "messages": [AIMessage(content=reply_text)],
        "customer_data": customer,
        "current_node": "fetch_customer",
    }
