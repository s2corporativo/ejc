# ── tests/test_ai_ailog_propagation.py ────────────────────────────────────────
# Auditoria 2026-07-15 (relatório final do Núcleo Único de IA, seção 13, item 1
# do achado de code-review/security-review): `war_room._registrar_auditoria` e
# `sentimento_magistrado.analisar_tendencia` gravavam AILog em um try/except que
# ENGOLIA qualquer falha de gravação (só logava e seguia, devolvendo a resposta
# da IA mesmo sem trilha de auditoria). Isso contraria o invariante já
# documentado em `audit_logger.registrar`/`orchestrator.run`/`ai_guard.
# registrar_ai_log`: erro de log PROPAGA — IA sem trilha de auditoria deve
# falhar, não responder em silêncio.
#
# Estes testes travam: (a) AILog é gravado quando db/user são passados; (b) uma
# falha na gravação agora propaga (não é mais engolida); (c) sem db/user, nada
# muda (comportamento antigo preservado).
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.ai_log import AILog
from app.services.sentimento_magistrado import sentimento_ia
from app.services.war_room import war_room

_USER = SimpleNamespace(id="user-1")


class _FakeDB:
    """Mesma forma usada em test_diplomacia_v3.py — db.add/commit em memória,
    com opção de simular falha de gravação (ex.: conexão perdida)."""

    def __init__(self, falha_no_commit: bool = False):
        self.added: list = []
        self.commits = 0
        self._falha = falha_no_commit

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        if self._falha:
            raise RuntimeError("falha simulada de gravação de AILog")
        self.commits += 1


# ── WarRoom ───────────────────────────────────────────────────────────────────

async def test_war_room_grava_ailog_quando_db_user_fornecidos(monkeypatch):
    async def fake_generate(prompt, modo="principal"):
        return {"ok": True, "texto": "vulnerabilidades encontradas",
                "modelo": "anthropic/claude-x"}
    monkeypatch.setattr(war_room.ai, "generate_com_metadados", fake_generate)

    db = _FakeDB()
    r = await war_room.simular_contestacao(
        "peticao fake", db=db, user=_USER, case_id="caso-1")

    assert r == "vulnerabilidades encontradas"
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    assert logs[0].case_id == "caso-1"
    assert logs[0].user_id == "user-1"
    assert logs[0].modelo == "anthropic/claude-x"
    assert db.commits == 1


async def test_war_room_propaga_falha_de_ailog_em_vez_de_engolir(monkeypatch):
    async def fake_generate(prompt, modo="principal"):
        return {"ok": True, "texto": "resposta gerada", "modelo": "anthropic/claude-x"}
    monkeypatch.setattr(war_room.ai, "generate_com_metadados", fake_generate)

    db = _FakeDB(falha_no_commit=True)
    with pytest.raises(RuntimeError, match="falha simulada"):
        await war_room.simular_contestacao(
            "peticao fake", db=db, user=_USER, case_id="caso-1")


async def test_war_room_sem_db_user_nao_grava_e_nao_propaga(monkeypatch):
    """db/user continuam OPCIONAIS (uso interno sem sessão) — comportamento
    de geração idêntico ao anterior quando o chamador não os fornece."""
    async def fake_generate(prompt, modo="principal"):
        return {"ok": True, "texto": "resposta gerada", "modelo": "anthropic/claude-x"}
    monkeypatch.setattr(war_room.ai, "generate_com_metadados", fake_generate)

    r = await war_room.simular_contestacao("peticao fake")
    assert r == "resposta gerada"


async def test_war_room_replica_blindada_tambem_propaga_falha_de_ailog(monkeypatch):
    async def fake_generate(prompt, modo="secundario"):
        return {"ok": True, "texto": "argumentos de replica", "modelo": "anthropic/claude-x"}
    monkeypatch.setattr(war_room.ai, "generate_com_metadados", fake_generate)

    db = _FakeDB(falha_no_commit=True)
    with pytest.raises(RuntimeError, match="falha simulada"):
        await war_room.preparar_replica_blindada(
            "contestacao fake", "tese fake", db=db, user=_USER, case_id="caso-1")


# ── SentimentoMagistrado ───────────────────────────────────────────────────────

async def test_sentimento_magistrado_grava_ailog_quando_db_user_fornecidos(monkeypatch):
    async def fake_generate(prompt, modo="secundario"):
        return {"ok": True, "texto": "Tendência: Rigorosa", "modelo": "anthropic/claude-x"}
    monkeypatch.setattr(sentimento_ia.ai, "generate_com_metadados", fake_generate)

    db = _FakeDB()
    r = await sentimento_ia.analisar_tendencia(
        ["decisão 1", "decisão 2"], db=db, user=_USER, case_id="caso-2")

    assert r == "Tendência: Rigorosa"
    logs = [o for o in db.added if isinstance(o, AILog)]
    assert len(logs) == 1
    assert logs[0].case_id == "caso-2"
    assert logs[0].user_id == "user-1"
    assert db.commits == 1


async def test_sentimento_magistrado_propaga_falha_de_ailog_em_vez_de_engolir(monkeypatch):
    async def fake_generate(prompt, modo="secundario"):
        return {"ok": True, "texto": "Tendência: Rigorosa", "modelo": "anthropic/claude-x"}
    monkeypatch.setattr(sentimento_ia.ai, "generate_com_metadados", fake_generate)

    db = _FakeDB(falha_no_commit=True)
    with pytest.raises(RuntimeError, match="falha simulada"):
        await sentimento_ia.analisar_tendencia(
            ["decisão 1"], db=db, user=_USER, case_id="caso-2")


async def test_sentimento_magistrado_sem_db_user_nao_grava_e_nao_propaga(monkeypatch):
    async def fake_generate(prompt, modo="secundario"):
        return {"ok": True, "texto": "Tendência: Rigorosa", "modelo": "anthropic/claude-x"}
    monkeypatch.setattr(sentimento_ia.ai, "generate_com_metadados", fake_generate)

    r = await sentimento_ia.analisar_tendencia(["decisão 1"])
    assert r == "Tendência: Rigorosa"
