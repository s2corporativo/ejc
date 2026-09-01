from __future__ import annotations

from datetime import date

import pytest

from app.models.deadline import Deadline, _origem_exige_confirmacao_humana


@pytest.mark.parametrize(
    "origem",
    ["datajud", "importacao_ia", "ia_documento", "ia_nova_futura"],
)
def test_origem_automatizada_nasce_nao_confirmada(origem):
    prazo = Deadline(
        id=f"d-{origem}",
        titulo="Prazo de teste",
        data_prazo=date(2026, 9, 10),
        origem=origem,
    )
    assert _origem_exige_confirmacao_humana(origem) is True
    assert prazo.confirmado is False


def test_origem_manual_preserva_default_legado():
    prazo = Deadline(
        id="d-manual",
        titulo="Prazo manual",
        data_prazo=date(2026, 9, 10),
        origem="manual",
    )
    assert _origem_exige_confirmacao_humana("manual") is False
    # Default físico/ORM do campo continua sendo aplicado no flush; a regra
    # central não reclassifica prazo manual como rascunho.
    assert prazo.confirmado is None


def test_valor_explicito_do_chamador_prevalece():
    prazo = Deadline(
        id="d-explicito",
        titulo="Prazo automatizado revisado",
        data_prazo=date(2026, 9, 10),
        origem="ia_documento",
        confirmado=True,
    )
    assert prazo.confirmado is True
