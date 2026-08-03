"""Marca do momento em que a senha atual foi definida, para invalidar access tokens antigos.

Por que esta coluna existe
──────────────────────────
Trocar a senha já revogava todos os `refresh_tokens` do usuário
(`routers/auth.py:alterar_senha`), mas o ACCESS token em circulação continuava
válido até o seu próprio `exp` — até `ACCESS_TOKEN_EXPIRE_HOURS` depois. O
resultado é que quem troca a senha por suspeita de comprometimento segue
comprometido exatamente durante a janela em que a troca deveria ter efeito: um
token roubado continua abrindo a API por horas, com a senha nova já em vigor.

Não dá para resolver só com revogação de refresh: o access token é auto-contido
e validado por assinatura, sem consulta ao banco. Precisa existir um dado do
lado do servidor contra o qual comparar cada token — é esta coluna.
`get_current_user` recusa access token cujo `iat` seja ANTERIOR a ela.

Por que nullable, sem backfill
──────────────────────────────
`NULL` significa "senha nunca redefinida desde esta migration" e NÃO invalida
nada. Preencher as linhas existentes com `now()` derrubaria todas as sessões
ativas do escritório no momento do deploy, sem que ninguém tivesse trocado
senha alguma — efeito colateral que a correção não pede e que o titular não
autorizou. A proteção passa a valer a partir da próxima troca de cada usuário.

Precisão: gravada truncada ao SEGUNDO na aplicação, porque o `iat` do JWT é
inteiro em segundos. Sem truncar, o token emitido na própria troca teria `iat`
(segundo cheio) menor que a marca (com microssegundos) e nasceria inválido.

Nome da tabela e da coluna aparecem como LITERAIS nas chamadas de
`op.add_column`/`op.drop_column` de propósito: `test_schema_dr_parity` varre o
texto da cadeia de migrations para provar que toda coluna do ORM tem migration
correspondente, e uma chamada montada por variável passaria invisível por essa
trava.

Revision ID: 133_user_password_changed_at
Revises: 132_case_parte_pii_encriptado
Create Date: 2026-08-03

Renumerada de 128 para 133 em 2026-08-05 após PR #652 ser renumerada de 131
para 132. O down_revision foi repontado para 132_case_parte_pii_encriptado.
O DDL não mudou.
"""
from alembic import op
import sqlalchemy as sa

revision = "133_user_password_changed_at"
down_revision = "132_case_parte_pii_encriptado"
branch_labels = None
depends_on = None


def _tem_coluna(conn) -> bool:
    return "password_changed_at" in {
        c["name"] for c in sa.inspect(conn).get_columns("users")
    }


def upgrade() -> None:
    # Guardado por existência: reexecutar o upgrade inteiro não estoura (mesmo
    # desenho das migrations 112/127 do repositório).
    if _tem_coluna(op.get_bind()):
        return
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    if not _tem_coluna(op.get_bind()):
        return
    # Reverter devolve o estado anterior: access token antigo volta a valer até
    # expirar. É regressão de segurança ASSUMIDA, não perda de dado — a coluna
    # só guarda um instante, e nenhum dado do usuário depende dela.
    op.drop_column("users", "password_changed_at")
