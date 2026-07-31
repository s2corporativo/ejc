from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.document import DocConfidencialidade
from app.services.dossie_documental_canonico import montar_dossie_documental_canonico


class _ResultadoFake:
    def __init__(self, *, escalares=None, linhas=None):
        self._escalares = escalares
        self._linhas = linhas

    def scalars(self):
        return self

    def all(self):
        if self._escalares is not None:
            return self._escalares
        return self._linhas or []


class _DbFake:
    def __init__(self, respostas):
        self._respostas = list(respostas)

    async def execute(self, _stmt):
        return self._respostas.pop(0)


def _documento(*, doc_id: str, confidencialidade: DocConfidencialidade, texto: str):
    return SimpleNamespace(
        id=doc_id,
        case_id="caso-1",
        filename=f"{doc_id}.pdf",
        tipo="prova",
        ocr_text=texto,
        confidencialidade=confidencialidade,
        versao=1,
        versao_grupo_id=None,
        versao_anterior_id=None,
        created_at=datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_documento_do_cofre_nao_entra_no_contexto_da_ia():
    permitido = _documento(
        doc_id="doc-normal",
        confidencialidade=DocConfidencialidade.normal,
        texto="Fato documental autorizado para o contexto.",
    )
    sigiloso = _documento(
        doc_id="doc-sigiloso",
        confidencialidade=DocConfidencialidade.segredo_justica,
        texto="SEGREDO QUE NÃO PODE SAIR DO COFRE.",
    )
    db = _DbFake(
        [
            _ResultadoFake(escalares=[permitido, sigiloso]),
            _ResultadoFake(linhas=[]),
        ]
    )

    resultado = await montar_dossie_documental_canonico(db, "caso-1")

    assert resultado is not None
    assert resultado["qtd_documentos_total_ged"] == 2
    assert resultado["qtd_documentos"] == 1
    assert resultado["qtd_documentos_sigilosos_omitidos"] == 1
    assert "Fato documental autorizado para o contexto." in resultado["texto_contexto"]
    assert "SEGREDO QUE NÃO PODE SAIR DO COFRE." not in resultado["texto_contexto"]
    assert "AVISO DE SIGILO" in resultado["texto_contexto"]


@pytest.mark.asyncio
async def test_todos_os_documentos_sigilosos_geram_aviso_sem_vazar_conteudo():
    sigiloso = _documento(
        doc_id="doc-restrito",
        confidencialidade=DocConfidencialidade.restrito,
        texto="CONTEÚDO RESTRITO.",
    )
    db = _DbFake([_ResultadoFake(escalares=[sigiloso])])

    resultado = await montar_dossie_documental_canonico(db, "caso-1")

    assert resultado is not None
    assert resultado["qtd_documentos"] == 0
    assert resultado["qtd_documentos_sigilosos_omitidos"] == 1
    assert "CONTEÚDO RESTRITO." not in resultado["texto_contexto"]
    assert "originais permanecem preservados" in resultado["texto_contexto"]
