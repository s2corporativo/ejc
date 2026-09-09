"""Isolamento do RAG por cliente — validação ROW-LEVEL contra Postgres real.

Este é o teste que fecha o Bloco 5: prova, com dados reais no banco, que a
busca RAG só recupera conteúdo RESTRITO (precedente_interno) do PRÓPRIO cliente
do escopo, nunca de outro. Complementa test_rag_isolation.py (que valida filtro
+ plumbing sem banco).

Requer Postgres com pg_trgm + pgvector e as migrations aplicadas. Roda só quando
RUN_DB_TESTS=1 (setado no job de CI `db-validation`); caso contrário, pula — não
tenta conectar em ambiente sem banco (nem em produção).

Determinístico: usa o caminho TEXTUAL (ILIKE) do buscar_contexto_rag — com
embeddings desligados pela fixture — então dois docs com o mesmo termo mas client_id
diferentes são diferenciados APENAS pelo filtro de escopo. Sem tuning de
similaridade semântica.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requer Postgres+pgvector com migrations (defina RUN_DB_TESTS=1)",
)

_TERMO = "usucapiaoextraordinariavintenaria"  # termo distintivo, casa ILIKE nos dois


@pytest.fixture(autouse=True)
async def _dispose_engine_apos_teste(monkeypatch):
    """pytest-asyncio (asyncio_mode=auto) cria um event loop novo POR FUNÇÃO de
    teste, mas app.core.database.engine é um singleton global cujo pool guarda
    conexões asyncpg presas ao loop em que foram abertas. Sem dispose explícito
    NESTE loop, o teste seguinte roda noutro loop e o garbage collector tenta
    fechar as conexões do teste anterior no loop errado — "Event loop is closed".
    Descartar o pool aqui, ainda dentro do loop que o usou, evita o problema."""
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service, "disponivel", lambda: False)
    yield
    from app.core.database import engine
    await engine.dispose()


async def _inserir_precedente(db, doc_id, client_id, titulo):
    await db.execute(
        text(
            "INSERT INTO knowledge_docs "
            "(id, titulo, categoria, client_id, status_indexacao, extra) "
            "VALUES (:id, :tit, 'precedente_interno', :cli, 'indexado', "
            "'{\"rag_status\":\"aprovado\"}'::jsonb)"
        ),
        {"id": doc_id, "tit": titulo, "cli": client_id},
    )
    await db.execute(
        text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc, 0, :cont)"
        ),
        {"id": str(uuid4()), "doc": doc_id, "cont": f"{_TERMO} caso {titulo} conteudo distintivo"},
    )


async def test_precedente_interno_isolado_por_cliente_rowlevel():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    cli_A, cli_B = str(uuid4()), str(uuid4())
    doc_A, doc_B = str(uuid4()), str(uuid4())

    async with AsyncSessionLocal() as db:
        await _inserir_precedente(db, doc_A, cli_A, "PRECEDENTE_CLIENTE_A")
        await _inserir_precedente(db, doc_B, cli_B, "PRECEDENTE_CLIENTE_B")
        await db.commit()
        try:
            def titulos(res):
                return {r["titulo"] for r in res}

            # Escopo A → só vê o precedente de A.
            resA = await buscar_contexto_rag(
                db, _TERMO, limite=5, categorias=["precedente_interno"],
                modo_or=True, scope_client_id=cli_A,
            )
            tA = titulos(resA)
            assert "PRECEDENTE_CLIENTE_A" in tA, "precedente do próprio cliente deveria aparecer"
            assert "PRECEDENTE_CLIENTE_B" not in tA, "VAZAMENTO: precedente de outro cliente apareceu"

            # Escopo B → só vê o precedente de B.
            resB = await buscar_contexto_rag(
                db, _TERMO, limite=5, categorias=["precedente_interno"],
                modo_or=True, scope_client_id=cli_B,
            )
            tB = titulos(resB)
            assert "PRECEDENTE_CLIENTE_B" in tB
            assert "PRECEDENTE_CLIENTE_A" not in tB, "VAZAMENTO: precedente de outro cliente apareceu"

            # Sem escopo (None) → fail-closed: nenhum precedente restrito.
            resN = await buscar_contexto_rag(
                db, _TERMO, limite=5, categorias=["precedente_interno"],
                modo_or=True, scope_client_id=None,
            )
            tN = titulos(resN)
            assert "PRECEDENTE_CLIENTE_A" not in tN and "PRECEDENTE_CLIENTE_B" not in tN, (
                "fail-closed quebrado: conteúdo restrito recuperado sem escopo de cliente"
            )
        finally:
            await db.execute(
                text("DELETE FROM knowledge_chunks WHERE doc_id IN (:a, :b)"),
                {"a": doc_A, "b": doc_B},
            )
            await db.execute(
                text("DELETE FROM knowledge_docs WHERE id IN (:a, :b)"),
                {"a": doc_A, "b": doc_B},
            )
            await db.commit()


async def test_conteudo_publico_sempre_visivel_rowlevel():
    """Contraprova: conteúdo PÚBLICO (não restrito) aparece independentemente do
    escopo — o isolamento não pode ter quebrado a busca de legislação/súmulas."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    doc_pub = str(uuid4())
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO knowledge_docs "
                "(id, titulo, categoria, status_indexacao, extra) "
                "VALUES (:id, 'SUMULA_PUBLICA_TESTE', 'sumula_stj', 'indexado', "
                # `\:` — escapa o ":" para o text() do SQLAlchemy não ler
                # ":true" como bind param dentro do literal JSON.
                "'{\"rag_status\":\"aprovado\",\"conferido\"\\:true}'::jsonb)"
            ),
            {"id": doc_pub},
        )
        await db.execute(
            text(
                "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
                "VALUES (:id, :doc, 0, :cont)"
            ),
            {"id": str(uuid4()), "doc": doc_pub, "cont": f"{_TERMO} sumula publica de teste"},
        )
        await db.commit()
        try:
            # Mesmo sem escopo de cliente, público aparece.
            res = await buscar_contexto_rag(db, _TERMO, limite=5, modo_or=True, scope_client_id=None)
            assert "SUMULA_PUBLICA_TESTE" in {r["titulo"] for r in res}
        finally:
            await db.execute(text("DELETE FROM knowledge_chunks WHERE doc_id = :d"), {"d": doc_pub})
            await db.execute(text("DELETE FROM knowledge_docs WHERE id = :d"), {"d": doc_pub})
            await db.commit()


