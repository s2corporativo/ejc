#!/usr/bin/env python3
"""Manutenção QA do EJC (sandbox). Uso: scripts/inventory/env_shell.sh python3
scripts/inventory/qa_maintenance.py [reset_senhas|limpar_usuarios|status]

Não versionar alterações reais; destina-se exclusivamente ao ambiente de
homologação local (dados EJC_QA_*).
"""

if __package__:
    from . import _shared
else:  # Execução direta: python scripts/inventory/<script>.py
    import _shared

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

def _qa_pw(name: str) -> str:
    return _shared.qa_password(name)

SENHA_QA = _qa_pw('SENHA_QA')
EMAILS_QA = [
    _shared.qa_email('admin'),
    _shared.qa_email('socio'),
    _shared.qa_email('advogado'),
    _shared.qa_email('estagiario'),
    _shared.qa_email('financeiro'),
    _shared.qa_email('secretaria'),
    _shared.qa_email('cliente'),
    _shared.qa_email('inativo'),
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
