"""#1401 — CSV Formula Injection deve permanecer neutralizada em todos os exports."""
from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.csv_safe import sanitize_csv_cell, sanitize_csv_row
from app.routers import deadlines, despesas, export


@pytest.mark.parametrize(
    "payload",
    [
        "=HYPERLINK(\"https://exemplo.invalid\")",
        "+SUM(1,2)",
        "-1+2",
        "@SUM(A1:A2)",
        "\t=cmd",
        "\r+SUM(1,2)",
        "  @SUM(A1:A2)",
    ],
)
def test_celula_textual_com_prefixo_de_formula_recebe_apostrofo(payload):
    assert sanitize_csv_cell(payload) == "'" + payload


def test_valores_numericos_tipados_permanecem_numericos():
    assert sanitize_csv_cell(-12.5) == -12.5
    assert sanitize_csv_cell(10) == 10


def test_texto_normal_nao_e_alterado():
    assert sanitize_csv_row(["Cliente", "texto normal", 12]) == ["Cliente", "texto normal", 12]


def test_export_de_prazos_neutraliza_titulo_e_base_legal():
    prazo = SimpleNamespace(
        titulo="=HYPERLINK(\"https://exemplo.invalid\")",
        tipo="processual",
        prioridade="alta",
        status="pendente",
        data_prazo=date(2026, 9, 20),
        data_intimacao=date(2026, 9, 10),
        base_legal="\t@SUM(A1:A2)",
    )
    texto = deadlines._prazos_para_csv([prazo], date(2026, 9, 17))
    assert "'=HYPERLINK" in texto
    assert "'\t@SUM" in texto


def test_guard_todos_os_exportadores_backend_usam_sanitizador_canonico():
    assert "sanitize_csv_row" in inspect.getsource(export._csv)
    assert "sanitize_csv_row" in inspect.getsource(deadlines._prazos_para_csv)
    assert "sanitize_csv_row" in inspect.getsource(despesas.export_despesas_csv)
