"""
app/agent/nodes/farewell.py

Encerramento da conversa — a mensagem varia conforme o desfecho:
1. Acordo fechado          → template fixo e caloroso
2. Falha na autenticação   → LLM (TASK_FAREWELL_NO_AUTH)
3. CPF não encontrado       → LLM (TASK_FAREWELL_NO_CUSTOMER)
4. Encerrou sem acordo      → LLM (TASK_FAREWELL_NO_DEAL)
"""

from langchain_core.messages import AIMessage
from app.agent.state import AgentState
from app.agent.prompts import (
    compose_reply,
    TASK_FAREWELL_DEAL,
    TASK_FAREWELL_NO_DEAL,
    TASK_FAREWELL_NO_AUTH,
    TASK_FAREWELL_NO_CUSTOMER,
)
from app.settings import settings


async def farewell_node(state: AgentState) -> dict:
    contact = settings.fallback_contact

    if state.get("deal_closed"):
        reply_text = await compose_reply(
            scenario="O acordo foi fechado com sucesso.",
            task=TASK_FAREWELL_DEAL,
            context={"fallback_contact": contact},
            messages=state.get("messages"),
            fallback=(
                "Foi um prazer te atender! Qualquer dúvida sobre seu acordo, "
                f"fale com a nossa central: **{contact}**.\n\nTenha um ótimo dia! 😊"
            ),
        )

    elif not state.get("authenticated"):
        reply_text = await compose_reply(
            scenario="Não foi possível validar a identidade do cliente.",
            task=TASK_FAREWELL_NO_AUTH,
            context={"fallback_contact": contact},
            messages=state.get("messages"),
            fallback=(
                "Não consegui validar sua identidade. "
                f"Por favor, entre em contato com a nossa central: **{contact}**.\n\nAté logo!"
            ),
        )

    elif not state.get("customer_data"):
        reply_text = await compose_reply(
            scenario="Nenhuma pendência foi encontrada para o CPF informado.",
            task=TASK_FAREWELL_NO_CUSTOMER,
            context={"fallback_contact": contact},
            messages=state.get("messages"),
            fallback=(
                "Não localizei nenhuma pendência associada ao seu CPF em nossa base. "
                f"Para mais informações, ligue para a nossa central: **{contact}**.\n\nAté logo!"
            ),
        )

    else:
        reply_text = await compose_reply(
            scenario="O cliente não fechou acordo nesta conversa.",
            task=TASK_FAREWELL_NO_DEAL,
            context={
                "fallback_contact": contact,
                "debt_reason": state.get("debt_reason", ""),
            },
            messages=state.get("messages"),
            fallback=(
                "Entendo que as condições não se encaixam no seu momento. "
                "Elas continuam disponíveis e você pode retornar quando quiser.\n\n"
                f"Para outras opções, ligue: **{contact}**.\n\nAté logo! 👋"
            ),
        )

    return {
        "messages": [AIMessage(content=reply_text)],
        "current_node": "farewell",
    }
