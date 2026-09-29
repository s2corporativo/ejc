#!/usr/bin/env python3
"""Probe: por que 20/11 não suspende o prazo mesmo no conjunto?"""
import asyncio
import datetime as dt
import os
import sys

os.environ.setdefault("PYTHONPATH", "/home/ubuntu/ejc_repo/backend")
sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")

from sqlalchemy import text

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://ejc:ejc@localhost/ejc")


def db(sql):
    import subprocess
    out = subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A", "-c", sql],
        env={**os.environ, "PGPASSWORD": "ejc"},
        capture_output=True, text=True,
    )
    return out.stdout.strip()


import app.services.deadline_calculator as dc

print("pre:", dc._FERIADOS_DB)
print("type of set members:", [type(x).__name__ for x in dc._FERIADOS_DB][:2] if dc._FERIADOS_DB else "vazio")

db("INSERT INTO feriados (id, data, nome, tipo, movel) VALUES "
   "('ejc-qa-2026-11-20','2026-11-20','EJC_QA sint','municipal',false) ON CONFLICT (id) DO NOTHING")
print("row count:", db("SELECT count(*) FROM feriados WHERE id='ejc-qa-2026-11-20'"))
print("col type:", db("SELECT data_type FROM information_schema.columns WHERE table_name='feriados' AND column_name='data'"))

cnt = asyncio.run(dc.carregar_feriados_db())
print("cnt loaded:", cnt)
print("set após carga:", dc._FERIADOS_DB)
print("20/11 in set:", dt.date(2026, 11, 20) in dc._FERIADOS_DB)

v = dc.prazo_dias_uteis(dt.date(2026, 11, 16), 3)
print("v =", v)

# Teste direto da cadeia: 16/11 +1, +2, +3
for d in [dt.date(2026, 11, 17), dt.date(2026, 11, 18), dt.date(2026, 11, 19), dt.date(2026, 11, 20)]:
    print(d, "eh_dia_util:", dc.eh_dia_util(d), "eh_feriado:", dc.eh_feriado(d))

db("DELETE FROM feriados WHERE id='ejc-qa-2026-11-20'")
