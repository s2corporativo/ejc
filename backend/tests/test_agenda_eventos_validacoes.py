"""Agenda de eventos — validações de schema (B3, sem banco).

O DDL de agenda_eventos (migration 053) define titulo VARCHAR(255) e hora
VARCHAR(10). Sem max_length no Pydantic, um payload maior estourava DataError
no INSERT/UPDATE (500) em vez de 422 claro. Cobre EventoIn e EventoPatch.
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.routers.agenda_eventos import EventoIn, EventoPatch


def test_eventoin_titulo_e_hora_respeitam_limites_do_ddl():
    # No limite: aceito.
    ok = EventoIn(titulo="x" * 255, data_evento=date(2026, 8, 1), hora="0" * 10)
    assert len(ok.titulo) == 255 and len(ok.hora) == 10
    # Acima do VARCHAR: 422 (ValidationError) em vez de DataError 500.
    with pytest.raises(ValidationError):
        EventoIn(titulo="x" * 256, data_evento=date(2026, 8, 1))
    with pytest.raises(ValidationError):
        EventoIn(titulo="ok", data_evento=date(2026, 8, 1), hora="0" * 11)


def test_eventopatch_titulo_e_hora_respeitam_limites_do_ddl():
    ok = EventoPatch(titulo="x" * 255, hora="1" * 10)
    assert len(ok.titulo) == 255 and len(ok.hora) == 10
    with pytest.raises(ValidationError):
        EventoPatch(titulo="x" * 256)
    with pytest.raises(ValidationError):
        EventoPatch(hora="1" * 11)