async def _inserir_doc_escopo(
    db,
    *,
    doc_id: str,
    titulo: str,
    categoria: str,
    client_id: str | None = None,
    case_id: str | None = None,
    base_rag: str = "publica",
):
    """Cria fixture RAG mínima; permite representar legado inconsistente."""
    await db.execute(
        text(
            "INSERT INTO knowledge_docs "
            "(id, titulo, categoria, client_id, case_id, status_indexacao, extra) "
            "VALUES (:id, :tit, :cat, :cli, :caso, 'indexado', "
            "'{\"rag_status\":\"aprovado\"}'::jsonb)"
        ),
        {"id": doc_id, "tit": titulo, "cat": categoria,
         "cli": client_id, "caso": case_id},
    )
    if base_rag != "publica":
        if base_rag not in {"escritorio", "caso"}:
            raise AssertionError("base_rag de teste inválida")
        # Literal controlado pelo próprio teste; evita depender do nome do enum PG.
        await db.execute(
            text(f"UPDATE knowledge_docs SET base_rag = '{base_rag}' WHERE id = :id"),
            {"id": doc_id},
        )
    await db.execute(
        text(
            "INSERT INTO knowledge_chunks (id, doc_id, chunk_index, conteudo) "
            "VALUES (:id, :doc, 0, :cont)"
        ),
        {"id": str(uuid4()), "doc": doc_id,
         "cont": f"{_TERMO} {titulo} escopo ownership"},
    )


async def _limpar_docs_escopo(db, ids: list[str]):
    for doc_id in ids:
        await db.execute(text("DELETE FROM knowledge_chunks WHERE doc_id = :d"), {"d": doc_id})
        await db.execute(text("DELETE FROM knowledge_docs WHERE id = :d"), {"d": doc_id})
    await db.commit()


