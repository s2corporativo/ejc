from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.deadline import Deadline


def test_novo_prazo_critico_ignora_confirmacao_do_caller_legado():
    prazo = Deadline(
        id="critico-1",
        titulo="Prazo crítico",
        tipo="processual",
        prioridade="critica",
        data_prazo=date(2026, 9, 22),
        confirmado=True,
        conferido_por="mesmo-usuario",
        conferido_em=datetime.now(timezone.utc),
    )
    assert prazo.confirmado is False
    assert prazo.conferido_por is None
    assert prazo.conferido_em is None


def test_novo_prazo_nao_critico_preserva_confirmacao_explicita():
    prazo = Deadline(
        id="alto-1",
        titulo="Prazo alto",
        tipo="processual",
        prioridade="alta",
        data_prazo=date(2026, 9, 22),
        confirmado=True,
    )
    assert prazo.confirmado is True
