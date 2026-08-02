"""Gate de SITUAÇÃO JURÍDICA na recuperação RAG (Issue #636).

Antes deste gate, curadoria (`rag_status`) e vigência da norma eram campos
distintos e só o primeiro era olhado na recuperação: um documento podia estar
'aprovado' para o RAG e, ao mesmo tempo, revogado ou com vigência nunca
conferida. Estes testes fecham a regressão em DOIS pontos:

1. o fragmento SQL do gate (`_filtros_gate_rag`) exclui norma REVOGADA sempre e,
   sob RAG_EXIGIR_VIGENCIA_VERIFICADA, também a legislação sem vigência
   declarada — sem esvaziar o resto do acervo (o recorte é por categoria);
2. o fragmento chega às consultas reais de `buscar_contexto_rag`.

Mesmo padrão de test_rag_isolation.py: fakes locais, sem rede e sem banco. A
prova ROW-LEVEL (o documento revogado realmente não volta da busca) está em
test_rag_gate_governanca_dblevel.py, que roda com Postgres no CI.
"""
from __future__ import annotations

import pytest

from app.services import ai_service
from app.services.ai_service import (
    _FILTRO_REVOGADA_RAG,
    _FILTRO_VIGENCIA_VERIFICADA_RAG,
    _filtros_gate_rag,
    buscar_contexto_rag,
)


@pytest.fixture(autouse=True)
def _busca_textual_sem_download(monkeypatch):
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)


class _CaptureDB:
    """Captura o SQL/params da última consulta; retorna zero linhas."""

    def __init__(self):
        self.sql = ""
        self.params = {}

    async def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or {}
        return []


def _flags(monkeypatch, *, vigencia: bool):
    monkeypatch.setattr(
        ai_service.settings, "RAG_EXIGIR_VIGENCIA_VERIFICADA", vigencia
    )


# ── 1. Default seguro ─────────────────────────────────────────────────────────

def test_default_de_fabrica_exige_vigencia_verificada():
    from app.core.config import Settings

    assert Settings.model_fields["RAG_EXIGIR_VIGENCIA_VERIFICADA"].default is True


# ── 2. Revogada: exclusão INCONDICIONAL ───────────────────────────────────────

def test_revogada_sai_da_recuperacao_independente_de_flag(monkeypatch):
    """Norma revogada nunca é fundamentação atual — não há flag que a devolva."""
    for vigencia in (True, False):
        _flags(monkeypatch, vigencia=vigencia)
        assert _FILTRO_REVOGADA_RAG in _filtros_gate_rag(False)
        assert _FILTRO_REVOGADA_RAG in _filtros_gate_rag(True)


def test_filtro_revogada_le_as_tres_chaves_de_vigencia():
    """Mesma precedência de knowledge_governance.inferir_situacao_juridica."""
    for chave in ("legal_status", "situacao_normativa", "vigencia_status"):
        assert f"kd.extra->>'{chave}'" in _FILTRO_REVOGADA_RAG
    assert "'revogada'" in _FILTRO_REVOGADA_RAG
    # 'parcialmente_revogada' é aviso, NÃO bloqueio (permanece recuperável)
    assert "'parcialmente_revogada'" not in _FILTRO_REVOGADA_RAG


# ── 3. Vigência não verificada: sob flag, e só para legislação ────────────────

def test_flag_ligada_exclui_vigencia_nao_verificada(monkeypatch):
    _flags(monkeypatch, vigencia=True)
    assert _FILTRO_VIGENCIA_VERIFICADA_RAG in _filtros_gate_rag(False)


def test_flag_desligada_devolve_vigencia_nao_verificada(monkeypatch):
    _flags(monkeypatch, vigencia=False)
    gate = _filtros_gate_rag(False)
    assert _FILTRO_VIGENCIA_VERIFICADA_RAG not in gate
    # ...sem afrouxar o que não é opcional
    assert _FILTRO_REVOGADA_RAG in gate


def test_filtro_de_vigencia_so_alcanca_legislacao():
    """Efeito colateral proibido: a inferência devolve 'nao_aplicavel' (que
    PERMITE fundamentação) para o que não é legislação, então súmula,
    jurisprudência, doutrina e modelos não podem sair da base por este filtro."""
    assert "kd.categoria" in _FILTRO_VIGENCIA_VERIFICADA_RAG
    assert "'%legisl%'" in _FILTRO_VIGENCIA_VERIFICADA_RAG
    assert _FILTRO_VIGENCIA_VERIFICADA_RAG.startswith("AND NOT (")


def test_situacao_declarada_espelha_o_vocabulario_da_governanca():
    """O conjunto reconhecido no SQL não pode ser MAIOR que o da inferência —
    senão o gate deixaria passar como declarado algo que a governança considera
    não verificado."""
    from app.services.knowledge_governance import LEGAL_STATUS_VALUES
    from app.services.ai_service import _SQL_SITUACAO_DECLARADA

    declarados = {
        v.strip().strip("'")
        for v in _SQL_SITUACAO_DECLARADA.strip("()").split(",")
    }
    aliases = {"parcialmente revogada", "nao aplicavel", "não aplicável", "revogado"}
    assert declarados - aliases <= LEGAL_STATUS_VALUES
    # 'vigencia_nao_verificada' JAMAIS conta como vigência declarada
    assert "vigencia_nao_verificada" not in declarados


# ── 4. Os filtros chegam às consultas reais ───────────────────────────────────

async def test_consulta_textual_aplica_gate_de_vigencia(monkeypatch):
    _flags(monkeypatch, vigencia=True)
    db = _CaptureDB()
    await buscar_contexto_rag(db, "consulta de teste sobre tese qualquer", limite=3)
    assert _FILTRO_REVOGADA_RAG in db.sql
    assert _FILTRO_VIGENCIA_VERIFICADA_RAG in db.sql
    # o gate é fragmento SQL puro: nenhum bind param novo para propagar
    assert "legal_status" not in db.params


async def test_geracao_de_peca_com_ficticio_mantem_gate_de_vigencia(monkeypatch):
    """incluir_ficticio=True libera modelos, não norma revogada."""
    _flags(monkeypatch, vigencia=True)
    db = _CaptureDB()
    await buscar_contexto_rag(
        db, "modelo de peça", limite=3,
        categorias=["modelo_documento_juridico"], incluir_ficticio=True,
    )
    assert _FILTRO_REVOGADA_RAG in db.sql
    assert _FILTRO_VIGENCIA_VERIFICADA_RAG in db.sql


def test_citation_gate_herda_o_mesmo_filtro():
    """O verificador de citações usa o gate central: um artigo de norma revogada
    não pode ser certificado como existente."""
    import inspect

    from app.services import citation_check

    assert "_filtros_gate_rag" in inspect.getsource(citation_check._fonte_artigo)


def test_gate_nao_enfraquece_os_controles_anteriores(monkeypatch):
    """Este PR só APERTA: aprovação, quarentena de súmulas e exclusão do corpus
    fictício seguem no fragmento."""
    from app.services.ai_service import (
        _FILTRO_APROVADO_RAG,
        _FILTRO_FICTICIO_RAG,
        _FILTRO_GATE_RAG,
        _FILTRO_SUMULAS_QUARENTENA,
    )

    _flags(monkeypatch, vigencia=True)
    gate = _filtros_gate_rag(False)
    for fragmento in (_FILTRO_GATE_RAG, _FILTRO_APROVADO_RAG,
                      _FILTRO_SUMULAS_QUARENTENA, _FILTRO_FICTICIO_RAG):
        assert fragmento in gate
