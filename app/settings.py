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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
