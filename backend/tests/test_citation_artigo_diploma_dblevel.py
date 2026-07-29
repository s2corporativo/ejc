"""P0 — verificação determinística de artigo × diploma com Postgres real."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres com migrations (defina RUN_DB_TESTS=1)",
)


@pytest.fixture(autouse=True)
async def _isolar_pool_por_event_loop():
    from app.core.database import engine

    await engine.dispose(close=False)
    yield
    await engine.dispose(close=False)


async def _inserir_diploma(
    db,
    *,
    chave: str,
    titulo: str,
    conteudo: str,
    vigente: bool = True,
    versao: int = 1,
) -> str:
    doc_id = str(uuid4())
    await db.execute(
        text(
            """
            INSERT INTO knowledge_docs (
                id, titulo, categoria, chave_origem, status_indexacao,
                versao, vigente, revisado, extra, base_rag
            ) VALUES (
                :id, :titulo, 'legislacao', :chave, 'indexado',
                :versao, :vigente, true,
                CAST(:extra AS jsonb), 'publica'
            )
            """
        ),
        {
            "id": doc_id,
            "titulo": titulo,
            "chave": chave,
            "versao": versao,
            "vigente": vigente,
            "extra": '{"rag_status":"aprovado","confidence_level":"alta"}',
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo)
            VALUES (:id, :doc_id, 0, :conteudo)
            """
        ),
        {"id": str(uuid4()), "doc_id": doc_id, "conteudo": conteudo},
    )
    return doc_id


async def _limpar(db, ids: list[str]) -> None:
    if ids:
        await db.execute(
            text("DELETE FROM knowledge_docs WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        await db.commit()


async def _verificar(db, texto_citacao: str) -> dict:
    from app.services.citation_check import verificar_citacoes

    relatorio = await verificar_citacoes(db, texto_citacao)
    assert relatorio["total"] == 1
    return relatorio["citacoes"][0]


@pytest.mark.parametrize(
    (
        "texto_citacao",
        "numero",
        "chave_correta",
        "titulo_correto",
        "chave_errada",
        "titulo_errado",
    ),
    [
        (
            "Tutela de urgência conforme o art. 300 do CPC.",
            "300",
            "planalto:cpc",
            "Código de Processo Civil (Lei 13.105/2015)",
            "planalto:cp",
            "Código Penal (DL 2.848/1940)",
        ),
        (
            "Garantia fundamental prevista no art. 5º da CF.",
            "5",
            "planalto:cf88",
            "Constituição Federal de 1988",
            "planalto:cc",
            "Código Civil (Lei 10.406/2002)",
        ),
        (
            "Direito básico do consumidor previsto no art. 6º do CDC.",
            "6",
            "planalto:cdc",
            "Código de Defesa do Consumidor (Lei 8.078/1990)",
            "planalto:ctn",
            "Código Tributário Nacional (Lei 5.172/1966)",
        ),
        (
            "Responsabilidade civil fundada no art. 927 do CC.",
            "927",
            "planalto:cc",
            "Código Civil (Lei 10.406/2002)",
            "planalto:cpc",
            "Código de Processo Civil (Lei 13.105/2015)",
        ),
    ],
)
async def test_artigo_so_confirma_no_diploma_citado_e_expoe_fonte(
    texto_citacao,
    numero,
    chave_correta,
    titulo_correto,
    chave_errada,
    titulo_errado,
):
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            ids.append(
                await _inserir_diploma(
                    db,
                    chave=chave_errada,
                    titulo=titulo_errado,
                    conteudo=f"Art. {numero}. Dispositivo homônimo do diploma errado.",
                )
            )
            id_correto = await _inserir_diploma(
                db,
                chave=chave_correta,
                titulo=titulo_correto,
                conteudo=f"Art. {numero}. Texto vigente do diploma correto.",
            )
            ids.append(id_correto)
            await db.commit()

            citacao = await _verificar(db, texto_citacao)

            assert citacao["status"] == "verificada"
            assert citacao["encontrada"] is True
            assert citacao["fonte_chave_origem"] == chave_correta
            assert citacao["fonte_titulo"] == titulo_correto
            assert citacao["fonte_doc_id"] == id_correto
            assert citacao["fonte_versao"] == 1
            assert citacao["fonte_vigente"] is True
            assert citacao["fonte_chave_origem"] != chave_errada
        finally:
            await _limpar(db, ids)


async def test_artigo_existente_apenas_em_outro_diploma_nao_recebe_selo_positivo():
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cp",
                    titulo="Código Penal (DL 2.848/1940)",
                    conteudo="Art. 300. Dispositivo existente somente no diploma errado.",
                )
            )
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cpc",
                    titulo="Código de Processo Civil (Lei 13.105/2015)",
                    conteudo="Art. 301. Outro dispositivo, sem o artigo citado.",
                )
            )
            await db.commit()

            citacao = await _verificar(
                db,
                "Tutela de urgência conforme o art. 300 do CPC.",
            )

            assert citacao["status"] != "verificada"
            assert citacao["encontrada"] is False
            assert citacao["fonte_chave_origem"] is None
        finally:
            await _limpar(db, ids)


async def test_lei_por_numero_normalizado_exige_numero_exato():
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:l18078",
                    titulo="Lei Experimental (Lei 18.078/2020)",
                    conteudo="Art. 6º. Diploma de número apenas parcialmente parecido.",
                )
            )
            id_cdc = await _inserir_diploma(
                db,
                chave="planalto:cdc",
                titulo="Código de Defesa do Consumidor (Lei 8.078/1990)",
                conteudo="Art. 6º. Direitos básicos do consumidor.",
            )
            ids.append(id_cdc)
            await db.commit()

            citacao = await _verificar(
                db,
                "Aplicação do art. 6º da Lei nº 8.078/90.",
            )

            assert citacao["status"] == "verificada"
            assert citacao["fonte_chave_origem"] == "planalto:cdc"
            assert citacao["fonte_doc_id"] == id_cdc
            assert "18.078" not in citacao["fonte_titulo"]
        finally:
            await _limpar(db, ids)


async def test_versao_superada_mantem_o_mesmo_recorte_de_diploma():
    from app.core.database import AsyncSessionLocal

    ids: list[str] = []
    async with AsyncSessionLocal() as db:
        try:
            id_cc = await _inserir_diploma(
                db,
                chave="planalto:cc",
                titulo="Código Civil (Lei 10.406/2002)",
                conteudo="Art. 927. Versão histórica do dispositivo.",
                vigente=False,
                versao=2,
            )
            ids.append(id_cc)
            ids.append(
                await _inserir_diploma(
                    db,
                    chave="planalto:cpc",
                    titulo="Código de Processo Civil (Lei 13.105/2015)",
                    conteudo="Art. 927. Dispositivo vigente de outro diploma.",
                )
            )
            await db.commit()

            citacao = await _verificar(
                db,
                "Responsabilidade civil fundada no art. 927 do CC.",
            )

            assert citacao["status"] == "possivelmente_desatualizada"
            assert citacao["encontrada"] is False
            assert citacao["fonte_chave_origem"] == "planalto:cc"
            assert citacao["fonte_doc_id"] == id_cc
            assert citacao["fonte_versao"] == 2
            assert citacao["fonte_vigente"] is False
        finally:
            await _limpar(db, ids)
