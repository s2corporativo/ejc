# ── tests/test_scheduler_auditoria.py ────────────────────────────────────────
# P1 (2026-07-05) — Sentinela → sino: o job semanal _auditoria_processos passou
# a criar notificações internas via _notificar_auditoria, com IDEMPOTÊNCIA por
# janela (user_id + tipo="auditoria" + link, JANELA_REAUDITORIA_DIAS).
# Testes unitários sem Postgres: sessão fake (padrão dos vizinhos).
from types import SimpleNamespace

from app.models.notification import Notification
from app.services.scheduler import (
    JANELA_REAUDITORIA_DIAS,
    _notificar_auditoria,
)


class _FakeResult:
    def __init__(self, valor):
        self._valor = valor

    def scalar_one_or_none(self):
        return self._valor


class _FakeDB:
    """Sessão mínima: SELECT de dedupe devolve `existente`; add/commit gravam."""

    def __init__(self, existente=None):
        self.existente = existente
        self.added: list = []
        self.commits = 0
        self.queries: list = []

    async def execute(self, stmt, *a, **k):
        self.queries.append(stmt)
        return _FakeResult(self.existente)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


async def test_notificar_auditoria_cria_notificacao_no_sino():
    db = _FakeDB(existente=None)
    criou = await _notificar_auditoria(
        db, "user-1", "🕵️ Sentinela: caso parado",
        "Caso X sem movimentação há 30+ dias", link="/casos/abc",
    )
    assert criou is True
    assert len(db.added) == 1
    n = db.added[0]
    assert isinstance(n, Notification)
    assert n.user_id == "user-1"
    assert n.tipo == "auditoria"
    assert n.link == "/casos/abc"
    assert "30+" in n.mensagem
    assert db.commits == 1  # criar_notificacao_interna commita


async def test_notificar_auditoria_suprime_duplicata_na_janela():
    # Já existe notificação (mesmo user+tipo+link) dentro da janela → não repete
    db = _FakeDB(existente="notif-antiga-id")
    criou = await _notificar_auditoria(
        db, "user-1", "🕵️ Sentinela: caso parado", "msg", link="/casos/abc",
    )
    assert criou is False
    assert db.added == []
    assert db.commits == 0


def test_janela_maior_que_intervalo_semanal():
    # O job roda a cada 7 dias; janela DEVE ser > 7 para não colidir com o
    # horário exato da execução anterior (jitter de segundos re-notificaria).
    assert JANELA_REAUDITORIA_DIAS > 7


async def test_dedupe_consulta_filtra_user_tipo_link_e_janela():
    db = _FakeDB(existente=None)
    await _notificar_auditoria(db, "user-2", "t", "m", link="/prazos")
    # A query de dedupe foi executada antes do INSERT
    assert len(db.queries) >= 1
    sql = str(db.queries[0]).lower()
    for coluna in ("user_id", "tipo", "link", "created_at"):
        assert coluna in sql


class _FakeSemResponsavel(SimpleNamespace):
    pass


async def test_notificacao_por_caso_usa_link_unico_por_caso():
    # Links distintos por caso ⇒ dedupe é POR CASO, não global
    db = _FakeDB(existente=None)
    await _notificar_auditoria(db, "u", "t", "m", link="/casos/caso-1")
    await _notificar_auditoria(db, "u", "t", "m", link="/casos/caso-2")
    assert [n.link for n in db.added] == ["/casos/caso-1", "/casos/caso-2"]
