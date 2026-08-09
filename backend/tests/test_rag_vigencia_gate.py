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


def test_filtro_de_vigencia_respeita_o_ramo_historico_da_inferencia():
    """`inferir_situacao_juridica` testa `vigente` ANTES do extra e devolve
    'historica' — situação DECLARADA — para toda versão não vigente. Sem essa
    guarda no espelho SQL, o histórico de legislação sem `legal_status` sumia da
    recuperação e levava junto o aviso 'possivelmente desatualizada', que
    `_artigo_superado`/`_sumula_superada` produzem consultando `vigente=FALSE`.
    Coluna NULL vale como não vigente, igual ao `bool()` do Python."""
    from app.models.rag import KnowledgeDoc
    from app.services.knowledge_governance import inferir_situacao_juridica

    doc = KnowledgeDoc(titulo="x", categoria="legislacao", extra={}, vigente=False)
    assert inferir_situacao_juridica(doc)["code"] == "historica"
    assert "COALESCE(kd.vigente, false) = true" in _FILTRO_VIGENCIA_VERIFICADA_RAG


def test_recorte_por_categoria_exclui_proposicao_por_decisao_registrada():
    """`LIKE '%legisl%'` alcança também `proposicao_legislativa` (ingestores da
    Câmara e do Senado), que não grava vigência. A exclusão é INTENCIONAL e
    PERMANENTE — proposição é projeto em tramitação, não lei em vigor — e por
    isso precisa estar escrita onde quem opera a flag vai ler."""
    from pathlib import Path

    import app.services.ai_service as mod

    fonte = Path(mod.__file__).read_text(encoding="utf-8")
    assert "proposicao_legislativa" in fonte, (
        "a captura de proposição pelo recorte precisa estar documentada no "
        "comentário do filtro, não descoberta em produção")
    env = Path(__file__).resolve().parents[2] / ".env.example"   # tests → backend → raiz
    assert "proposicao_legislativa" in env.read_text(encoding="utf-8"), (
        "quem liga/desliga a flag precisa saber que a exclusão da proposição é "
        "permanente e não se resolve reingerindo")


# ── 3b. Vigência de CURADOR sobrevive ao re-feed do ingestor ──────────────────

def test_decisao_de_curadoria_sobre_vigencia_nao_e_revertida_pelo_ingestor():
    """Review de segurança do PR #642: o job semanal do Planalto reescreve
    `legal_status` a cada execução (o merge do upsert deixa o extra do ingestor
    vencer, inclusive pelo atalho 'inalterado'). Um diploma marcado 'revogada'
    no painel voltaria sozinho a 'vigente' — e, como `governance_updated_by`
    continua apontando para o curador, o estado revertido ainda PARECERIA
    decisão humana."""
    from app.services.ingestion_service import _vigencia_de_curadoria

    assert _vigencia_de_curadoria({"legal_status": "revogada"}) is True
    assert _vigencia_de_curadoria(
        {"legal_status": "revogada", "legal_status_origem": "curadoria:u-1"}) is True


def test_leitura_de_ingestor_nao_se_disfarca_de_curadoria():
    """O que o ingestor gravou é RE-gravável pelo ingestor: a preservação vale
    só para decisão humana, senão a primeira leitura automática congelaria o
    documento e nenhuma reingestão poderia corrigi-la."""
    from app.services.ingestion_service import _vigencia_de_curadoria

    for origem in ("planalto:texto_compilado", "lexml:registro"):
        assert _vigencia_de_curadoria(
            {"legal_status": "vigente", "legal_status_origem": origem}) is False


def test_vigencia_nao_verificada_nao_conta_como_decisao():
    """`knowledge_autoapproval` grava 'vigencia_nao_verificada' por setdefault:
    é a AUSÊNCIA de decisão. Tratá-la como curadoria prenderia o documento fora
    da recuperação para sempre, já que nenhum re-feed poderia mais corrigi-lo."""
    from app.services.ingestion_service import _vigencia_de_curadoria

    assert _vigencia_de_curadoria({"legal_status": "vigencia_nao_verificada"}) is False
    assert _vigencia_de_curadoria({}) is False


def test_painel_de_governanca_carimba_a_origem_da_decisao():
    """Sem o carimbo, `upsert_documento` não distingue a decisão do curador da
    leitura do ingestor — e a preservação acima não teria como funcionar."""
    import inspect

    from app.routers import rag_governance
    from app.services.ingestion_service import ORIGEM_VIGENCIA_CURADORIA

    fonte = inspect.getsource(rag_governance.atualizar_governanca_documento)
    assert "ORIGEM_VIGENCIA_CURADORIA" in fonte
    assert 'if "legal_status" in values' in fonte
    assert ORIGEM_VIGENCIA_CURADORIA == "curadoria"


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
