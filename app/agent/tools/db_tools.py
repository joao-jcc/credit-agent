"""
app/agent/tools/db_tools.py

Funções de acesso ao PostgreSQL via SQLAlchemy async.
Em produção, parte dessas funções pode virar chamadas a APIs externas.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.connection import get_session


async def get_customer_by_cpf(cpf: str) -> dict | None:
    """
    Busca cliente e sua dívida pelo CPF.
    Retorna dict com dados do cliente ou None se não encontrado.
    """
    async with get_session() as session:
        result = await session.execute(
            text("""
                SELECT id, name, cpf, debt_amount, overdue_days
                FROM customers
                WHERE cpf = :cpf
                LIMIT 1
            """),
            {"cpf": cpf}
        )
        row = result.mappings().first()
        return dict(row) if row else None


async def save_agreement(data: dict) -> None:
    """
    Salva o acordo fechado na tabela agreements.
    """
    async with get_session() as session:
        await session.execute(
            text("""
                INSERT INTO agreements
                    (id, customer_id, session_id, original_debt, agreed_amount,
                     installments, discount_pct, created_at)
                VALUES
                    (:id, :customer_id, :session_id, :original_debt, :agreed_amount,
                     :installments, :discount_pct, NOW())
            """),
            data
        )
        await session.commit()