async def test_categoria_nova_com_client_id_continua_privada_rowlevel():
    """Categoria desconhecida não pode transformar ownership em conteúdo global."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    cli_a, cli_b, doc = str(uuid4()), str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_doc_escopo(
            db, doc_id=doc, titulo="CATEGORIA_NOVA_CLIENTE_A",
            categoria="categoria_privada_nova", client_id=cli_a,
        )
        await db.commit()
        try:
            sem = await buscar_contexto_rag(db, _TERMO, limite=10, modo_or=True)
            outro = await buscar_contexto_rag(
                db, _TERMO, limite=10, modo_or=True, scope_client_id=cli_b,
            )
            proprio = await buscar_contexto_rag(
                db, _TERMO, limite=10, modo_or=True, scope_client_id=cli_a,
            )
            assert "CATEGORIA_NOVA_CLIENTE_A" not in {r["titulo"] for r in sem}
            assert "CATEGORIA_NOVA_CLIENTE_A" not in {r["titulo"] for r in outro}
            assert "CATEGORIA_NOVA_CLIENTE_A" in {r["titulo"] for r in proprio}
        finally:
            await _limpar_docs_escopo(db, [doc])


async def test_case_id_exige_cliente_e_caso_exatos_rowlevel():
    """Mesmo cliente não pode recuperar documento pertencente a outro caso."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    cli, caso_x, caso_y = str(uuid4()), str(uuid4()), str(uuid4())
    doc_x, doc_y = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_doc_escopo(
            db, doc_id=doc_x, titulo="DOC_CASO_X", categoria="categoria_privada_nova",
            client_id=cli, case_id=caso_x,
        )
        await _inserir_doc_escopo(
            db, doc_id=doc_y, titulo="DOC_CASO_Y", categoria="categoria_privada_nova",
            client_id=cli, case_id=caso_y,
        )
        await db.commit()
        try:
            res_x = await buscar_contexto_rag(
                db, _TERMO, limite=10, modo_or=True,
                scope_client_id=cli, scope_case_id=caso_x,
            )
            tit_x = {r["titulo"] for r in res_x}
            assert "DOC_CASO_X" in tit_x
            assert "DOC_CASO_Y" not in tit_x

            sem_caso = await buscar_contexto_rag(
                db, _TERMO, limite=10, modo_or=True, scope_client_id=cli,
            )
            tit_sem = {r["titulo"] for r in sem_caso}
            assert "DOC_CASO_X" not in tit_sem
            assert "DOC_CASO_Y" not in tit_sem
        finally:
            await _limpar_docs_escopo(db, [doc_x, doc_y])


async def test_base_rag_caso_sem_ids_falha_fechado_rowlevel():
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    doc = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_doc_escopo(
            db, doc_id=doc, titulo="CASO_SEM_OWNERSHIP",
            categoria="categoria_privada_nova", base_rag="caso",
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, _TERMO, limite=10, modo_or=True)
            res_scope = await buscar_contexto_rag(
                db, _TERMO, limite=10, modo_or=True,
                scope_client_id=str(uuid4()), scope_case_id=str(uuid4()),
            )
            assert "CASO_SEM_OWNERSHIP" not in {r["titulo"] for r in res}
            assert "CASO_SEM_OWNERSHIP" not in {r["titulo"] for r in res_scope}
        finally:
            await _limpar_docs_escopo(db, [doc])


