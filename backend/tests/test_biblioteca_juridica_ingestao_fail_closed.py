"""Regressões P0 da Biblioteca Jurídica: ingestão deve falhar para o lado seguro."""
from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "scripts" / "ingestao_biblioteca_juridica.py"
_SPEC = importlib.util.spec_from_file_location("ingestao_biblioteca_juridica", _SCRIPT)
assert _SPEC and _SPEC.loader
MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MOD)


def _doc(**overrides):
    base = {
        "tipo_camada": "jurisprudencia_estruturada",
        "canonical_id": "JUR-TEST-000001",
        "origem_conteudo": "jurisprudencia_oficial",
        "autoridade_juridica": "jurisprudencial",
        "score_autoridade": 90,
        "area_juridica": "consumidor_bancario",
        "nivel_confiaca": "ALTA",
        "data_pesquisa": "2026-08-14",
        "gerado_por_IA": False,
        "tribunal": "STJ",
        "link_official": "https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp?pesquisa_livre=466",
        "last_verified_at": "2026-08-14",
        "__file": "fixture.md",
        "__body": "Tribunal: STJ\nREsp 1.199.782/PR\nFonte: https://processo.stj.jus.br/SCON/",
        "__raw": "---\ntipo_camada: jurisprudencia_estruturada\n---\ncorpo",
    }
    base.update(overrides)
    return base


def test_simulacao_bloqueia_documento_oficial():
    d = _doc(__body="Tribunal: STJ\nREsp 1.199.782/PR\nURL Simulada: https://processo.stj.jus.br/SCON/")
    erros = MOD.validar([d])
    assert any("simulação" in e for e in erros)


def test_jurisprudencia_alta_sem_url_oficial_bloqueia():
    d = _doc(link_official=None, __body="Tribunal: STJ\nREsp 1.199.782/PR")
    erros = MOD.validar([d])
    assert any("sem URL oficial" in e or "sem fonte oficial" in e for e in erros)


def test_url_comercial_nao_e_tratada_como_oficial():
    d = _doc(
        link_official="https://exemplo.com/julgado",
        __body="Tribunal: STJ\nREsp 1.199.782/PR\nhttps://exemplo.com/julgado",
    )
    erros = MOD.validar([d])
    assert any("domínio institucional" in e or "sem fonte oficial" in e for e in erros)


def test_categoria_jurisprudencial_e_derivada_do_tribunal():
    assert MOD.categoria_rag(_doc(tribunal="STF")) == "jurisprudencia_stf"
    assert MOD.categoria_rag(_doc(tribunal="STJ")) == "jurisprudencia_stj"
    assert MOD.categoria_rag(_doc(tribunal="TJMG")) == "jurisprudencia_tjmg_acordaos"
    assert MOD.categoria_rag(_doc(tribunal="TRF6")) == "jurisprudencia_trf"


def test_fonte_primaria_e_classificada_por_area():
    d = _doc(
        tipo_camada="fonte_primaria",
        origem_conteudo="legislacao",
        autoridade_juridica="normativa",
        area_juridica="ambiental",
    )
    assert MOD.categoria_rag(d) == "legislacao_ambiental"


def test_ingestao_nunca_autoaprova_lote():
    extra = MOD.build_extra(_doc())
    assert extra["rag_status"] == "pendente"
    assert extra["requires_human_review"] is True
    assert extra["human_reviewed"] is False


def test_ia_nao_pode_receber_autoridade_jurisprudencial():
    d = _doc(gerado_por_IA=True)
    erros = MOD.validar([d])
    assert any("gerado por IA" in e for e in erros)
