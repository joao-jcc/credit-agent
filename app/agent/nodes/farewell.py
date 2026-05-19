"""
app/agent/nodes/farewell.py

Encerramento da conversa — mensagem varia conforme o desfecho.
"""

from langchain_core.messages import AIMessage
from app.agent.state import AgentState


async def farewell_node(state: AgentState) -> dict:
    if state.get("deal_closed"):
        content = (
            "Foi um prazer te atender! Qualquer dúvida sobre seu acordo, "
            "entre em contato com nossa central.\n\n"
            "Tenha um ótimo dia! 😊"
        )
    elif not state.get("customer_data"):
        content = (
            "Não conseguimos localizar seus dados em nossa base. "
            "Por favor, ligue para nossa central: **0800-XXX-XXXX**.\n\n"
            "Até logo!"
        )
    else:
        # Esgotou rodadas sem acordo
        content = (
            "Entendo que as condições disponíveis não se encaixam no seu momento. "
            "Nossas ofertas ficam disponíveis e você pode retornar quando quiser.\n\n"
            "Para outras opções, ligue: **0800-XXX-XXXX**.\n\n"
            "Até logo! 👋"
        )

    return {
        "messages": [AIMessage(content=content)],
        "current_node": "farewell",
    }
