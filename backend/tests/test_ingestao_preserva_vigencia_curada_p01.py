"""Regressão P0.1: nova versão não apaga decisão humana de vigência."""
from __future__ import annotations

from app.models.rag import KnowledgeDoc
from app.services.ingestion_service import upsert_documento


class _Resultado:
    def __init__(self, doc):
        self._doc = doc

    def scalar_one_or_none(self):
        return self._doc


class _BancoFalso:
    def __init__(self, existente):
        self.existente = existente
        self.adicionados = []

    async def execute(self, _stmt, _params=None):
        return _Resultado(self.existente)

    async def flush(self):
        return None

    def add(self, obj):
        self.adicionados.append(obj)


async def test_nova_versao_preserva_status_e_proveniencia_da_curadoria():
    existente = KnowledgeDoc(
        id="doc-antigo",
        titulo="Lei antiga",
        categoria="legislacao",
        chave_origem="planalto:lei-teste",
        hash_conteudo="hash-anterior",
        versao=3,
        vigente=True,
        extra={
            "legal_status": "revogada",
            "legal_status_origem": "curadoria:u-123",
            "legal_status_verificado_em": "2026-08-08T12:00:00+00:00",
            "governance_updated_by": "u-123",
        },
    )
    db = _BancoFalso(existente)

    resultado = await upsert_documento(
        db,
        titulo="Lei atualizada na fonte",
        categoria="legislacao",
        conteudo=(
            "Conteúdo oficial alterado da norma, suficientemente longo para "
            "forçar nova versão no pipeline de conhecimento jurídico."
        ),
        chave_origem="planalto:lei-teste",
        fonte="https://www.planalto.gov.br/",
        extra={
            "legal_status": "vigente",
            "legal_status_origem": "planalto:texto_compilado",
            "legal_status_inferido_em": "2026-08-09T10:00:00+00:00",
        },
        embutir_vetores=False,
        chunks=[
            "Art. 1 Conteúdo atualizado suficientemente longo para compor um chunk de teste."
        ],
    )

    novos_docs = [obj for obj in db.adicionados if isinstance(obj, KnowledgeDoc)]
    assert resultado == "atualizado"
    assert len(novos_docs) == 1
    novo = novos_docs[0]
    assert existente.vigente is False
    assert novo.versao == 4
    assert novo.versao_anterior_id == "doc-antigo"
    assert novo.extra["legal_status"] == "revogada"
    assert novo.extra["legal_status_origem"] == "curadoria:u-123"
    assert novo.extra["legal_status_verificado_em"] == "2026-08-08T12:00:00+00:00"
    assert "legal_status_inferido_em" not in novo.extra


async def test_nova_versao_pode_atualizar_status_quando_anterior_nao_era_curadoria():
    existente = KnowledgeDoc(
        id="doc-auto",
        titulo="Lei automática",
        categoria="legislacao",
        chave_origem="planalto:lei-auto",
        hash_conteudo="hash-anterior",
        versao=1,
        vigente=True,
        extra={
            "legal_status": "vigencia_nao_verificada",
            "legal_status_origem": "planalto:texto_compilado",
        },
    )
    db = _BancoFalso(existente)

    await upsert_documento(
        db,
        titulo="Lei automática atualizada",
        categoria="legislacao",
        conteudo=(
            "Conteúdo oficial novo suficientemente longo para gerar uma nova "
            "versão sem congelar metadado automático antigo."
        ),
        chave_origem="planalto:lei-auto",
        extra={
            "legal_status": "revogada",
            "legal_status_origem": "planalto:texto_compilado",
            "legal_status_verificado_em": "2026-08-09T10:00:00+00:00",
        },
        embutir_vetores=False,
        chunks=[
            "Art. 1 Conteúdo novo suficientemente longo para compor um chunk de teste válido."
        ],
    )

    novo = next(obj for obj in db.adicionados if isinstance(obj, KnowledgeDoc))
    assert novo.extra["legal_status"] == "revogada"
    assert novo.extra["legal_status_origem"] == "planalto:texto_compilado"


async def test_status_legado_sem_origem_nao_e_presumido_curadoria_humana():
    """Ausência de origem é ausência de prova de autoria humana, não curadoria."""
    existente = KnowledgeDoc(
        id="doc-legado-sem-origem",
        titulo="Lei legada",
        categoria="legislacao",
        chave_origem="planalto:lei-legada",
        hash_conteudo="hash-anterior",
        versao=2,
        vigente=True,
        extra={
            "legal_status": "vigente",
            "legal_status_verificado_em": "2025-01-01T10:00:00+00:00",
        },
    )
    db = _BancoFalso(existente)

    await upsert_documento(
        db,
        titulo="Lei legada atualizada",
        categoria="legislacao",
        conteudo=(
            "Conteúdo oficial realmente alterado e suficientemente longo para "
            "criar nova versão sem preservar status legado de origem desconhecida."
        ),
        chave_origem="planalto:lei-legada",
        extra={
            "legal_status": "revogada",
            "legal_status_origem": "planalto:texto_compilado",
            "legal_status_verificado_em": "2026-08-09T11:00:00+00:00",
        },
        embutir_vetores=False,
        chunks=[
            "Art. 1 Conteúdo alterado suficientemente longo para compor um chunk de teste."
        ],
    )

    novo = next(obj for obj in db.adicionados if isinstance(obj, KnowledgeDoc))
    assert novo.extra["legal_status"] == "revogada"
    assert novo.extra["legal_status_origem"] == "planalto:texto_compilado"
    assert novo.extra["legal_status_verificado_em"] == "2026-08-09T11:00:00+00:00"
