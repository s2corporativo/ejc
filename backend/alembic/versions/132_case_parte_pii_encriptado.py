"""132 — Cifra o CPF/CNPJ das PARTES processuais (case_partes) em repouso.

P1-5 da auditoria integral (docs/auditoria-ejc/12-seguranca-lgpd.md).

O cutover C6/LGPD (migrations 061 → 112) removeu o documento em texto puro de
`clients`, mas parou ali. `case_partes.cpf_cnpj` — que guarda o CPF/CNPJ do
autor, do réu, do terceiro e do procurador de cada caso — permaneceu em TEXTO
PURO. Era o furo mais largo dos dois: a mesma pessoa costuma estar nas duas
tabelas (o titular figura como parte do próprio caso, via `client_id`), de modo
que o documento apagado de `clients` seguia legível em `case_partes` — e ali
estão também os documentos de quem NÃO é cliente e nunca contratou o escritório.

Esta migration faz o cutover inteiro num passo só (a tabela nunca teve
dual-write, então não há fase intermediária a preservar):

1. ADD das colunas do padrão Bloco 6a — `cpf_cnpj_enc` (Fernet), `cpf_cnpj_hash`
   (HMAC-SHA256, índice cego) e `cpf_cnpj_mascarado` (exibição).
2. BACKFILL em lotes com paginação por KEYSET (o mesmo desenho da 112: OFFSET
   pularia linhas conforme o predicado encolhe, e uma linha só-lixo repetiria
   para sempre).
3. DROP da coluna em texto puro.

O índice `ix_case_partes_cpf_cnpj_hash` NÃO é único, ao contrário do
`ux_clients_cpf_hash`: a mesma pessoa é parte legitimamente em vários casos, e
até em vários papéis no mesmo caso. Ele existe para a busca exata (`search.py`)
e para a checagem de conflito de interesses (`clients.py`), que passam a
consultar o hash em vez de normalizar texto puro em SQL — mais barato e sem
expor o valor.

`downgrade()` recria a coluna VAZIA e devolve o schema da revisão anterior. O texto puro
NÃO é reconstruído: é exatamente o que se quer eliminar, e o dado segue íntegro
e decifrável em `cpf_cnpj_enc`. Reverter esta migration não perde documento —
perde só a capacidade de lê-lo por SQL cru, que é o objetivo.

Escrita À MÃO (não autogenerate): `case_partes` é uma das tabelas que o EJC
criou em SQL bruto e o `include_name()` de `alembic/env.py` protege.

Revision ID: 132_case_parte_pii_encriptado
Revises: 131_audit_logs_worm
Create Date: 2026-08-03

Renumerada de 127 para 132 em 2026-08-05 (após 131_audit_logs_worm mergear em main).
Nasceu encadeada na 126; enquanto o PR aguardava revisão, a `main` mesclou a
`127_publicacao_explicita` (que tomou o número) e a `130_ejc_skills_uso`. Mantida
na 126, teria criado uma SEGUNDA head. Repontada para 131_audit_logs_worm; o DDL
não mudou.
"""
from alembic import op
import sqlalchemy as sa


revision = "132_case_parte_pii_encriptado"
down_revision = "131_audit_logs_worm"
branch_labels = None
depends_on = None


_LOTE = 500


def _backfill_enc_hash() -> None:
    """Cifra, hasheia e mascara `cpf_cnpj` antes do DROP.

    Idempotente (só toca em quem tem `cpf_cnpj_enc` NULL) e por keyset, para não
    carregar a tabela inteira em memória nem pular linha. Documento só-lixo
    (sem dígitos) vira None e não é cifrado — não há nada de útil a preservar,
    e o valor sujo some no drop.
    """
    from app.services.pii_crypto import (
        encrypt,
        hash_documento,
        mascarar_documento,
        normalizar_documento,
    )

    conn = op.get_bind()
    # Se `cpf_cnpj` já não existe, o cutover terminou — reexecutar o upgrade
    # (retomada após falha no meio, replay manual) não pode estourar em
    # UndefinedColumn. É a mesma tolerância dos `IF NOT EXISTS`/`IF EXISTS` que
    # cercam o resto desta migration.
    tem_texto_puro = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'case_partes' AND column_name = 'cpf_cnpj'"
    )).first()
    if not tem_texto_puro:
        return

    sel = sa.text(
        "SELECT id, cpf_cnpj FROM case_partes "
        "WHERE id > :last AND cpf_cnpj IS NOT NULL AND cpf_cnpj_enc IS NULL "
        "ORDER BY id LIMIT :lim"
    )
    upd = sa.text(
        "UPDATE case_partes SET cpf_cnpj_enc = :enc, cpf_cnpj_hash = :hash, "
        "cpf_cnpj_mascarado = :masc WHERE id = :id"
    )

    last_id = ""  # varchar: '' precede todo id (comparação PG válida)
    while True:
        linhas = conn.execute(sel, {"last": last_id, "lim": _LOTE}).fetchall()
        if not linhas:
            break
        for pid, doc in linhas:
            norm = normalizar_documento(doc)
            conn.execute(
                upd,
                {
                    "id": pid,
                    "enc": encrypt(norm) if norm else None,
                    "hash": hash_documento(norm) if norm else None,
                    # A máscara é None para comprimento inesperado (política de
                    # mascarar_documento): não se devolve "parte" de um
                    # documento sujo sem saber quanto se está vazando.
                    "masc": mascarar_documento(norm) if norm else None,
                },
            )
            last_id = pid


