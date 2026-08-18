"""Regressões P0 da Biblioteca Jurídica: ingestão deve falhar para o lado seguro."""
from __future__ import annotations

import importlib.util
import inspect
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


def test_simulacao_bloqueia_documento_com_autoridade():
    d = _doc(__body="Tribunal: STJ\nREsp 1.199.782/PR\nURL Simulada: https://processo.stj.jus.br/SCON/")
    erros = MOD.validar([d])
    assert any("simulado" in e.lower() for e in erros)


def test_marcador_simulado_entre_parenteses_tambem_bloqueia():
    d = _doc(
        __body=(
            "Tribunal: STJ\nREsp 1.199.782/PR\n"
            "https://processo.stj.jus.br/SCON/ (Simulado, fonte oficial: stj.jus.br)"
        )
    )
    erros = MOD.validar([d])
    assert any("simulado" in e.lower() for e in erros)


def test_nota_historica_de_auditoria_nao_e_falso_positivo():
    d = _doc(
        __body=(
            "Tribunal: STJ\nREsp 1.199.782/PR\n"
            "Fonte: https://processo.stj.jus.br/SCON/\n"
            "Nota: a versão anterior continha referências simuladas e foi substituída."
        )
    )
    erros = MOD.validar([d])
    assert not any("simulado" in e.lower() for e in erros)


def test_modelo_ficticio_sem_autoridade_pode_existir_como_estrutura():
    d = _doc(
        tipo_camada="modelo_peca",
        canonical_id="MOD-TEST-000001",
        origem_conteudo="modelo_IA",
        autoridade_juridica="modelo_sem_autoridade",
        score_autoridade=0,
        nivel_confiaca="BAIXA",
        gerado_por_IA=True,
        tribunal=None,
        link_official=None,
        last_verified_at=None,
        __body="MODELO DIDÁTICO. Processo fictício 0000000-00.0000.0.00.0000. Não usar como fonte.",
    )
    erros = MOD.validar([d])
    assert erros == []


def test_modelo_ia_com_score_de_autoridade_e_bloqueado():
    d = _doc(
        tipo_camada="modelo_peca",
        canonical_id="MOD-TEST-000002",
        origem_conteudo="modelo_IA",
        autoridade_juridica="modelo_sem_autoridade",
        score_autoridade=10,
        nivel_confiaca="BAIXA",
        gerado_por_IA=True,
        tribunal=None,
        link_official=None,
        last_verified_at=None,
        __body="Modelo didático sem valor de fonte jurídica.",
    )
    erros = MOD.validar([d])
    assert any("score_autoridade=0" in e for e in erros)


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


def test_execute_tem_transacao_unica_e_commit_so_no_final():
    """Regressão P0: falha no documento N não pode deixar 1..N-1 commitados."""
    fonte = inspect.getsource(MOD.main)
    assert fonte.count("async with AsyncSessionLocal() as db") == 1
    assert fonte.count("await db.commit()") == 1
    assert fonte.count("await db.rollback()") == 1
    pos_sessao = fonte.index("async with AsyncSessionLocal() as db")
    pos_loop = fonte.index("for d in docs", pos_sessao)
    pos_commit = fonte.index("await db.commit()", pos_loop)
    assert pos_sessao < pos_loop < pos_commit
    assert "rollback integral executado" in fonte
