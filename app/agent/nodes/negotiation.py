"""
app/agent/nodes/negotiation.py

Nó central do loop de negociação.

O LLM interpreta a resposta do cliente e decide:
1. Cliente aceitou uma oferta → retorna selected_offer preenchido
2. Cliente fez contraproposta → tenta adaptar e contra-ofertar
3. Cliente recusou tudo → incrementa rodada, o roteador decidirá encerrar se necessário
"""

import json
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.agent.state import AgentState


llm = ChatOpenAI(model="gpt-4o", temperature=0.3)

NEGOTIATION_SYSTEM = """
Você é um negociador de dívidas simpático e empático da empresa FinanceX.
Seu objetivo é fechar um acordo que o cliente consiga pagar.

Regras:
- Seja cordial e compreensivo, nunca pressione agressivamente
- Tente entender a situação financeira do cliente
- Você SOMENTE pode oferecer as opções listadas em "Ofertas desbloqueadas" — não invente parcelas ou descontos diferentes
- Se o cliente não aceitar a oferta atual e ainda houver ofertas não reveladas, use status "countered" — a próxima oferta será apresentada automaticamente na próxima rodada
- Se o cliente aceitar qualquer oferta, marque status como "accepted" e informe o id correto
- Se o cliente rejeitar todas as ofertas disponíveis e não houver mais, use status "rejected"
- Retorne SEMPRE um JSON com os campos abaixo

Formato de resposta obrigatório (JSON puro, sem markdown):
{{
  "reply": "sua mensagem para o cliente (sem mencionar a próxima oferta — ela aparecerá automaticamente)",
  "accepted_offer_id": "id da oferta aceita ou null",
  "status": "accepted | countered | rejected"
}}

Ofertas desbloqueadas até agora: {offers}
Total de ofertas disponíveis: {total_offers}
Rodada atual: {round}
Valor original da dívida: R$ {debt_amount}
"""


async def negotiation_node(state: AgentState) -> dict:
    debt_amount = float(state["customer_data"]["debt_amount"])
    rounds = state["negotiation_rounds"]
    all_offers = state["available_offers"]

    # Desbloqueia ofertas progressivamente: rodada 0 → 1ª oferta, rodada 1 → 2ª, etc.
    unlocked_offers = all_offers[: rounds + 1]

    system = SystemMessage(content=NEGOTIATION_SYSTEM.format(
        offers=json.dumps(unlocked_offers, ensure_ascii=False),
        total_offers=len(all_offers),
        round=rounds + 1,
        debt_amount=debt_amount,
    ))

    # Inclui histórico recente para o LLM ter contexto
    recent_messages = state["messages"][-6:]

    response = await llm.ainvoke([system] + recent_messages)

    try:
        data = json.loads(response.content)
    except json.JSONDecodeError:
        data = {
            "reply": response.content,
            "accepted_offer_id": None,
            "status": "countered",
        }

    # Se o cliente não aceitou e ainda há ofertas para revelar, apresenta a próxima
    next_round = rounds + 1
    has_more_offers = next_round < len(all_offers)

    if data.get("status") in ("countered", "rejected") and has_more_offers:
        next_offer = all_offers[next_round]
        disc = debt_amount * (1 - next_offer["discount_pct"] / 100)
        disc_fmt = f"R$ {disc:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        inst_val = disc / next_offer["installments"]
        inst_fmt = f"R$ {inst_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
    if data.get("status") == "accepted" and not selected_offer:
        selected_offer = unlocked_offers[-1]

    return {
        "messages": [reply],
        "selected_offer": selected_offer,
        "negotiation_rounds": next_round,
        "negotiation_status": data.get("status", "countered"),
        "current_node": "negotiation",
    }
