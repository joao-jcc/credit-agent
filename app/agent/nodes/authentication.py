"""
app/agent/nodes/authentication.py

Nó de autenticação: coleta nome e CPF do usuário.

Estratégia:
- Usa um LLM para extrair nome/CPF da mensagem do usuário de forma natural.
- O LLM retorna JSON estruturado com os campos extraídos.
- Se o CPF tiver 11 dígitos numéricos, consideramos autenticado.
"""

import json
import re
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from app.agent.state import AgentState


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


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


def validate_cpf_format(cpf: str) -> bool:
    """Validação básica: 11 dígitos numéricos. Adicione validação real se necessário."""
    digits = re.sub(r"\D", "", cpf or "")
    return len(digits) == 11


async def authentication_node(state: AgentState) -> dict:
    last_user_msg = next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        ""
    )

    # Extrai nome e CPF da mensagem usando LLM
    extraction_response = await llm.ainvoke(
        EXTRACTION_PROMPT.format(user_message=last_user_msg)
    )

    try:
        extracted = json.loads(extraction_response.content)
    except json.JSONDecodeError:
        extracted = {"nome": None, "cpf": None}

    extracted_name = extracted.get("nome") or state.get("customer_name", "")
    extracted_cpf = extracted.get("cpf") or state.get("cpf", "")

    # Determina o que ainda falta coletar
    has_name = bool(extracted_name.strip())
    has_valid_cpf = validate_cpf_format(extracted_cpf)

    if has_name and has_valid_cpf:
        # Autenticação completa
        reply = AIMessage(content=(
            f"Perfeito, **{extracted_name}**! ✅\n"
            "Encontrei seus dados. Deixa eu verificar sua situação..."
        ))
        return {
            "messages": [reply],
            "customer_name": extracted_name,
            "cpf": re.sub(r"\D", "", extracted_cpf),
            "authenticated": True,
            "current_node": "authentication",
        }

    elif has_name and not has_valid_cpf:
        # Tem nome, falta CPF
        reply = AIMessage(content=(
            f"Obrigado, **{extracted_name}**! Agora preciso do seu **CPF** "
            "(apenas os números está ótimo)."
        ))
        return {
            "messages": [reply],
            "customer_name": extracted_name,
            "authenticated": False,
            "current_node": "authentication",
        }

    else:
        # Falta nome (e talvez CPF também)
        reply = AIMessage(content=(
            "Para continuar, preciso do seu **nome completo**. "
            "Pode me informar?"
        ))
        return {
            "messages": [reply],
            "authenticated": False,
            "current_node": "authentication",
        }
