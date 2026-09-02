from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.deadline import Deadline


def test_materializacao_estilo_djen_critica_nasce_sem_conferencia():
    prazo = Deadline(
        id="djen-critico-1",
        titulo="Prazo DJEN crítico",
        tipo="processual",
        prioridade="critica",
        data_prazo=date(2026, 9, 22),
        data_publicacao=date(2026, 9, 1),
        termo_inicial=date(2026, 9, 2),
        regime_calculo="civel",
        calculo_metadata={"fonte": "djen", "termo_final": "2026-09-22"},
        calculado_por="adv-1",
        conferido_por="adv-1",
        conferido_em=datetime.now(timezone.utc),
        origem="djen",
        confirmado=True,
    )

    assert prazo.confirmado is False
    assert prazo.conferido_por is None
    assert prazo.conferido_em is None
