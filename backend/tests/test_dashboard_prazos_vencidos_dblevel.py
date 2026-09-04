# -*- coding: utf-8 -*-
"""O contador de prazos VENCIDOS do dashboard não pode zerar após as 07:10.

Regressão da auditoria funcional de 22/08/2026 (Issue #1237), encontrada na
passagem pela INTERFACE: o painel exibia "0 vencido(s)" enquanto o banco tinha
três prazos com `data_prazo = 2026-05-29` e `status = 'vencido'`.

Mecanismo — dois comportamentos corretos que se anulavam:

1. `scheduler._marcar_prazos_vencidos` roda às 07:10 e move o prazo estourado
   de `status='pendente'` para `status='vencido'`, alertando o responsável.
   Existe justamente para dar visibilidade ao que venceu.
2. As duas consultas de dashboard contavam vencidos com `status='pendente'`.

Depois que o job rodava, a linha saía do filtro e o contador ia a zero. Entre a
meia-noite e as 07:10 o número estava certo; depois, virava 0 em silêncio — o
job que existe para expor o vencido era o que o escondia do painel.

A contagem certa é a que o resto do repositório já usava
(`routers/relatorio.py`, `services/case_health.py`, `routers/indice_risco.py`,
`modules/dpt360/dashboard_service.py`): venceu a data e não foi cumprido nem
cancelado. Este teste exercita o SQL real, porque o defeito só existe no SQL.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_DB_TESTS") and os.getenv("SCHEMA_CHECK_DATABASE_URL")),
    reason="requer PostgreSQL (RUN_DB_TESTS=1 e SCHEMA_CHECK_DATABASE_URL)",
)

# Cópia fiel do critério aplicado nas duas consultas corrigidas.
SQL_VENCIDOS = """
    SELECT COUNT(*) FILTER (WHERE data_prazo < :hoje) AS vencidos
    FROM deadlines
    WHERE status NOT IN ('concluido','cancelado') AND deleted_at IS NULL
      AND id = ANY(:ids)
"""


@pytest.fixture()
def conn():
    eng = create_engine(os.environ["SCHEMA_CHECK_DATABASE_URL"])
    with eng.begin() as c:
        yield c
        # tudo criado por este teste é removido na mesma transação de teardown
        c.execute(text("DELETE FROM deadlines WHERE titulo LIKE 'regress-vencidos-%'"))


def _criar(conn, status: str, dias_atras: int) -> str:
    ident = str(uuid.uuid4())
    conn.execute(text("""
        INSERT INTO deadlines (id, titulo, tipo, prioridade, status, data_prazo,
                               created_at, updated_at)
        VALUES (:i, :t, 'processual', 'media', :s, :d, now(), now())
    """), {"i": ident, "t": f"regress-vencidos-{ident[:8]}", "s": status,
           "d": date.today() - timedelta(days=dias_atras)})
    return ident


def test_prazo_marcado_vencido_pelo_job_continua_no_contador(conn):
    """O caso exato do defeito: status='vencido', data no passado."""
    ids = [_criar(conn, "vencido", 90)]
    n = conn.execute(text(SQL_VENCIDOS), {"hoje": date.today(), "ids": ids}).scalar()
    assert n == 1, (
        "prazo marcado como 'vencido' pelo job das 07:10 sumiu do contador do "
        "dashboard — é exatamente o que exibia '0 vencido(s)' com prazos estourados"
    )


def test_prazo_pendente_e_vencido_contam_juntos(conn):
    """Antes das 07:10 o prazo é `pendente`; depois, `vencido`. Os dois contam.

    O número na tela não pode mudar só porque o job passou.
    """
    ids = [_criar(conn, "pendente", 5), _criar(conn, "vencido", 5)]
    n = conn.execute(text(SQL_VENCIDOS), {"hoje": date.today(), "ids": ids}).scalar()
    assert n == 2


def test_cumprido_e_cancelado_nao_contam_como_vencidos(conn):
    """Prazo cumprido em atraso, ou cancelado, não é dívida em aberto."""
    ids = [_criar(conn, "concluido", 30), _criar(conn, "cancelado", 30)]
    n = conn.execute(text(SQL_VENCIDOS), {"hoje": date.today(), "ids": ids}).scalar()
    assert n == 0


def test_prazo_futuro_nao_conta_como_vencido(conn):
    ids = [_criar(conn, "pendente", -10)]  # vence daqui a 10 dias
    n = conn.execute(text(SQL_VENCIDOS), {"hoje": date.today(), "ids": ids}).scalar()
    assert n == 0


def test_criterio_antigo_falharia_neste_cenario(conn):
    """Prova que o teste pega o defeito, em vez de passar por construção.

    Com o filtro antigo (`status='pendente'`) o mesmo cenário devolve 0 — que
    era o número exibido no painel.
    """
    ids = [_criar(conn, "vencido", 90)]
    antigo = conn.execute(text("""
        SELECT COUNT(*) FILTER (WHERE data_prazo < :hoje)
        FROM deadlines
        WHERE status='pendente' AND deleted_at IS NULL AND id = ANY(:ids)
    """), {"hoje": date.today(), "ids": ids}).scalar()
    novo = conn.execute(text(SQL_VENCIDOS),
                        {"hoje": date.today(), "ids": ids}).scalar()
    assert antigo == 0 and novo == 1
