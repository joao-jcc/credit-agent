"""
app/settings.py

Todas as configurações do projeto lidas do .env via pydantic-settings.
Importe `settings` de qualquer lugar — nunca use os.getenv() diretamente.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/negotiation_db"
    offers_file_path: str = "data/offers.json"
    max_negotiation_rounds: int = 3

    # ── Identidade do agente (usada nos prompts) ──────────────────────────────
    agent_name: str = "Seven"
    company_name: str = "FinanceX"
    fallback_contact: str = "0800-XXX-XXXX"
    product_name: str = "cartão de crédito"
    history_window: int = 8  # nº de mensagens recentes passadas ao LLM como contexto

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
