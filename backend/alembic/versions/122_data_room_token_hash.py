"""Data Room: tokens de link públicos passam a ser armazenados como SHA-256.

Auditoria 2026-07-26: o segredo do link ficava em claro em data_room_links.token
(dump de banco/backup expunha acesso público a documentos). O router agora grava
apenas o hash e compara por hash no acesso; esta migration converte os tokens
já persistidos. Irreversível por natureza (hash) — o downgrade é no-op: links
antigos continuam funcionando porque a comparação passa a ser sempre por hash.
"""
from __future__ import annotations

import hashlib
import re

import sqlalchemy as sa
from alembic import op

revision = "122_data_room_token_hash"
down_revision = "121_sala_juridica_chat"
branch_labels = None
depends_on = None

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, token FROM data_room_links")
    ).fetchall()
    for row in rows:
        token = row.token or ""
        # Guarda de idempotência: um re-run não pode re-hashear hash já gravado.
        # token_urlsafe(48) contém '-'/'_' e maiúsculas, nunca casa com hex-64.
        if _SHA256_HEX.fullmatch(token):
            continue
        bind.execute(
            sa.text("UPDATE data_room_links SET token = :h WHERE id = :i"),
            {"h": hashlib.sha256(token.encode()).hexdigest(), "i": row.id},
        )


def downgrade() -> None:
    # Hash não é reversível; nada a fazer. Para restaurar o comportamento
    # antigo seria preciso reverter o código E revogar/regerar os links.
    pass
