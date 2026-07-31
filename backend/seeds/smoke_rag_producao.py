#!/usr/bin/env python3
"""
smoke_rag_producao.py — Teste de fumaça da busca RAG em Postgres REAL (pós-deploy).

Valida, contra o banco de produção/staging, o que o SQLite de teste não consegue
exercitar (operadores ILIKE e ANY do PostgreSQL, e o operador <=> do pgvector):

  1. Conexão e extensão pgvector ativa.
  2. Busca TEXTUAL com filtro de categoria (= ANY(:cats)).
  3. Busca SEMÂNTICA via pgvector (<=>), se EMBEDDINGS_ENABLED=true.
  4. Recuperação de precedentes internos (categoria precedente_interno).

Uso (dentro do container backend):
    python seeds/smoke_rag_producao.py

NÃO escreve dados — apenas lê. Seguro rodar em produção.
Saída: relatório com PASS/FALHA por verificação. Código de saída != 0 se algo falhar.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text                      # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.ai_service import buscar_contexto_rag  # noqa: E402
from app.services.embedding_service import disponivel     # noqa: E402

FALHAS = 0


def chk(cond: bool, ok: str, fail: str):
    global FALHAS
    if cond:
        print(f"  ✅ {ok}")
    else:
        print(f"  ❌ {fail}")
        FALHAS += 1


async def main():
    print("═══ SMOKE TEST RAG — PostgreSQL real ═══\n")

    async with AsyncSessionLocal() as db:
        # 1. pgvector ativo
        print("[1] Extensão pgvector")
        try:
            r = (await db.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )).scalar()
            chk(r == 1, "Extensão 'vector' instalada",
                "Extensão pgvector AUSENTE — rode: CREATE EXTENSION vector;")
        except Exception as e:
            chk(False, "", f"Falha ao consultar pg_extension: {e}")

        # 2. Contagem de base de conhecimento
        print("\n[2] Base de conhecimento")
        try:
            docs = (await db.execute(
                text("SELECT COUNT(*) FROM knowledge_docs WHERE deleted_at IS NULL")
            )).scalar()
            chunks = (await db.execute(
                text("SELECT COUNT(*) FROM knowledge_chunks")
            )).scalar()
            com_vetor = (await db.execute(
                text("SELECT COUNT(*) FROM knowledge_chunks WHERE embedding IS NOT NULL")
            )).scalar()
            print(f"     docs={docs} · chunks={chunks} · com_embedding={com_vetor}")
            chk(docs > 0, f"{docs} documentos na base",
                "Base VAZIA — rode seeds/seed_all.py e a ingestão de fontes")
        except Exception as e:
            chk(False, "", f"Falha ao contar base: {e}")

        # 3. Busca textual com filtro de categoria (exercita ILIKE + ANY)
        print("\n[3] Busca textual + filtro de categoria (ILIKE + ANY)")
        try:
            res = await buscar_contexto_rag(
                db, "prazo recurso", limite=3, categorias=["legislacao", "jurisprudencia"]
            )
            chk(isinstance(res, list),
                f"Filtro de categoria executou (retornou {len(res)} resultado(s))",
                "Filtro de categoria FALHOU — verifique sintaxe ANY/ILIKE")
        except Exception as e:
            chk(False, "", f"Busca textual com categoria FALHOU: {e}")

        # 4. Busca semântica (pgvector <=>), se habilitada
        print("\n[4] Busca semântica (pgvector <=>)")
        if disponivel():
            try:
                res = await buscar_contexto_rag(db, "responsabilidade civil dano moral", limite=3)
                tem_score = bool(res) and "score" in res[0]
                chk(tem_score or len(res) == 0,
                    f"Busca vetorial executou ({len(res)} resultado(s), score presente)",
                    "Busca vetorial não retornou score — operador <=> pode ter falhado")
            except Exception as e:
                chk(False, "", f"Busca vetorial FALHOU: {e}")
        else:
            print("  ⚠️  EMBEDDINGS_ENABLED=false ou sentence-transformers ausente "
                  "— busca semântica desligada (fallback textual ativo).")

        # 5. Precedentes internos
        print("\n[5] Precedentes internos (precedente_interno)")
        try:
            prec = (await db.execute(text(
                "SELECT COUNT(*) FROM knowledge_docs "
                "WHERE categoria = 'precedente_interno' AND deleted_at IS NULL"
            ))).scalar()
            print(f"     {prec} precedente(s) interno(s) registrado(s)")
            res = await buscar_contexto_rag(
                db, "adimplemento substancial", limite=3,
                categorias=["precedente_interno"], modo_or=True
            )
            chk(isinstance(res, list),
                f"Recuperação de precedentes executou ({len(res)} resultado(s))",
                "Recuperação de precedentes FALHOU")
        except Exception as e:
            chk(False, "", f"Consulta de precedentes FALHOU: {e}")

    print("\n" + "═" * 40)
    if FALHAS == 0:
        print("✅ SMOKE TEST OK — RAG operacional em produção")
        sys.exit(0)
    else:
        print(f"❌ {FALHAS} verificação(ões) falharam — investigar antes de liberar")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
