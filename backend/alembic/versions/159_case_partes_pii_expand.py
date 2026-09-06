"""159 — EXPAND: CPF/CNPJ cifrado + índice cego em case_partes (LGPD, DB-03).

Achado DB-03 (P1) da auditoria de camadas de 06/09/2026: `case_partes.cpf_cnpj`
guarda em TEXTO PURO o documento de partes adversas, testemunhas e
procuradores, enquanto `clients.cpf/cnpj` vive cifrado (Fernet) + índice cego
(HMAC) desde as migrations 061/112. Vazamento do banco expõe CPF de terceiros.

Esta migration é o passo EXPAND do mesmo cutover em três tempos que a tabela
`clients` já percorreu (061 → dual-write → 112 drop):

1. (AQUI) cria `cpf_cnpj_enc` (ciphertext Fernet, não indexável) e
   `cpf_cnpj_hash` (HMAC-SHA256 hex, indexado — busca exata/dedup/conflito).
   Nada é dropado; a coluna em claro continua existindo e sendo lida como
   FALLBACK pelo ORM (`CaseParte.cpf_cnpj` é propriedade: lê a cifrada e só
   cai na coluna em claro quando a cifrada é NULL).
2. BACKFILL — fora desta migration, de propósito. A migration 112 fez o
   backfill em Python dentro do `upgrade()`, mas ela é anterior à catraca do
   gate de deploy (`scripts/check_migration_compatibility.py`, ativa a partir
   da 132): o gate reprova qualquer chamada fora de `op.*` e `op.get_bind`
   em `upgrade()`, porque migration que se monta em tempo de execução não é
   conferível estaticamente antes de produção. Fernet não é reproduzível em
   SQL, então o backfill mora em `app/services/case_parte_pii.py`
   (`backfill_case_partes_pii`, idempotente, paginação por keyset) e é
   disparado por `python scripts/backfill_case_partes_pii.py` — o entrypoint
   o chama logo após `alembic upgrade head`. Enquanto o backfill não roda, o
   fallback de leitura garante que nenhuma parte "perde" o documento.
3. CONTRACT (drop da coluna em claro) — migration FUTURA, só depois que os
   routers de SQL cru (`routers/case_partes.py`, `clients.py:333`,
   `search.py:167`) passarem a escrever/buscar por `cpf_cnpj_hash`. Não é
   feito nesta rodada.

`downgrade()` é FUNCIONAL e sem perda: antes de dropar as colunas, decifra
`cpf_cnpj_enc` de volta para `cpf_cnpj` nas linhas cuja coluna em claro
esteja NULL (as gravadas pelo ORM após esta migration, que só escreve na
cifrada). O gate de deploy não avalia `downgrade()` — por isso o laço em
Python é aceitável aqui e não em `upgrade()`. Usa as mesmas chaves PII do
ambiente que a 112 (`PII_ENCRYPTION_KEY`).

Escrita À MÃO (não autogenerate). Aditiva.
"""
from alembic import op
import sqlalchemy as sa


revision = "159_case_partes_pii_expand"
down_revision = "158_indices_fk_negocio"
branch_labels = None
depends_on = None


_LOTE = 500


def upgrade() -> None:
    op.add_column("case_partes", sa.Column("cpf_cnpj_enc", sa.Text(), nullable=True))
    op.add_column("case_partes", sa.Column("cpf_cnpj_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_case_partes_cpf_cnpj_hash", "case_partes", ["cpf_cnpj_hash"])


def _restaurar_texto_puro_antes_do_drop() -> None:
    """Decifra cpf_cnpj_enc → cpf_cnpj onde a coluna em claro está NULL.

    Keyset por id (não OFFSET): as linhas atualizadas saem do predicado e um
    OFFSET crescente pularia linhas — mesma lição da 112. Linha cujo
    ciphertext não decifra (chave rotacionada) é deixada como está, com aviso:
    o downgrade não pode inventar um documento.
    """
    from app.services.pii_crypto import decrypt

    conn = op.get_bind()
    sel = sa.text(
        "SELECT id, cpf_cnpj_enc FROM case_partes "
        "WHERE id > :last AND cpf_cnpj IS NULL AND cpf_cnpj_enc IS NOT NULL "
        "ORDER BY id LIMIT :lim"
    )
    upd = sa.text("UPDATE case_partes SET cpf_cnpj = :doc WHERE id = :id")

    last_id = ""
    while True:
        linhas = conn.execute(sel, {"last": last_id, "lim": _LOTE}).fetchall()
        if not linhas:
            break
        for pid, enc in linhas:
            try:
                doc = decrypt(enc)
            except ValueError:
                print(f"[159 downgrade] parte {pid}: ciphertext indecifrável — mantida sem texto puro")
                doc = None
            if doc:
                conn.execute(upd, {"doc": doc[:18], "id": pid})
            last_id = pid


def downgrade() -> None:
    _restaurar_texto_puro_antes_do_drop()
    op.drop_index("ix_case_partes_cpf_cnpj_hash", table_name="case_partes")
    op.drop_column("case_partes", "cpf_cnpj_hash")
    op.drop_column("case_partes", "cpf_cnpj_enc")
