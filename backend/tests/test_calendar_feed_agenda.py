"""Fase 1 (plano ERP/agenda/IA, achado A4): o feed ICS inclui `agenda_eventos`.

Antes o feed lia só `deadlines`; audiência ou compromisso lançado pela agenda
não chegava ao calendário do celular.
"""
from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace

from app.routers import calendar_feed


def _evento(**over):
    base = {
        "id": "ev-1",
        "titulo": "Audiência de conciliação",
        "tipo": "audiencia",
        "data_evento": date(2026, 10, 20),
        "hora": "14:30",
        "local": "Fórum de BH, sala 3",
        "descricao": "Levar procuração",
    }
    base.update(over)
    return base


def test_evento_com_hora_vira_evento_com_horario_no_fuso_de_brasilia():
    ics = calendar_feed._vevent_agenda(_evento())
    assert "UID:ejc-agenda-ev-1@depaulateixeira" in ics
    assert "DTSTART;TZID=America/Sao_Paulo:20261020T143000" in ics
    assert "DTEND;TZID=America/Sao_Paulo:20261020T153000" in ics
    assert "LOCATION:Fórum de BH\\, sala 3" in ics
    assert "SUMMARY:⚖️ Audiência de conciliação" in ics
    assert "TRIGGER:-PT2H" in ics


def test_evento_sem_hora_vira_dia_inteiro():
    ics = calendar_feed._vevent_agenda(_evento(hora=None, tipo="reuniao", local=None))
    assert "DTSTART;VALUE=DATE:20261020" in ics
    assert "DTEND" not in ics
    assert "LOCATION" not in ics
    assert "SUMMARY:📅" in ics
    assert "TRIGGER:-P1D" in ics


def test_hora_invalida_cai_para_dia_inteiro_sem_quebrar_o_feed():
    for hora in ("25:00", "manhã", "9:75", ""):
        ics = calendar_feed._vevent_agenda(_evento(hora=hora))
        assert "DTSTART;VALUE=DATE:20261020" in ics


def test_hora_com_h_e_aceita():
    ics = calendar_feed._vevent_agenda(_evento(hora="9h05"))
    assert "DTSTART;TZID=America/Sao_Paulo:20261020T090500" in ics


def test_uid_da_agenda_nao_colide_com_uid_de_prazo():
    prazo = SimpleNamespace(
        id="ev-1",
        tipo=SimpleNamespace(value="audiencia"),
        prioridade=SimpleNamespace(value="media"),
        data_prazo=date(2026, 10, 20),
        titulo="Audiência",
        base_legal=None,
        descricao=None,
    )
    assert "UID:ejc-ev-1@depaulateixeira" in calendar_feed._vevent_prazo(prazo)
    assert "UID:ejc-agenda-ev-1@" in calendar_feed._vevent_agenda(_evento())


def test_prazo_comum_de_prioridade_media_segue_fora_do_feed():
    prazo = SimpleNamespace(
        id="p-1",
        tipo=SimpleNamespace(value="processual"),
        prioridade=SimpleNamespace(value="media"),
        data_prazo=date(2026, 10, 20),
        titulo="Réplica",
        base_legal=None,
        descricao=None,
    )
    assert calendar_feed._vevent_prazo(prazo) is None


def test_vtimezone_declarado_para_o_tzid_usado():
    assert "TZID:America/Sao_Paulo" in calendar_feed._VTIMEZONE_SAO_PAULO
    assert "TZOFFSETTO:-0300" in calendar_feed._VTIMEZONE_SAO_PAULO


def test_consulta_da_agenda_respeita_responsavel_exclusao_e_conclusao():
    fonte = inspect.getsource(calendar_feed.feed_ics)
    assert "FROM agenda_eventos" in fonte
    assert "responsavel_id = :uid" in fonte
    assert "deleted_at IS NULL" in fonte
    assert "concluido = FALSE" in fonte


# ── Revisão de segurança: injeção via CR/controle e campos sem teto ──────────

def _linhas_sem_escape(ics: str) -> list[str]:
    """Linhas físicas do VEVENT (separadas por CRLF), como um cliente as lê."""
    return ics.split("\r\n")


def test_cr_solto_nao_injeta_propriedade_nem_vevent():
    for campo in ("titulo", "local", "descricao"):
        malicioso = "x\rEND:VEVENT\rBEGIN:VEVENT\rURL:http://evil"
        ics = calendar_feed._vevent_agenda(_evento(**{campo: malicioso}))
        assert "\r" not in ics.replace("\r\n", "")
        linhas = _linhas_sem_escape(ics)
        assert linhas.count("BEGIN:VEVENT") == 1
        assert linhas.count("END:VEVENT") == 1
        assert not any(linha.startswith("URL:") for linha in linhas)


def test_crlf_vira_quebra_escapada():
    ics = calendar_feed._vevent_agenda(_evento(descricao="linha 1\r\nlinha 2"))
    assert "DESCRIPTION:linha 1\\nlinha 2\r\n" in ics


def test_caracteres_de_controle_sao_removidos_e_tab_preservado():
    assert calendar_feed._ics_escape("a\x00b\x07c\x1bd\x7fe\tf") == "abcde\tf"


def test_campos_longos_sao_truncados():
    ics = calendar_feed._vevent_agenda(_evento(descricao="a" * 5000, local="b" * 5000))
    assert "a" * calendar_feed._MAX_CAMPO_ICS in ics
    assert "a" * (calendar_feed._MAX_CAMPO_ICS + 1) not in ics
    assert "b" * (calendar_feed._MAX_CAMPO_ICS + 1) not in ics


def test_consulta_da_agenda_tem_teto_de_linhas():
    assert "LIMIT 500" in inspect.getsource(calendar_feed.feed_ics)
