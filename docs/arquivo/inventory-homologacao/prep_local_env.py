#!/usr/bin/env python3
"""Prepara .env local de teste a partir de .env.example (raiz do repo).

- Gera chaves Fernet reais.
- Aponta DATABASE_URL/DATABASE_URL_SYNC para PostgreSQL local (usuário ejc/ejc).
- Desabilita IA externa (AI_ENABLED=false) para testes determinísticos.
"""
import re
import sys
from pathlib import Path

from cryptography.fernet import Fernet

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / ".env.example"
DST = REPO / ".env"

src = SRC.read_text()

fernet = Fernet.generate_key().decode()
src = re.sub(r"(^[A-Z_]*FERNET[A-Z_]*\s*=).*$", rf"\1 {fernet}", src, flags=re.M | re.I)

src = re.sub(r"^POSTGRES_USER=.*$", "POSTGRES_USER=ejc", src, flags=re.M)
src = re.sub(r"^POSTGRES_PASSWORD=.*$", "POSTGRES_PASSWORD=ejc", src, flags=re.M)
src = re.sub(r"^POSTGRES_DB=.*$", "POSTGRES_DB=ejc", src, flags=re.M)
src = re.sub(
    r"^DATABASE_URL=.*$",
    "DATABASE_URL=postgresql+asyncpg://ejc:ejc@localhost:5432/ejc",
    src,
    flags=re.M,
)
src = re.sub(
    r"^DATABASE_URL_SYNC=.*$",
    "DATABASE_URL_SYNC=postgresql://ejc:ejc@localhost:5432/ejc",
    src,
    flags=re.M,
)
src = re.sub(
    r"^SCHEMA_CHECK_DATABASE_URL=.*$",
    "SCHEMA_CHECK_DATABASE_URL=postgresql://ejc:ejc@localhost:5432/ejc",
    src,
    flags=re.M,
)
src = re.sub(r"^REDIS_URL=.*$", "REDIS_URL=redis://localhost:6379/0", src, flags=re.M)
src = re.sub(r"^APP_ENV=.*$", "APP_ENV=development", src, flags=re.M)
src = re.sub(r"^AI_ENABLED=.*$", "AI_ENABLED=false", src, flags=re.M)
pii = Fernet.generate_key().decode()
src = re.sub(r"^PII_ENCRYPTION_KEY=.*$", f"PII_ENCRYPTION_KEY={pii}", src, flags=re.M)
src = re.sub(r"^VAULT_MASTER_KEYS=.*$", f"VAULT_MASTER_KEYS={pii}", src, flags=re.M)

tail = (
    "\n"
    "# ── Compostos para o app/Alembic (equivalente ao docker-compose.yml) ──\n"
    "DATABASE_URL=postgresql+asyncpg://ejc:ejc@localhost:5432/ejc\n"
    "DATABASE_URL_SYNC=postgresql://ejc:ejc@localhost:5432/ejc\n"
    "SCHEMA_CHECK_DATABASE_URL=postgresql://ejc:ejc@localhost:5432/ejc\n"
)
if "DATABASE_URL=" not in src:
    src += tail

DST.write_text(src)
print("OK: .env local gerado em", DST)
