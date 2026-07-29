"""Detector de resíduos do caso de origem (Modo Molde — Fase 2).

O Modo Molde reaproveita a estrutura de uma peça anterior; o risco jurídico é
o dado do cliente ANTERIOR sobreviver na peça nova (quebra de sigilo — EOAB
art. 34/LGPD). Até a Fase 2 isso era apenas uma frase no prompt: nenhuma
verificação acontecia. Estes testes cobrem a detecção determinística.

Sem banco: `detectar_residuos` é função pura.
"""
from __future__ import annotations

import pytest

from app.services.peca_residuos import (
    IdentificadoresCaso,
    detectar_residuos,
)


def _origem() -> IdentificadoresCaso:
    return IdentificadoresCaso(
        cliente=["Construtora Beta Ltda"],
        parte_contraria=["Banco Alfa S/A"],
        documento=["12345678000199"],
        processo=["10012345620248130024"],
    )


# ── achados ──────────────────────────────────────────────────────────────────

def test_nome_do_cliente_anterior_e_detectado():
    achados = detectar_residuos(
        "Requer a condenação, conforme contrato firmado pela Construtora Beta "
        "Ltda em 2024.",
        _origem(),
    )
    assert [a["categoria"] for a in achados] == ["cliente"]
    assert achados[0]["termo"] == "Construtora Beta Ltda"
    assert "Remova ou substitua" in achados[0]["mensagem"]


def test_parte_contraria_anterior_e_detectada():
    achados = detectar_residuos("Ação movida em face do Banco Alfa S/A.", _origem())
    assert [a["categoria"] for a in achados] == ["parte_contraria"]


def test_detecta_documento_com_e_sem_mascara():
    # A peça formata o CNPJ; o identificador guardado é só dígitos.
    achados = detectar_residuos(
        "Inscrita no CNPJ sob o nº 12.345.678/0001-99.", _origem()
    )
    assert [a["categoria"] for a in achados] == ["documento"]

    achados_cru = detectar_residuos("CNPJ 12345678000199", _origem())
    assert [a["categoria"] for a in achados_cru] == ["documento"]


def test_detecta_numero_de_processo_formatado():
    achados = detectar_residuos(
        "Autos nº 1001234-56.2024.8.13.0024, em trâmite.", _origem()
    )
    assert [a["categoria"] for a in achados] == ["processo"]


def test_comparacao_ignora_acento_e_caixa():
    origem = IdentificadoresCaso(cliente=["JOSÉ DA SILVA SAURO"])
    achados = detectar_residuos("outorgado por jose da silva sauro.", origem)
    assert len(achados) == 1


def test_varios_residuos_de_categorias_distintas():
    achados = detectar_residuos(
        "Construtora Beta Ltda, CNPJ 12.345.678/0001-99, nos autos "
        "1001234-56.2024.8.13.0024 contra Banco Alfa S/A.",
        _origem(),
    )
    assert sorted(a["categoria"] for a in achados) == [
        "cliente", "documento", "parte_contraria", "processo",
    ]


def test_achado_repetido_aparece_uma_vez_so():
    achados = detectar_residuos(
        "Construtora Beta Ltda … novamente Construtora Beta Ltda.", _origem()
    )
    assert len(achados) == 1


# ── o que NÃO pode virar achado ──────────────────────────────────────────────

def test_peca_limpa_nao_gera_achado():
    texto = "Requer a procedência dos pedidos, com base no art. 186 do CC."
    assert detectar_residuos(texto, _origem()) == []


def test_identificador_do_caso_de_destino_e_legitimo():
    """Mesmo cliente nos dois casos: o nome na peça nova é correto, não resíduo."""
    destino = IdentificadoresCaso(
        cliente=["Construtora Beta Ltda"],
        documento=["12345678000199"],
    )
    achados = detectar_residuos(
        "Construtora Beta Ltda, CNPJ 12.345.678/0001-99, requer…",
        _origem(),
        destino,
    )
    # Só sobram os identificadores que NÃO pertencem ao destino.
    assert [a["categoria"] for a in achados] == []


def test_nome_curto_nao_dispara_falso_positivo():
    # Abaixo do piso: "S/A", "Ltda" e iniciais apareceriam em toda peça.
    origem = IdentificadoresCaso(cliente=["S/A"], parte_contraria=["ABC"])
    assert detectar_residuos("Empresa S/A e outros. ABC.", origem) == []


def test_nome_nao_casa_dentro_de_outra_palavra():
    origem = IdentificadoresCaso(cliente=["Susan"])
    # "Susana" contém "Susan", mas é outra pessoa — fronteira de palavra.
    assert detectar_residuos("A testemunha Susana compareceu.", origem) == []


def test_sequencia_curta_de_digitos_e_ignorada():
    # Abaixo de 11 dígitos não identifica ninguém (valores, datas, artigos).
    origem = IdentificadoresCaso(documento=["12345"], processo=["987654"])
    assert detectar_residuos("Valor de R$ 12.345,00 e 987654.", origem) == []


def test_texto_vazio_nao_quebra():
    assert detectar_residuos("", _origem()) == []
    assert detectar_residuos("   ", _origem()) == []


def test_origem_vazia_nao_gera_achado():
    assert detectar_residuos("Qualquer texto.", IdentificadoresCaso()) == []


# ── coleta de identificadores (fail-soft) ────────────────────────────────────

@pytest.mark.anyio
async def test_coletar_identificadores_sem_case_id_devolve_vazio():
    from app.services.peca_residuos import coletar_identificadores

    ids = await coletar_identificadores(None, None)  # type: ignore[arg-type]
    assert ids.cliente == [] and ids.documento == []


@pytest.mark.anyio
async def test_detectar_do_molde_sem_documento_devolve_vazio():
    from app.services.peca_residuos import detectar_residuos_do_molde

    achados = await detectar_residuos_do_molde(
        None, "texto", documento_molde_id=None, case_id_destino="c1",  # type: ignore[arg-type]
    )
    assert achados == []
