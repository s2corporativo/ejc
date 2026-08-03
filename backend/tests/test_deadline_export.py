# ── tests/test_deadline_export.py ─────────────────────────────────────────────
# Serialização CSV do export de prazos (_prazos_para_csv) — função pura.
import csv
import io
from datetime import date
from types import SimpleNamespace

from app.routers.deadlines import _prazos_para_csv


def _linhas(texto):
    # Remove o BOM antes de parsear.
    return list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))


def _prazo(**kw):
    base = dict(titulo="Contestacao", tipo="processual", prioridade="alta",
                status="pendente", data_prazo=date(2026, 7, 20),
                data_intimacao=date(2026, 7, 1), base_legal="CPC 335")
    base.update(kw)
    return SimpleNamespace(**base)


def test_csv_tem_bom_e_cabecalho():
    out = _prazos_para_csv([], date(2026, 7, 5))
    assert out.startswith("﻿")  # BOM p/ Excel abrir acentos
    linhas = _linhas(out)
    assert linhas[0][0] == "Titulo"
    assert linhas[0][-1] == "Base legal"
    assert len(linhas) == 1  # só cabeçalho quando não há prazos


def test_csv_serializa_prazo_e_calcula_dias_restantes():
    out = _prazos_para_csv([_prazo()], date(2026, 7, 5))
    linhas = _linhas(out)
    assert len(linhas) == 2
    linha = linhas[1]
    assert linha[0] == "Contestacao"
    assert linha[4] == "2026-07-20"        # data_prazo ISO
    assert linha[5] == "2026-07-01"        # data_intimacao ISO
    assert linha[6] == "15"                # 20/07 - 05/07 = 15 dias


def test_csv_escapa_delimitador_no_titulo():
    # Título com ';' não pode quebrar a coluna — o csv.writer deve aspá-lo.
    out = _prazos_para_csv([_prazo(titulo="Prazo A; parte B")], date(2026, 7, 5))
    linhas = _linhas(out)
    assert linhas[1][0] == "Prazo A; parte B"  # continua uma única célula


def test_csv_tolera_campos_ausentes():
    p = _prazo(data_intimacao=None, base_legal=None, data_prazo=None)
    out = _prazos_para_csv([p], date(2026, 7, 5))
    linha = _linhas(out)[1]
    assert linha[4] == "" and linha[5] == "" and linha[6] == "" and linha[7] == ""


# ── Filtro de status: enum nativo do Postgres, 422 em vez de 500 ──────────────
# `Deadline.status` é ENUM nativo. Comparar a coluna com string fora do enum
# NÃO devolve lista vazia: estoura no banco e vira 500. A interface oferece
# "all" — logo `GET /deadlines?status=all` e o export.csv respondiam 500.

import pytest
from fastapi import HTTPException

from app.models.deadline import DeadlineStatus
from app.routers.deadlines import STATUS_PRAZO_VALIDOS, _validar_status_prazo


def test_status_valido_vira_enum():
    """String do enum sobe para o enum — é ele que vai ao banco, não a string."""
    for valor in STATUS_PRAZO_VALIDOS:
        assert _validar_status_prazo(valor) is DeadlineStatus(valor)


@pytest.mark.parametrize("valor", ["all", "ativo", "concluída", "PENDENTE", "'; DROP"])
def test_status_fora_do_enum_vira_422_e_nao_chega_ao_banco(valor):
    """Regressão: `all` e `ativo` são os valores que a interface oferece hoje.
    Antes chegavam crus ao Postgres (500); agora param aqui, com 422 nomeando
    os aceitos — mesmo contrato que /cases já dá para o mesmo `status=all`."""
    with pytest.raises(HTTPException) as exc:
        _validar_status_prazo(valor)
    assert exc.value.status_code == 422
    assert repr(valor) in exc.value.detail
    for aceito in STATUS_PRAZO_VALIDOS:
        assert aceito in exc.value.detail


@pytest.mark.parametrize("vazio", [None, ""])
def test_status_vazio_nao_filtra(vazio):
    """Sem filtro = todos os status. É a saída legítima para 'quero ver tudo',
    e a mensagem do 422 aponta para ela."""
    assert _validar_status_prazo(vazio) is None
