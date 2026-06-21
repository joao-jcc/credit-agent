"""
app/agent/nodes/authentication.py

Nó de autenticação: coleta nome e CPF do usuário.

Estratégia:
- Usa um LLM leve para extrair nome/CPF da mensagem do usuário (JSON estruturado).
- Valida o CPF (11 dígitos, dígitos verificadores, sem sequência repetida).
- As mensagens de resposta são compostas via prompts centralizados (TASK_AUTH_*).
"""

import json
import re
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from app.agent.state import AgentState
from app.agent.prompts import (
    compose_reply,
    TASK_AUTH_NEED_CPF,
    TASK_AUTH_WRONG_CPF,
    TASK_AUTH_OK,
)


# LLM dedicado à extração estruturada (temperatura 0 para determinismo)
_extractor_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


EXTRACTION_PROMPT = """
Você é um assistente de extração de dados.
Analise a mensagem do usuário e extraia nome e CPF se presentes.

Retorne APENAS um JSON válido no formato:
{{"nome": "string ou null", "cpf": "apenas dígitos ou null"}}

Exemplos:
- "Meu nome é João Silva, CPF 123.456.789-00" → {{"nome": "João Silva", "cpf": "12345678900"}}
- "João" → {{"nome": "João", "cpf": null}}
- "123.456.789-00" → {{"nome": null, "cpf": "12345678900"}}

Mensagem do usuário: {user_message}
"""


def _first_name(full_name: str) -> str:
    return (full_name or "").strip().split(" ")[0]


def validate_cpf_format(cpf: str) -> bool:
    """
    Valida o CPF usando o algoritmo oficial de dígitos verificadores.
    Rejeita sequências trivialmente inválidas (ex.: 000.000.000-00, 111.111.111-11).
    """
    digits = re.sub(r"\D", "", cpf or "")
    if len(digits) != 11:
        return False
    if len(set(digits)) == 1:
        return False

    def _check(d: str, length: int) -> bool:
        total = sum(int(d[i]) * (length + 1 - i) for i in range(length))
        remainder = (total * 10) % 11
        return remainder == int(d[length])

    return _check(digits, 9) and _check(digits, 10)


async def authentication_node(state: AgentState) -> dict:
    last_user_msg = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        ""
    )

    # Extrai nome e CPF da mensagem usando LLM
    extraction_response = await _extractor_llm.ainvoke(
        EXTRACTION_PROMPT.format(user_message=last_user_msg)
    )

    try:
        extracted = json.loads(extraction_response.content)
    except json.JSONDecodeError:
        extracted = {"nome": None, "cpf": None}

    extracted_name = extracted.get("nome") or state.get("customer_name", "")
    extracted_cpf = extracted.get("cpf") or state.get("cpf", "")

    has_name = bool(extracted_name.strip())
    has_valid_cpf = validate_cpf_format(extracted_cpf)
    first_name = _first_name(extracted_name)

    if has_name and has_valid_cpf:
        reply_text = await compose_reply(
            scenario="Identidade do cliente validada com sucesso.",
            task=TASK_AUTH_OK,
            context={"user_name": first_name},
            messages=state.get("messages"),
            fallback=f"Perfeito, **{first_name}**! Identidade confirmada. "
                     "Deixa eu verificar sua situação no sistema...",
        )
        return {
            "messages": [AIMessage(content=reply_text)],
            "customer_name": extracted_name,
            "cpf": re.sub(r"\D", "", extracted_cpf),
            "authenticated": True,
            "current_node": "authentication",
        }

    elif has_name and not has_valid_cpf:
        # Tem nome; CPF ausente ou inválido
        had_cpf_attempt = bool(re.sub(r"\D", "", extracted_cpf))
        task = TASK_AUTH_WRONG_CPF if had_cpf_attempt else TASK_AUTH_NEED_CPF
        fallback = (
            f"Hmm, **{first_name}**, esse CPF não parece válido. "
            "Pode conferir e enviar novamente (apenas os números)?"
            if had_cpf_attempt else
            f"Obrigado, **{first_name}**! Agora preciso do seu **CPF** "
            "(apenas os números está ótimo)."
        )
        reply_text = await compose_reply(
            scenario="Cliente informou o nome; falta o CPF válido.",
            task=task,
            context={"user_name": first_name},
            messages=state.get("messages"),
            fallback=fallback,
        )
        return {
            "messages": [AIMessage(content=reply_text)],
            "customer_name": extracted_name,
            "authenticated": False,
            "current_node": "authentication",
        }

    else:
        # Falta o nome (e talvez o CPF também)
        reply_text = await compose_reply(
            scenario="Cliente ainda não informou o nome completo.",
            task="Peça gentilmente o nome completo do cliente para continuar. "
                 "Não mencione dívida ou valores.",
            context={},
            messages=state.get("messages"),
            fallback="Para continuar, preciso do seu **nome completo**. Pode me informar?",
        )
        result: dict = {
            "messages": [AIMessage(content=reply_text)],
            "authenticated": False,
            "current_node": "authentication",
        }
        if has_valid_cpf:
            result["cpf"] = re.sub(r"\D", "", extracted_cpf)
        return result
