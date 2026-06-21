"""
app/agent/tools/offer_tools.py

Carrega e ranqueia ofertas do arquivo JSON local.
Em produção: substituir por chamada a API externa.
"""

import json
from functools import lru_cache
from app.settings import settings


@lru_cache(maxsize=1)
def _load_all_offers() -> list[dict]:
    """Carrega e faz cache das ofertas do arquivo JSON."""
    with open(settings.offers_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["offers"]


def _rank_offers(offers: list[dict], debt_amount: float, overdue_days: int) -> list[dict]:
    """
    Ranqueia as ofertas conforme o perfil financeiro do cliente.

    Lógica:
    - Dívida alta (> R$ 5.000) ou muito tempo em atraso (> 90 dias) → cliente provavelmente
      não consegue quitar à vista; começa com parcelamento (ordem: mais parcelas primeiro).
    - Dívida baixa e atraso curto → cliente tem mais chances de quitar à vista;
      começa com o maior desconto como gancho de negociação.
    """
    HIGH_DEBT = 5_000.0
    HIGH_OVERDUE = 90

    if debt_amount > HIGH_DEBT or overdue_days > HIGH_OVERDUE:
        # Prioriza parcelas: mais parcelas = menor prestação = mais acessível
        return sorted(offers, key=lambda o: o["installments"], reverse=True)
    else:
        # Prioriza desconto: maior abatimento = gancho mais forte para fechar rápido
        return sorted(offers, key=lambda o: o["discount_pct"], reverse=True)


async def load_offers_for_debt(debt_amount: float, overdue_days: int = 0) -> list[dict]:
    """
    Retorna as ofertas ranqueadas para o perfil do cliente.
    """
    offers = list(_load_all_offers())
    return _rank_offers(offers, debt_amount, overdue_days)
