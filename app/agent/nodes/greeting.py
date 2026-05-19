"""
app/agent/nodes/greeting.py

Nó de saudação: primeiro contato com o cliente.
Retorna apenas as chaves do estado que foram modificadas.
"""

from langchain_core.messages import AIMessage
from app.agent.state import AgentState


async def greeting_node(state: AgentState) -> dict:
    """
    Ponto de entrada da conversa.
    Não precisa de LLM — mensagem fixa/template é suficiente aqui.
    """
    message = AIMessage(content=(
        "Olá! 👋 Bem-vindo à central de renegociação de dívidas.\n\n"
        "Estou aqui para te ajudar a quitar sua dívida da melhor forma possível. "
        "Temos condições especiais disponíveis hoje!\n\n"
        "Para começar, preciso verificar seus dados. "
        "Pode me dizer seu **nome completo**?"
    ))

    return {
        "messages": [message],
        "current_node": "greeting",
    }