def upgrade() -> None:
    # 1. Colunas do padrão Bloco 6a.
    op.execute("ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS cpf_cnpj_enc text")
    op.execute(
        "ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS cpf_cnpj_hash varchar(64)"
    )
    op.execute(
        "ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS cpf_cnpj_mascarado varchar(32)"
    )
    # Índice CEGO, não único — a mesma pessoa é parte em vários casos.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_case_partes_cpf_cnpj_hash "
        "ON case_partes (cpf_cnpj_hash)"
    )

    # 2. Backfill defensivo ANTES do drop (nenhum documento é perdido).
    _backfill_enc_hash()

    # 3. Texto puro sai. A partir daqui o documento da parte só existe cifrado.
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj")


def _restaurar_texto_puro() -> None:
    """Decifra `cpf_cnpj_enc` de volta para `cpf_cnpj` antes do DROP.

    Sem isto o downgrade DESTRUIRIA todo documento de parte: o texto puro já não
    existe e o ciphertext sai junto com a coluna. Achado de review do PR #652 —
    a versão anterior dizia que "o dado segue decifrável em cpf_cnpj_enc" e
    então dropava exatamente essa coluna.

    Reverter uma migration tem de devolver o estado ANTERIOR, e o estado
    anterior à 127 é o documento em claro em `cpf_cnpj`. Quem reverte assume
    conscientemente esse retrocesso de privacidade — não uma perda silenciosa
    de dado. Mesma paginação por keyset do backfill de ida.

    Linha cujo `cpf_cnpj_enc` não decifra (chave rotacionada, ciphertext
    corrompido) fica com `cpf_cnpj` NULL e é CONTADA no log: o downgrade não
    para por causa dela, mas também não some com ela em silêncio.
    """
    from app.services.pii_crypto import decrypt

    conn = op.get_bind()
    sel = sa.text(
        "SELECT id, cpf_cnpj_enc FROM case_partes "
        "WHERE id > :last AND cpf_cnpj_enc IS NOT NULL AND cpf_cnpj IS NULL "
        "ORDER BY id LIMIT :lim"
    )
    upd = sa.text("UPDATE case_partes SET cpf_cnpj = :doc WHERE id = :id")

    last_id, indecifraveis = "", 0
    while True:
        linhas = conn.execute(sel, {"last": last_id, "lim": _LOTE}).fetchall()
        if not linhas:
            break
        for pid, enc in linhas:
            try:
                doc = decrypt(enc)
            except ValueError:
                doc, indecifraveis = None, indecifraveis + 1
            if doc:
                conn.execute(upd, {"id": pid, "doc": doc[:18]})
            last_id = pid
    if indecifraveis:
        print(
            f"[132 downgrade] {indecifraveis} linha(s) com cpf_cnpj_enc "
            "indecifrável — documento NÃO restaurado nessas linhas."
        )


def downgrade() -> None:
    # Restaura o schema da revisão anterior — e o DADO junto com ele.
    op.execute("ALTER TABLE case_partes ADD COLUMN IF NOT EXISTS cpf_cnpj varchar(18)")
    _restaurar_texto_puro()
    op.execute("DROP INDEX IF EXISTS ix_case_partes_cpf_cnpj_hash")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj_mascarado")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj_hash")
    op.execute("ALTER TABLE case_partes DROP COLUMN IF EXISTS cpf_cnpj_enc")
