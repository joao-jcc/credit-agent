-- data/seed.sql
-- Cria as tabelas e popula com dados fake para desenvolvimento

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tabela de clientes endividados
CREATE TABLE IF NOT EXISTS customers (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         VARCHAR(200) NOT NULL,
    cpf          VARCHAR(11)  NOT NULL UNIQUE,
    debt_amount  DECIMAL(12, 2) NOT NULL,
    overdue_days INTEGER NOT NULL DEFAULT 0,
    email        VARCHAR(200),
    phone        VARCHAR(20),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Tabela de acordos fechados
CREATE TABLE IF NOT EXISTS agreements (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id   UUID NOT NULL REFERENCES customers(id),
    session_id    UUID NOT NULL,
    original_debt DECIMAL(12, 2) NOT NULL,
    agreed_amount DECIMAL(12, 2) NOT NULL,
    installments  INTEGER NOT NULL,
    discount_pct  DECIMAL(5, 2) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Dados fake
INSERT INTO customers (name, cpf, debt_amount, overdue_days, email, phone) VALUES
    ('João Silva',        '12345678900', 5000.00,  90,  'joao@email.com',    '11999990001'),
    ('Maria Souza',       '98765432100', 12500.00, 180, 'maria@email.com',   '11999990002'),
    ('Carlos Oliveira',   '11122233344', 800.00,   30,  'carlos@email.com',  '11999990003'),
    ('Ana Lima',          '55566677788', 32000.00, 365, 'ana@email.com',     '11999990004'),
    ('Pedro Costa',       '99988877766', 2300.50,  60,  'pedro@email.com',   '11999990005')
ON CONFLICT (cpf) DO NOTHING;
