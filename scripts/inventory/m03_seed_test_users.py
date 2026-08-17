#!/usr/bin/env python3
# Seed de usuários QA — reconstruído após reset do sandbox (16/08/2026).
# Mesmos emails/roles/senha do fluxo original M03 (padrão EJC_QA).
import asyncio, os, uuid, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from sqlalchemy import text

# Carrega env via loader
import subprocess, pathlib
env = dict(os.environ)
envfile = pathlib.Path(__file__).resolve().parents[2] / ".env"
if envfile.exists():
    for line in envfile.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"'))

from sqlalchemy.ext.asyncio import create_async_engine
DATABASE_URL = env.get("DATABASE_URL", "postgresql+asyncpg://ejc:ejc@localhost/ejc")
engine = create_async_engine(DATABASE_URL)

USERS = [
    ("admin", "ejc_qa_auth_admin@golocal.ejc"),
    ("socio", "ejc_qa_auth_socio@golocal.ejc"),
    ("advogado", "ejc_qa_auth_advogado@golocal.ejc"),
    ("estagiario", "ejc_qa_auth_estagiario@golocal.ejc"),
    ("financeiro", "ejc_qa_auth_financeiro@golocal.ejc"),
    ("secretaria", "ejc_qa_auth_secretaria@golocal.ejc"),
    ("cliente_externo", "ejc_qa_auth_cliente@golocal.ejc"),
]
PWD = "EjcQa2026!SenhaForte"
NOME = {r: f"EJC QA {r.capitalize()}" for r, _ in USERS}
EMAILS = {r: e for r, e in USERS}


async def main():
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    from sqlalchemy import text as t
    async with engine.begin() as conn:
        # inspeciona colunas de users
        cols = {
            row[0]
            for row in (await conn.execute(t(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users'"))).fetchall()
        }
        pwd_hash = ctx.hash(PWD)
        advogado_uuid = "4701ecbf-cf9b-422f-b75a-b906814b8213"
        for role, email in USERS:
            exists = (await conn.execute(
                t("SELECT id FROM users WHERE email = :e"), {"e": email})).fetchone()
            if exists:
                print(f"existe: {email} ({exists[0]})")
                continue
            uid = (uuid.UUID(advogado_uuid) if role == "advogado"
                   else f"U-{uuid.uuid4().hex[:8]}")
            fields = ["id", "email", "role", "must_change_password"]
            vals = {
                "id": str(uid),
                "email": email,
                "role": role,
                "must_change_password": False,
            }
            if "full_name" in cols:
                fields.append("full_name")
                vals["full_name"] = NOME[role]
            if "hashed_password" in cols:
                fields.append("hashed_password")
                vals["hashed_password"] = pwd_hash
            if "is_active" in cols:
                fields.append("is_active")
                vals["is_active"] = True
            cols_sql = ", ".join(fields)
            params = {f"p_{k}": v for k, v in vals.items()}
            ins = f"INSERT INTO users ({cols_sql}) VALUES (" + \
                ", ".join(f":p_{k}" for k in vals) + ")"
            await conn.execute(t(ins), params)
            print(f"criado: {role} {email} -> {uid}")
    await engine.dispose()


asyncio.run(main())
