"""Trava anti-drift: os status de caso do frontend devem espelhar o backend.

A verdade física é o ENUM `casestatus` do Postgres, refletido em
`app.models.case.CaseStatus` e agrupado em `app.core.status_caso`. O frontend
não consegue importar Python, então mantém a própria cópia em
`frontend/src/types/caseStatus.ts`.

Cópia sem trava vira divergência: era exatamente assim que o repositório
acumulou quatro listas de status no frontend, com chaves mortas
(`em_andamento`, `cancelado`, `inativo`) e ausências (`triagem`, `acordo`), o
que produzia contagens diferentes para o mesmo rótulo em telas diferentes.

Este teste falha no CI se alguém alterar o enum de um lado e esquecer o outro.
Segue o precedente de `test_module_registry.py`, que também lê o frontend.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.status_caso import STATUS_ABERTOS, STATUS_FECHADOS
from app.models.case import CaseStatus

ARQUIVO_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "types" / "caseStatus.ts"
)


def _extrair_lista(fonte: str, nome: str) -> list[str]:
    """Lê os literais de uma const TS do tipo `export const NOME = [...]`."""
    m = re.search(rf"export const {nome}[^=]*=\s*\[(.*?)\]", fonte, re.S)
    assert m, f"const {nome} não encontrada em {ARQUIVO_TS.name}"
    return re.findall(r'"([^"]+)"', m.group(1))


@pytest.fixture(scope="module")
def fonte_ts() -> str:
    assert ARQUIVO_TS.exists(), f"fonte única do frontend ausente: {ARQUIVO_TS}"
    return ARQUIVO_TS.read_text(encoding="utf-8")


def test_lista_de_status_bate_com_o_enum_do_backend(fonte_ts):
    do_front = _extrair_lista(fonte_ts, "CASE_STATUS")
    do_back = [s.value for s in CaseStatus]
    assert do_front == do_back, (
        "frontend/src/types/caseStatus.ts divergiu de CaseStatus. "
        f"frontend={do_front} backend={do_back}"
    )


def test_agregado_abertos_bate(fonte_ts):
    do_front = _extrair_lista(fonte_ts, "CASE_STATUS_ABERTOS")
    do_back = [s.value for s in STATUS_ABERTOS]
    assert do_front == do_back, (
        "CASE_STATUS_ABERTOS divergiu de STATUS_ABERTOS (core/status_caso.py). "
        f"frontend={do_front} backend={do_back}"
    )


def test_agregado_fechados_bate(fonte_ts):
    do_front = _extrair_lista(fonte_ts, "CASE_STATUS_FECHADOS")
    do_back = [s.value for s in STATUS_FECHADOS]
    assert do_front == do_back, (
        "CASE_STATUS_FECHADOS divergiu de STATUS_FECHADOS (core/status_caso.py). "
        f"frontend={do_front} backend={do_back}"
    )


def test_abertos_e_fechados_particionam_o_enum():
    """Todo status pertence a exatamente um dos dois grupos.

    Se um status novo entrar no enum sem ser classificado, ele ficaria fora das
    duas listas e sumiria silenciosamente das contagens.
    """
    abertos, fechados = set(STATUS_ABERTOS), set(STATUS_FECHADOS)
    assert not (abertos & fechados), "status não pode ser aberto e fechado"
    assert abertos | fechados == set(CaseStatus), (
        "há status do enum fora de STATUS_ABERTOS e STATUS_FECHADOS: "
        f"{set(CaseStatus) - (abertos | fechados)}"
    )


def test_rotulos_cobrem_todos_os_status(fonte_ts):
    """`CASE_STATUS_LABEL` sem buraco: nenhum status cai em fallback cru."""
    m = re.search(
        r"export const CASE_STATUS_LABEL[^=]*=\s*\{(.*?)\n\};", fonte_ts, re.S
    )
    assert m, "CASE_STATUS_LABEL não encontrada"
    rotulados = set(re.findall(r"^\s*(\w+):", m.group(1), re.M))
    assert rotulados == {s.value for s in CaseStatus}, (
        f"rótulos incompletos ou sobrando: {rotulados ^ {s.value for s in CaseStatus}}"
    )