async def test_categoria_legada_restrita_sem_ids_permanece_invisivel_rowlevel():
    """Preserva fail-closed do legado peca_escritorio malclassificado como público."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    doc = str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_doc_escopo(
            db, doc_id=doc, titulo="LEGADO_RESTRITO_SEM_IDS",
            categoria="peca_escritorio",
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(db, _TERMO, limite=10, modo_or=True)
            res_scope = await buscar_contexto_rag(
                db, _TERMO, limite=10, modo_or=True,
                scope_client_id=str(uuid4()),
            )
            assert "LEGADO_RESTRITO_SEM_IDS" not in {r["titulo"] for r in res}
            assert "LEGADO_RESTRITO_SEM_IDS" not in {r["titulo"] for r in res_scope}
        finally:
            await _limpar_docs_escopo(db, [doc])



async def test_base_rag_caso_com_cliente_sem_case_id_falha_fechado_rowlevel():
    """base_rag=caso precisa do par client+case; client sozinho não basta."""
    from app.core.database import AsyncSessionLocal
    from app.services.ai_service import buscar_contexto_rag

    cli, doc = str(uuid4()), str(uuid4())
    async with AsyncSessionLocal() as db:
        await _inserir_doc_escopo(
            db, doc_id=doc, titulo="CASO_COM_CLIENTE_SEM_CASE",
            categoria="categoria_privada_nova", client_id=cli, base_rag="caso",
        )
        await db.commit()
        try:
            res = await buscar_contexto_rag(
                db, _TERMO, limite=10, modo_or=True, scope_client_id=cli,
            )
            assert "CASO_COM_CLIENTE_SEM_CASE" not in {r["titulo"] for r in res}
        finally:
            await _limpar_docs_escopo(db, [doc])


def _carregar_probe_ativacao():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "scripts" / "rag" / "provar_ativacao.py"
    spec = importlib.util.spec_from_file_location("ejc_provar_ativacao_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


async def test_canary_1_prioriza_documento_de_caso_pendente_rowlevel():
    """Se há pendência privada, `canary 1` precisa exercitar o caso, não só público."""
    from app.core.database import AsyncSessionLocal

    cli, caso = str(uuid4()), str(uuid4())
    ids = [str(uuid4()) for _ in range(3)]
    async with AsyncSessionLocal() as db:
        await _inserir_doc_escopo(
            db, doc_id=ids[0], titulo="CANARIO_PUBLICO",
            categoria="categoria_publica_teste",
        )
        await _inserir_doc_escopo(
            db, doc_id=ids[1], titulo="CANARIO_CLIENTE",
            categoria="categoria_privada_nova", client_id=cli,
        )
        await _inserir_doc_escopo(
            db, doc_id=ids[2], titulo="CANARIO_CASO",
            categoria="categoria_privada_nova", client_id=cli,
            case_id=caso, base_rag="caso",
        )
        await db.commit()
        try:
            mod = _carregar_probe_ativacao()
            async with db.begin():
                docs = await mod._select_canary_docs(db, 1)
                assert len(docs) == 1
                assert docs[0].id == ids[2]
                assert docs[0].client_id == cli
                assert docs[0].case_id == caso
        finally:
            await _limpar_docs_escopo(db, ids)


async def test_probe_semantico_exercita_publico_cliente_e_caso_rowlevel():
    """O probe deve recuperar cada classe pelo próprio ownership persistido."""
    from app.core.database import AsyncSessionLocal

    cli, caso = str(uuid4()), str(uuid4())
    ids = [str(uuid4()) for _ in range(3)]
    async with AsyncSessionLocal() as db:
        await _inserir_doc_escopo(
            db, doc_id=ids[0], titulo="PROBE_PUBLICO",
            categoria="categoria_publica_teste",
        )
        await _inserir_doc_escopo(
            db, doc_id=ids[1], titulo="PROBE_CLIENTE",
            categoria="categoria_privada_nova", client_id=cli,
        )
        await _inserir_doc_escopo(
            db, doc_id=ids[2], titulo="PROBE_CASO",
            categoria="categoria_privada_nova", client_id=cli,
            case_id=caso, base_rag="caso",
        )
        # Vetor sintético 1024d; o probe usa o próprio vetor do chunk, distância 0.
        vec = "[" + ",".join(["1"] + ["0"] * 1023) + "]"
        for doc_id in ids:
            await db.execute(
                text("UPDATE knowledge_chunks SET embedding = CAST(:v AS vector(1024)) WHERE doc_id = :d"),
                {"v": vec, "d": doc_id},
            )
        await db.commit()
        try:
            mod = _carregar_probe_ativacao()
            assert await mod._probe_semantic_search() is True
        finally:
            await _limpar_docs_escopo(db, ids)
