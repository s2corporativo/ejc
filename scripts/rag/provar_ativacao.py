#!/usr/bin/env python3
"""Provas sem PII para ativação controlada dos embeddings do RAG.

Este programa é enviado por STDIN ao Python do container de produção. Ele não
imprime conteúdo de documentos, identificadores, DSN ou segredos: somente
estado de configuração, dimensões e contagens agregadas.

Modos:
  preflight  valida banco/modelo e gera um vetor antes de qualquer mutação;
  canary     reembeda uma quantidade limitada de documentos vigentes;
  proof      comprova configuração efetiva e continuidade da reindexação.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import text

EXPECTED_PROVIDER = "local"
EXPECTED_MODEL = "intfloat/multilingual-e5-large"
EXPECTED_DIM = 1024


def _emit(fase: str, dados: dict[str, Any], problemas: list[str]) -> int:
    payload = {
        "fase": fase,
        "ok": not problemas,
        **dados,
        "problemas": problemas,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not problemas else 1


async def _db_metrics() -> dict[str, int | None]:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text(
                    "SELECT a.atttypmod FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "WHERE c.relname = 'knowledge_chunks' "
                    "AND a.attname = 'embedding'"
                )
            )
        ).first()
        total = int(
            (await db.execute(text("SELECT COUNT(*) FROM knowledge_chunks"))).scalar_one()
        )
        embedded = int(
            (
                await db.execute(
                    text(
                        "SELECT COUNT(*) FROM knowledge_chunks "
                        "WHERE embedding IS NOT NULL"
                    )
                )
            ).scalar_one()
        )
        pending = int(
            (
                await db.execute(
                    text(
                        "SELECT COUNT(*) "
                        "FROM knowledge_chunks kc "
                        "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
                        "WHERE kc.embedding IS NULL "
                        "AND kd.deleted_at IS NULL AND kd.vigente = true"
                    )
                )
            ).scalar_one()
        )
    return {
        "embedding_dim_coluna": int(row[0]) if row and row[0] else None,
        "knowledge_chunks_total": total,
        "knowledge_chunks_com_embedding": embedded,
        "knowledge_chunks_vigentes_pendentes": pending,
    }


def _config_metrics() -> tuple[dict[str, Any], list[str]]:
    from app.core.config import get_settings
    from app.services import embedding_service as emb

    settings = get_settings()
    model_ok, model_detail = emb.validar_modelo_local()
    data: dict[str, Any] = {
        "EMBEDDINGS_ENABLED": bool(settings.EMBEDDINGS_ENABLED),
        "EMBEDDINGS_PROVIDER": emb._provider(),
        "EMBEDDINGS_MODEL": emb.MODEL_NAME,
        "embedding_dim_configurada": emb.EMBED_DIM,
        "modelo_valido": bool(model_ok),
        "modelo_detalhe": model_detail,
        "embeddings_disponivel": bool(emb.disponivel()),
        "ENABLE_SCHEDULER": bool(settings.ENABLE_SCHEDULER),
        "RAG_AUTO_REEMBED_ENABLED": bool(settings.RAG_AUTO_REEMBED_ENABLED),
    }
    problems: list[str] = []
    if data["EMBEDDINGS_PROVIDER"] != EXPECTED_PROVIDER:
        problems.append(
            f"provider deve ser {EXPECTED_PROVIDER}, recebido "
            f"{data['EMBEDDINGS_PROVIDER']}"
        )
    if data["EMBEDDINGS_MODEL"] != EXPECTED_MODEL:
        problems.append(
            f"modelo deve ser {EXPECTED_MODEL}, recebido {data['EMBEDDINGS_MODEL']}"
        )
    if data["embedding_dim_configurada"] != EXPECTED_DIM:
        problems.append(
            f"EMBEDDINGS_DIM deve ser {EXPECTED_DIM}, recebido "
            f"{data['embedding_dim_configurada']}"
        )
    if not data["modelo_valido"]:
        problems.append(f"modelo inválido: {model_detail}")
    if not data["embeddings_disponivel"]:
        problems.append("embedding_service.disponivel() retornou false")
    return data, problems


async def _probe_vector() -> tuple[bool, int | None]:
    from app.services.embedding_service import gerar_embeddings

    vectors = await gerar_embeddings(
        ["consulta canário de ativação sem dados pessoais"],
        modo="query",
    )
    if not vectors or len(vectors) != 1:
        return False, None
    dimension = len(vectors[0])
    return dimension == EXPECTED_DIM, dimension


async def preflight() -> int:
    data, problems = _config_metrics()
    try:
        data.update(await _db_metrics())
    except Exception as exc:
        problems.append(f"sonda do banco falhou: {type(exc).__name__}")

    if data.get("embedding_dim_coluna") != EXPECTED_DIM:
        problems.append(
            f"coluna deve ser vector({EXPECTED_DIM}), recebida "
            f"vector({data.get('embedding_dim_coluna')})"
        )

    try:
        vector_ok, vector_dim = await _probe_vector()
        data["probe_vetor_ok"] = vector_ok
        data["probe_vetor_dim"] = vector_dim
        if not vector_ok:
            problems.append("provider não gerou exatamente um vetor de 1024 dimensões")
    except Exception as exc:
        data["probe_vetor_ok"] = False
        data["probe_vetor_dim"] = None
        problems.append(f"probe do provider falhou: {type(exc).__name__}")

    return _emit("preflight", data, problems)


async def canary(max_docs: int) -> int:
    from app.core.database import AsyncSessionLocal
    from scripts.reembedar_chunks_orfaos import _reembedar_doc

    data, problems = _config_metrics()
    data["max_docs"] = max_docs
    if not data["EMBEDDINGS_ENABLED"]:
        problems.append("EMBEDDINGS_ENABLED ainda não está efetivamente ligado")
        return _emit("canary", data, problems)

    async with AsyncSessionLocal() as db:
        docs = (
            await db.execute(
                text(
                    "SELECT DISTINCT kd.id "
                    "FROM knowledge_docs kd "
                    "JOIN knowledge_chunks kc ON kc.doc_id = kd.id "
                    "WHERE kd.deleted_at IS NULL AND kd.vigente = true "
                    "AND kc.embedding IS NULL "
                    "ORDER BY kd.id LIMIT :limit"
                ),
                {"limit": max_docs},
            )
        ).scalars().all()

    processed = succeeded = failed = 0
    for doc_id in docs:
        processed += 1
        try:
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    result = await _reembedar_doc(db, doc_id, False)
            if result == "ok":
                succeeded += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            problems.append(f"reindexação canário falhou: {type(exc).__name__}")
            break

    data.update(
        {
            "documentos_processados": processed,
            "documentos_ok": succeeded,
            "documentos_com_erro": failed,
        }
    )
    try:
        data.update(await _db_metrics())
    except Exception as exc:
        problems.append(f"sonda pós-canário falhou: {type(exc).__name__}")
    if failed:
        problems.append("um ou mais documentos falharam no canário")
    return _emit("canary", data, problems)


async def proof() -> int:
    data, problems = _config_metrics()
    if not data["EMBEDDINGS_ENABLED"]:
        problems.append("EMBEDDINGS_ENABLED não está efetivamente ligado")

    try:
        data.update(await _db_metrics())
    except Exception as exc:
        problems.append(f"sonda do banco falhou: {type(exc).__name__}")

    if data.get("embedding_dim_coluna") != EXPECTED_DIM:
        problems.append(
            f"coluna deve ser vector({EXPECTED_DIM}), recebida "
            f"vector({data.get('embedding_dim_coluna')})"
        )
    total = int(data.get("knowledge_chunks_total") or 0)
    embedded = int(data.get("knowledge_chunks_com_embedding") or 0)
    pending = int(data.get("knowledge_chunks_vigentes_pendentes") or 0)
    data["cobertura_percentual"] = (
        round(embedded * 100 / total, 4) if total else 100.0
    )
    if total and not embedded:
        problems.append("o corpus existe, mas nenhum chunk possui embedding")
    if pending and not (
        data["ENABLE_SCHEDULER"] and data["RAG_AUTO_REEMBED_ENABLED"]
    ):
        problems.append(
            "há chunks vigentes pendentes, mas o scheduler de reindexação "
            "automática não está efetivamente ligado"
        )

    try:
        vector_ok, vector_dim = await _probe_vector()
        data["probe_consulta_ok"] = vector_ok
        data["probe_consulta_dim"] = vector_dim
        if not vector_ok:
            problems.append("probe final de consulta não produziu vetor 1024d")
    except Exception as exc:
        data["probe_consulta_ok"] = False
        data["probe_consulta_dim"] = None
        problems.append(f"probe final falhou: {type(exc).__name__}")

    return _emit("proof", data, problems)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("preflight")
    canary_parser = subparsers.add_parser("canary")
    canary_parser.add_argument("--max-docs", type=int, default=5)
    subparsers.add_parser("proof")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.mode == "canary":
        if not 1 <= args.max_docs <= 50:
            raise SystemExit("--max-docs deve ficar entre 1 e 50")
        return asyncio.run(canary(args.max_docs))
    if args.mode == "preflight":
        return asyncio.run(preflight())
    return asyncio.run(proof())


if __name__ == "__main__":
    raise SystemExit(main())
