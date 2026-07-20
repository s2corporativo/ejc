"""Fixtures Postgres para testes de saúde agregada."""
from __future__ import annotations

from uuid import uuid4
from sqlalchemy import text


async def portfolio_fixtures(db):
    ids = {name: str(uuid4()) for name in (
        "user_a", "user_b", "client_a", "client_b", "case_a", "case_b"
    )}
    for key in ("user_a", "user_b"):
        await db.execute(text(
            "INSERT INTO users (id,email,hashed_password,full_name,role,is_active) "
            "VALUES (:id,:email,'x',:name,'advogado',true)"
        ), {"id": ids[key], "email": f"portfolio-{ids[key][:8]}@teste.local", "name": key})
    for key in ("client_a", "client_b"):
        await db.execute(text(
            "INSERT INTO clients (id,tipo,nome,email,status) "
            "VALUES (:id,'PF',:name,:email,'ativo')"
        ), {"id": ids[key], "name": key, "email": f"portfolio-client-{ids[key][:8]}@teste.local"})
    await db.execute(text(
        "INSERT INTO cases (id,titulo,area,status,client_id,advogado_responsavel_id,"
        "has_judicial_process,created_at,updated_at) "
        "VALUES (:id,'Caso A','civil','ativo',:client,:user,true,"
        "now()-interval '60 days',now()-interval '60 days')"
    ), {"id": ids["case_a"], "client": ids["client_a"], "user": ids["user_a"]})
    await db.execute(text(
        "INSERT INTO cases (id,titulo,area,status,client_id,advogado_responsavel_id,"
        "has_judicial_process,created_at,updated_at) "
        "VALUES (:id,'Caso B','civil','ativo',:client,:user,true,"
        "now()-interval '10 days',now()-interval '10 days')"
    ), {"id": ids["case_b"], "client": ids["client_b"], "user": ids["user_b"]})
    await db.execute(text(
        "INSERT INTO deadlines (id,titulo,tipo,prioridade,status,data_prazo,case_id,"
        "confirmado,origem,created_at,updated_at) "
        "VALUES (:id,'Prazo A vencido','processual','critica','pendente',"
        "CURRENT_DATE-1,:case_id,true,'manual',"
        "now()-interval '45 days',now()-interval '45 days')"
    ), {"id": str(uuid4()), "case_id": ids["case_a"]})
    await db.commit()
    return ids


async def cleanup_portfolio(db, ids):
    await db.execute(text("DELETE FROM deadlines WHERE case_id IN (:a,:b)"), {"a": ids["case_a"], "b": ids["case_b"]})
    await db.execute(text("DELETE FROM cases WHERE id IN (:a,:b)"), {"a": ids["case_a"], "b": ids["case_b"]})
    await db.execute(text("DELETE FROM clients WHERE id IN (:a,:b)"), {"a": ids["client_a"], "b": ids["client_b"]})
    await db.execute(text("DELETE FROM users WHERE id IN (:a,:b)"), {"a": ids["user_a"], "b": ids["user_b"]})
    await db.commit()
