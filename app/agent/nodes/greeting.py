"""
app/agent/nodes/greeting.py

Nó de saudação: primeiro contato com o cliente.
Apresenta o assistente e pede o nome — SEM mencionar dívida/cobrança,
pois a identidade ainda não foi validada.
"""

from langchain_core.messages import AIMessage
from app.agent.state import AgentState
from app.agent.prompts import compose_reply, TASK_GREETING
from app.settings import settings


_FALLBACK = (
    f"Olá! Eu sou o assistente {settings.agent_name}, do {settings.company_name}. 👋\n\n"
    "Temos condições especiais disponíveis hoje. "
    "Para começar, pode me dizer seu **nome completo**?"
)


async def greeting_node(state: AgentState) -> dict:
    reply_text = await compose_reply(
        scenario="Primeiro contato com o cliente. Identidade ainda não validada.",
        task=TASK_GREETING,
        context={
            "agent_name": settings.agent_name,
            "company_name": settings.company_name,
        },
        messages=state.get("messages"),
        fallback=_FALLBACK,
    )

    return {
        "messages": [AIMessage(content=reply_text)],
        "current_node": "greeting",
    }
