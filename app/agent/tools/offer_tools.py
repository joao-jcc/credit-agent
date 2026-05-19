"""
app/agent/tools/offer_tools.py

Carrega ofertas do arquivo JSON local.
Em produção: substituir por chamada a API externa.
"""

import json
import os
from functools import lru_cache


OFFERS_FILE = os.getenv("OFFERS_FILE_PATH", "data/offers.json")


@lru_cache(maxsize=1)
def _load_all_offers() -> list[dict]:
    """Carrega e faz cache das ofertas do arquivo JSON."""
    with open(OFFERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["offers"]


async def load_offers_for_debt(debt_amount: float) -> list[dict]:
    """
    Retorna as ofertas disponíveis para um determinado valor de dívida.
    Por enquanto retorna todas as ofertas — futuramente pode filtrar por faixa de valor.
    """
    # TODO: filtrar/rankear ofertas com base no valor da dívida e perfil do cliente
    return _load_all_offers()
