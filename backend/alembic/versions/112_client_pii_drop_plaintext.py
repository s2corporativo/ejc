"""112 — Cutover C6/LGPD: remove CPF/CNPJ em texto puro da tabela clients.

Fecha o achado ALTO/C6 (LGPD): as colunas cpf_enc/cnpj_enc (Fernet) e
cpf_hash/cnpj_hash (HMAC) existiam desde a migration 061 em DUAL-WRITE, mas as
colunas cpf/cnpj em TEXTO PURO nunca foram removidas — a "criptografia em
repouso" era cosmética (o número seguia em claro no banco e nos índices).

Esta migration conclui o cutover:

1. BACKFILL DEFENSIVO (Python, em lotes) — para linhas legadas com cpf/cnpj
   preenchido mas cpf_enc/cnpj_enc NULL (ex.: cadastros anteriores ao dual-write
   sem backfill manual), cifra + hasheia ANTES de dropar. Torna a migration
   atômica: nenhum documento é perdido no drop. Usa app.services.pii_crypto com
   as chaves PII do ambiente (obrigatórias no boot de produção).

2. DROP dos índices sobre o texto puro (ix_clients_cpf, ix_clients_cnpj,
   uq_clients_cpf_active, uq_clients_cnpj_active) e das colunas clients.cpf /
   clients.cnpj. A unicidade/dedup passa a ser garantida SOMENTE pelos índices
   cegos ux_clients_cpf_hash / ux_clients_cnpj_hash (migrations 061/079).

Downgrade recria as colunas (VAZIAS) e os índices para reversibilidade de
schema — o texto puro NÃO é reconstruído (é justamente o que se quer eliminar);
os dados seguem preservados/decifráveis em cpf_enc/cnpj_enc.

Escrita À MÃO (não autogenerate): ~30 tabelas do EJC só existem em SQL bruto,
então nunca se confia no autogenerate cego para o schema completo (CLAUDE.md).

Revision ID: 112_client_pii_drop_plaintext
Revises: 111_ai_provider_metrics
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = "112_client_pii_drop_plaintext"
down_revision = "111_ai_provider_metrics"
branch_labels = None
depends_on = None


_LOTE = 500


def _backfill_enc_hash() -> None:
    """Cifra + hasheia linhas legadas (cpf/cnpj em texto puro sem cpf_enc/
    cnpj_enc) antes do drop. Em lotes, para não carregar a tabela inteira em
    memória. Idempotente: só toca em quem tem enc NULL."""
    from app.services.pii_crypto import (
        normalizar_documento,
        encrypt,
        hash_documento,
    )

    conn = op.get_bind()
    # Paginação por KEYSET (id > :last), NÃO por OFFSET: as linhas atualizadas
    # saem do predicado (enc deixa de ser NULL), então um OFFSET crescente
    # PULARIA linhas conforme o result set encolhe — e um documento só-lixo (sem
    # dígitos → enc continua NULL) faria um SELECT sem offset repetir a mesma
    # linha para sempre. Keyset avança por id: cada linha é vista exatamente uma
    # vez, sem pular (evita perder CPF/CNPJ no drop) e sem loop infinito.
    sel = sa.text(
        "SELECT id, cpf, cnpj FROM clients "
        "WHERE id > :last "
        "  AND ((cpf IS NOT NULL AND cpf_enc IS NULL) "
        "    OR (cnpj IS NOT NULL AND cnpj_enc IS NULL)) "
        "ORDER BY id LIMIT :lim"
    )
    upd = sa.text(
        "UPDATE clients SET cpf_enc = :cpf_enc, cpf_hash = :cpf_hash, "
        "cnpj_enc = :cnpj_enc, cnpj_hash = :cnpj_hash WHERE id = :id"
    )

    last_id = ""  # varchar: '' precede todo id uuid (comparação PG válida)
    while True:
        linhas = conn.execute(sel, {"last": last_id, "lim": _LOTE}).fetchall()
        if not linhas:
            break
        for linha in linhas:
            cid, cpf, cnpj = linha[0], linha[1], linha[2]
            cpf_norm = normalizar_documento(cpf)
            cnpj_norm = normalizar_documento(cnpj)
            conn.execute(
                upd,
                {
                    "id": cid,
                    # Só grava o lado que existe; o outro fica NULL (mantém
                    # coerência PF/PJ). Documento só-lixo vira None e não é
                    # cifrado — some no drop (nada de útil a preservar).
                    "cpf_enc": encrypt(cpf_norm) if cpf_norm else None,
                    "cpf_hash": hash_documento(cpf_norm) if cpf_norm else None,
                    "cnpj_enc": encrypt(cnpj_norm) if cnpj_norm else None,
                    "cnpj_hash": hash_documento(cnpj_norm) if cnpj_norm else None,
                },
            )
            last_id = cid


def upgrade() -> None:
    # 1. Backfill defensivo dos legados (cifra/hasheia antes de dropar).
    _backfill_enc_hash()

    # 2. Índices sobre o texto puro → DROP (idempotente).
    op.execute("DROP INDEX IF EXISTS uq_clients_cpf_active")
    op.execute("DROP INDEX IF EXISTS uq_clients_cnpj_active")
    op.execute("DROP INDEX IF EXISTS ix_clients_cpf")
    op.execute("DROP INDEX IF EXISTS ix_clients_cnpj")

    # 3. Colunas em texto puro → DROP. A partir daqui CPF/CNPJ só existem
    #    cifrados (cpf_enc/cnpj_enc) e hasheados (cpf_hash/cnpj_hash).
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS cpf")
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS cnpj")


def downgrade() -> None:
    # Recria as colunas VAZIAS (o texto puro NÃO é reconstruído — os dados
    # seguem em cpf_enc/cnpj_enc). Restaura o schema/índices da head 111.
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cpf varchar(14)")
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS cnpj varchar(18)")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clients_cpf ON clients (cpf)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_clients_cnpj ON clients (cnpj)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_cpf_active "
        "ON clients (cpf) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_cnpj_active "
        "ON clients (cnpj) WHERE deleted_at IS NULL"
    )
