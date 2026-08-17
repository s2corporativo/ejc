#!/usr/bin/env python3
"""Manutenção QA do EJC (sandbox). Uso: scripts/inventory/env_shell.sh python3
scripts/inventory/qa_maintenance.py [reset_senhas|limpar_usuarios|status]

Não versionar alterações reais; destina-se exclusivamente ao ambiente de
homologação local (dados EJC_QA_*).
"""
import os
import sys
import asyncio

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
os.chdir("/home/ubuntu/ejc_repo/backend")

from app.core.config import get_settings
settings = get_settings()
from app.core.database import engine
from app.core.security import get_password_hash
from sqlalchemy import text

SENHA_QA = "EjcQa2026!SenhaForte"
EMAILS_QA = [
    "ejc_qa_auth_admin@golocal.ejc",
    "ejc_qa_auth_socio@golocal.ejc",
    "ejc_qa_auth_advogado@golocal.ejc",
    "ejc_qa_auth_estagiario@golocal.ejc",
    "ejc_qa_auth_financeiro@golocal.ejc",
    "ejc_qa_auth_secretaria@golocal.ejc",
    "ejc_qa_auth_cliente@golocal.ejc",
    "ejc_qa_auth_inativo@golocal.ejc",
]


async def run(cmd: str) -> None:
    async with engine.begin() as conn:
        if cmd == "reset_senhas":
            h = get_password_hash(SENHA_QA)
            for e in EMAILS_QA:
                r = await conn.execute(
                    text("UPDATE users SET hashed_password = :h, "
                         "must_change_password = false "
                         "WHERE email = :e"), {"h": h, "e": e})
                print(f"senha resetada: {e} ({r.rowcount})")
        elif cmd == "limpar_usuarios":
            r = await conn.execute(
                text("DELETE FROM refresh_tokens WHERE user_id IN "
                     "(SELECT id FROM users WHERE email LIKE :pat)"),
                {"pat": "%qa_auth%"})
            r2 = await conn.execute(
                text("DELETE FROM users WHERE email LIKE :pat"),
                {"pat": "%qa_auth%"})
            r3 = await conn.execute(
                text("DELETE FROM clients WHERE nome LIKE :pat"),
                {"pat": "EJC_QA%"})
            print(f"refresh_tokens {r.rowcount}, users {r2.rowcount}, "
                  f"clients {r3.rowcount}")
        elif cmd == "status":
            rows = await conn.execute(
                text("SELECT email, role, is_active FROM users "
                     "WHERE email LIKE :pat ORDER BY email"),
                {"pat": "%qa_auth%"})
            for row in rows.fetchall():
                print(row)


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "status"))
