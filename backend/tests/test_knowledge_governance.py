"""Testes unitários da governança da Base de Conhecimento."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.rag import KnowledgeDoc
from app.services.ai import reranker
from app.services.knowledge_governance import (
    avaliar_frescor,
    avaliar_qualidade,
    detectar_duplicidades,
    dimensao_cobertura,
    inferir_autoridade,
    inferir_situacao_juridica,
)


def _doc(**kwargs) -> KnowledgeDoc:
    defaults = {
        "id": "doc-1",
        "titulo": "Lei de teste",
        "categoria": "legislacao",
        "fonte": "https://www.planalto.gov.br/ccivil_03/leis/teste.htm",
        "extra": {"rag_status": "aprovado"},
        "vigente": True,
        "versao": 1,
        "status_indexacao": "indexado",
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return KnowledgeDoc(**defaults)


def test_fonte_oficial_normativa_tem_maior_autoridade():
    result = inferir_autoridade(
        "legislacao",
        "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
        {},
    )
    assert result["code"] == "oficial_normativa"
    assert result["official"] is True
    assert result["weight"] == 100


def test_legislacao_nao_oficial_nao_e_promovida():
    result = inferir_autoridade("legislacao", "https://blog.exemplo.com/lei", {})
    assert result["code"] == "referencial"
    assert result["official"] is False


def test_versao_atual_nao_presume_vigencia_juridica():
    result = inferir_situacao_juridica(_doc(extra={"rag_status": "aprovado"}))
    assert result["code"] == "vigencia_nao_verificada"
    assert result["requires_warning"] is True


def test_norma_revogada_bloqueia_fundamentacao_atual():
    result = inferir_situacao_juridica(
        _doc(extra={"rag_status": "aprovado", "legal_status": "revogada"})
    )
    assert result["blocks_current_law"] is True
    assert result["permite_fundamentacao_atual"] is False


def test_qualidade_detecta_documento_sem_chunks():
    result = avaliar_qualidade(_doc(), chunks=0, chars=0, embedded_chunks=0)
    assert result["status"] == "incompleto"
    assert result["score"] < 60
    assert any("sem trechos" in issue.lower() for issue in result["issues"])


def test_frescor_de_legislacao_oficial_expira_em_ciclo_curto():
    result = avaliar_frescor(
        _doc(created_at=datetime.now(timezone.utc) - timedelta(days=40))
    )
    assert result["status"] == "desatualizado"
    assert result["threshold_days"] == 14


def test_dimensao_de_cobertura_reconhece_modelos():
    assert dimensao_cobertura(_doc(categoria="precedente_interno")) == "modelos"


def test_duplicidade_e_conflito_sao_separados():
    same_a = _doc(id="a", titulo="Lei A", hash_conteudo="hash-1")
    same_b = _doc(id="b", titulo="Lei A cópia", hash_conteudo="hash-1")
    conflict_a = _doc(id="c", titulo="Lei conflitante", hash_conteudo="hash-2")
    conflict_b = _doc(id="d", titulo="Lei conflitante", hash_conteudo="hash-3")

    duplicates, conflicts = detectar_duplicidades([same_a, same_b, conflict_a, conflict_b])

    assert len(duplicates) == 1
    assert len(conflicts) == 1


@pytest.mark.asyncio
def _candidato_legislacao() -> dict:
    return {
        "doc_id": "d1",
        "chunk_id": "c1",
        "titulo": "Lei oficial",
        "categoria": "legislacao",
        "fonte": "https://www.planalto.gov.br/lei",
        "versao": 2,
        "conteudo": "conteúdo",
        "confianca": "alta",
    }


async def test_reranker_enriquece_citacao_mesmo_desabilitado(monkeypatch):
    monkeypatch.setattr(reranker, "disponivel", lambda: False)
    # A hidratação de governança abre sessão própria (AsyncSessionLocal) e não
    # tem banco aqui. Este teste é sobre o ENRIQUECIMENTO com o cross-encoder
    # desligado, não sobre o gate — então a hidratação é neutralizada para não
    # confundir as duas coisas. O gate tem teste próprio logo abaixo.
    async def _passa_direto(candidatos):
        return candidatos

    monkeypatch.setattr(reranker, "_hidratar_governanca", _passa_direto)

    result = await reranker.rerank("consulta", [_candidato_legislacao()], 1)

    assert result[0]["autoridade"]["code"] == "oficial_normativa"
    assert result[0]["citacao"]["versao"] == 2
    assert result[0]["citacao"]["documento_id"] == "d1"


async def test_reranker_descarta_normativo_sem_governanca(monkeypatch):
    """Fail-closed: sem conseguir carregar a governança, material NORMATIVO sai
    do ranking em vez de seguir sem verificação.

    Norma revogada ou em quarentena que passasse por aqui viraria fundamentação
    de peça. Conteúdo não normativo (doutrina, jurisprudência) não corre esse
    risco e continua passando — o gate é recortado, não um apagão."""
    monkeypatch.setattr(reranker, "disponivel", lambda: False)

    doutrina = dict(_candidato_legislacao(), doc_id="d2", chunk_id="c2",
                    categoria="doutrina", titulo="Comentário doutrinário")

    # Sem banco, `_hidratar_governanca` cai no except e aplica o recorte.
    result = await reranker.rerank(
        "consulta", [_candidato_legislacao(), doutrina], 5
    )

    ids = [item["doc_id"] for item in result]
    assert "d1" not in ids, "legislação sem governança não pode ser recuperada"
    assert ids == ["d2"], "doutrina não é normativa e deve seguir no ranking"
