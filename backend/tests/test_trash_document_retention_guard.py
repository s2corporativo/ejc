from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_documento_nao_pode_ser_purgado_sem_politica_de_retencao():
    from app.routers.trash import _validar_purga_irreversivel_disponivel

    with pytest.raises(HTTPException) as exc:
        _validar_purga_irreversivel_disponivel("documents")

    assert exc.value.status_code == 409
    detalhe = str(exc.value.detail).lower()
    assert "retenção" in detalhe
    assert "legal hold" in detalhe


def test_demais_entidades_mantem_fluxo_existente():
    from app.routers.trash import _validar_purga_irreversivel_disponivel

    for entidade in (
        "clients",
        "cases",
        "deadlines",
        "legal_docs",
        "fees",
        "procuracoes",
        "environmental_cases",
        "tasks",
    ):
        _validar_purga_irreversivel_disponivel(entidade)


def test_registro_lixeira_preserva_entidade_ambiental_e_ordem():
    from app.routers.trash import ENTIDADES

    chaves = list(ENTIDADES)
    assert "environmental_cases" in ENTIDADES
    assert chaves.index("environmental_cases") < chaves.index("tasks")
