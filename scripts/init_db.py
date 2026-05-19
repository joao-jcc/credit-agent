"""
scripts/init_db.py

Cria as tabelas e popula o banco com dados fake.
Alternativa ao docker-entrypoint para quem roda sem Docker.

Uso:
    python scripts/init_db.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.db.connection import engine
from app.db.models import Base


SEED_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "seed.sql")


async def init():
    # Cria as tabelas via ORM
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Tabelas criadas")

    # Roda o seed com dados fake
    with open(SEED_FILE, "r") as f:
        seed_sql = f.read()

    async with engine.begin() as conn:
        for statement in seed_sql.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("--"):
                await conn.execute(text(stmt))
        print("✅ Dados fake inseridos")

    print("🎉 Banco pronto")


if __name__ == "__main__":
    asyncio.run(init())
