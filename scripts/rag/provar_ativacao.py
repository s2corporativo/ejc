#!/usr/bin/env python3
"""Provas agregadas, sem PII, para ativação controlada do RAG semântico.

O programa é enviado por STDIN ao Python dos containers. Nenhum conteúdo,
identificador de documento, DSN, segredo ou exceção bruta é emitido.

Modos:
  runtime   valida a configuração efetiva do processo, sem baixar pesos;
  preflight valida provider, banco e vetor real antes da mutação do .env;
  canary    reembeda no máximo N documentos elegíveis pela governança;
  proof     comprova configuração, pgvector, recuperação governada e continuidade.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
from typing import Any

from sqlalchemy import text

EXPECTED_PROVIDER = "local"
EXPECTED_MODEL = "intfloat/multilingual-e5-large"
EXPECTED_DIM = 1024
_COLUMN_RE = re.compile(r"^vector\((\d+)\)$")


def _emit(fase: str, dados: dict[str, Any], problemas: list[str]) -> int:
    payload = {"fase": fase, "ok": not problemas, **dados, "problemas": problemas}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not problemas else 1


def _exception_code(exc: BaseException) -> str:
    return type(exc).__name__


def _config_metrics() -> tuple[dict[str, Any], list[str]]:
    from app.core.config import get_settings
    from app.services import embedding_service as emb

    settings = get_settings()
    model_ok, _ = emb.validar_modelo_local()
    provider = emb._provider()
    data: dict[str, Any] = {
        "EMBEDDINGS_ENABLED": bool(settings.EMBEDDINGS_ENABLED),
        "EMBEDDINGS_PROVIDER": provider,
        "EMBEDDINGS_MODEL": emb.MODEL_NAME,
        "embedding_dim_configurada": emb.EMBED_DIM,
        "modelo_valido": bool(model_ok),
        "embeddings_disponivel": bool(emb.disponivel()),
        "ENABLE_SCHEDULER": bool(settings.ENABLE_SCHEDULER),
        "RAG_AUTO_REEMBED_ENABLED": bool(settings.RAG_AUTO_REEMBED_ENABLED),
    }
    problems: list[str] = []
    if provider != EXPECTED_PROVIDER:
        problems.append("provider de embeddings não é o provider local homologado")
    if emb.MODEL_NAME != EXPECTED_MODEL:
        problems.append("modelo de embeddings diverge do modelo homologado")
    if emb.EMBED_DIM != EXPECTED_DIM:
        problems.append("dimensão configurada diverge de 1024")
    if not model_ok:
        problems.append("modelo não é suportado pelo fastembed pinado")
    return data, problems


def _governance_contract(
    scope_client_id: str | None = None,
    scope_case_id: str | None = None,
) -> tuple[str, str, dict[str, object]]:
    """Retorna os mesmos gates e binds usados pela recuperação real do EJC."""
    from app.services import ai_service as ai

    return (
        ai._filtros_gate_rag(False),
        ai._FILTRO_ESCOPO_RAG,
        ai._params_escopo_rag(scope_client_id, scope_case_id),
    )


async def _db_metrics() -> dict[str, Any]:
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service as ai

    gate_sql, scope_sql, scope_params = _governance_contract()
    async with AsyncSessionLocal() as db:
        column_type = (
            await db.execute(
                text(
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = current_schema() "
                    "AND c.relname = 'knowledge_chunks' "
                    "AND a.attname = 'embedding' "
                    "AND a.attnum > 0 AND NOT a.attisdropped"
                )
            )
        ).scalar_one_or_none()
        active = (
            await db.execute(
                text(
                    "SELECT "
                    "COUNT(*) AS total, "
                    "COUNT(*) FILTER (WHERE kc.embedding IS NOT NULL) AS embedded, "
                    "COUNT(*) FILTER (WHERE kc.embedding IS NULL) AS pending "
                    "FROM knowledge_chunks kc "
                    "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
                    "WHERE kd.deleted_at IS NULL AND kd.vigente = true"
                )
            )
        ).one()
        governed = (
            await db.execute(
                # SQL literal com bind params; a regra marca todo text(), sem olhar
                # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                text(
                    "SELECT "
                    "COUNT(*) AS total, "
                    "COUNT(*) FILTER (WHERE kc.embedding IS NOT NULL) AS embedded, "
                    "COUNT(*) FILTER (WHERE kc.embedding IS NULL) AS pending "
                    "FROM knowledge_chunks kc "
                    "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
                    "WHERE kd.deleted_at IS NULL "
                    "AND (kd.vigente = TRUE OR :incl_hist) "
                    f"{scope_sql} "
                    f"{gate_sql}"
                ),
                {"incl_hist": False, **scope_params},
            )
        ).one()

    column_text = str(column_type) if column_type is not None else None
    match = _COLUMN_RE.fullmatch(column_text or "")
    return {
        "embedding_tipo_coluna": column_text,
        "embedding_dim_coluna": int(match.group(1)) if match else None,
        "knowledge_chunks_vigentes_total": int(active.total or 0),
        "knowledge_chunks_vigentes_com_embedding": int(active.embedded or 0),
        "knowledge_chunks_vigentes_pendentes": int(active.pending or 0),
        "knowledge_chunks_governados_total": int(governed.total or 0),
        "knowledge_chunks_governados_com_embedding": int(governed.embedded or 0),
        "knowledge_chunks_governados_pendentes": int(governed.pending or 0),
        "governanca_recuperacao_espelhada": True,
        "rag_max_dist": float(ai._rag_max_dist()),
    }


async def _probe_vector() -> list[float]:
    from app.services.embedding_service import gerar_embeddings

    vectors = await gerar_embeddings(
        ["consulta canário de ativação sem dados pessoais"], modo="query"
    )
    if not vectors or len(vectors) != 1 or len(vectors[0]) != EXPECTED_DIM:
        raise RuntimeError("invalid_vector_shape")
    vector = [float(value) for value in vectors[0]]
    if any(not math.isfinite(value) for value in vector):
        raise RuntimeError("non_finite_vector")
    return vector


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


async def _probe_pgvector(vector: list[float]) -> bool:
    from app.core.database import AsyncSessionLocal

    literal = _vector_literal(vector)
    async with AsyncSessionLocal() as db:
        distance = (
            await db.execute(
                text(
                    "SELECT CAST(:vector AS vector(1024)) "
                    "<=> CAST(:vector AS vector(1024))"
                ),
                {"vector": literal},
            )
        ).scalar_one()
    return abs(float(distance)) < 1e-9


async def _probe_semantic_search() -> bool:
    """Exercita os mesmos gates da recuperação real, sem emitir conteúdo/IDs.

    Primeiro escolhe internamente um chunk já elegível e usa o próprio vetor
    como consulta controlada. Em seguida repete escopo, vigência, aprovação,
    quarentena, exclusão de fictícios e limiar máximo de distância usados por
    ``buscar_contexto_rag``. A distância do próprio vetor é zero, portanto uma
    falha significa que o caminho governado não está recuperando o corpus.
    """
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service as ai

    gate_sql, scope_sql, scope_params = _governance_contract()
    async with AsyncSessionLocal() as db:
        seed = (
            await db.execute(
                # SQL literal com bind params; a regra marca todo text(), sem olhar
                # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                text(
                    "SELECT kc.embedding::text AS vector_text "
                    "FROM knowledge_chunks kc "
                    "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
                    "WHERE kd.deleted_at IS NULL "
                    "AND kc.embedding IS NOT NULL "
                    "AND (kd.vigente = TRUE OR :incl_hist) "
                    f"{scope_sql} "
                    f"{gate_sql} "
                    "ORDER BY kc.id LIMIT 1"
                ),
                {"incl_hist": False, **scope_params},
            )
        ).first()
        if seed is None:
            return False

        row = (
            await db.execute(
                # SQL literal com bind params; a regra marca todo text(), sem olhar
                # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                text(
                    "SELECT 1 "
                    "FROM knowledge_chunks kc "
                    "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
                    "WHERE kd.deleted_at IS NULL "
                    "AND kc.embedding IS NOT NULL "
                    "AND (kc.embedding <=> CAST(:vec AS vector(1024))) <= :max_dist "
                    f"{scope_sql} "
                    f"{ai._FILTRO_VIGENTE_RAG} "
                    f"{gate_sql} "
                    "ORDER BY kc.embedding <=> CAST(:vec AS vector(1024)) "
                    "LIMIT 1"
                ),
                {
                    "vec": seed.vector_text,
                    "max_dist": ai._rag_max_dist(),
                    "incl_hist": False,
                    **scope_params,
                },
            )
        ).first()
    return row is not None


async def runtime() -> int:
    data, problems = _config_metrics()
    return _emit("runtime", data, problems)


async def preflight() -> int:
    data, problems = _config_metrics()
    if not data["EMBEDDINGS_ENABLED"]:
        problems.append("override de preflight não habilitou embeddings no processo")

    try:
        data.update(await _db_metrics())
    except Exception as exc:
        problems.append(f"sonda do banco falhou:{_exception_code(exc)}")

    if data.get("embedding_dim_coluna") != EXPECTED_DIM:
        problems.append("coluna knowledge_chunks.embedding não é vector(1024)")

    try:
        vector = await _probe_vector()
        data["probe_vetor_ok"] = True
        data["probe_vetor_dim"] = len(vector)
        data["probe_pgvector_ok"] = await _probe_pgvector(vector)
        if not data["probe_pgvector_ok"]:
            problems.append("pgvector não aceitou o vetor canário 1024d")
    except Exception as exc:
        data["probe_vetor_ok"] = False
        data["probe_vetor_dim"] = None
        data["probe_pgvector_ok"] = False
        problems.append(f"probe vetorial falhou:{_exception_code(exc)}")

    return _emit("preflight", data, problems)


async def canary(max_docs: int) -> int:
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service as ai
    from scripts.reembedar_chunks_orfaos import _reembedar_doc

    data, problems = _config_metrics()
    data["max_docs"] = max_docs
    data["canario_governado"] = True
    if not data["EMBEDDINGS_ENABLED"]:
        problems.append("EMBEDDINGS_ENABLED não está efetivamente ligado")
        return _emit("canary", data, problems)

    try:
        before = await _db_metrics()
        data["governados_com_embedding_antes"] = before[
            "knowledge_chunks_governados_com_embedding"
        ]
        data["governados_pendentes_antes"] = before[
            "knowledge_chunks_governados_pendentes"
        ]
    except Exception as exc:
        problems.append(f"sonda pré-canário falhou:{_exception_code(exc)}")
        return _emit("canary", data, problems)

    gate_sql, scope_sql, scope_params = _governance_contract()
    processed = succeeded = failed = 0
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                docs = (
                    await db.execute(
                        # SQL literal com bind params; a regra marca todo text(), sem olhar
                        # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
                        # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                        text(
                            "SELECT kd.id "
                            "FROM knowledge_docs kd "
                            "WHERE kd.deleted_at IS NULL "
                            "AND (kd.vigente = TRUE OR :incl_hist) "
                            f"{scope_sql} "
                            f"{gate_sql} "
                            "AND EXISTS ("
                            "  SELECT 1 FROM knowledge_chunks kc "
                            "  WHERE kc.doc_id = kd.id AND kc.embedding IS NULL"
                            ") "
                            "ORDER BY kd.id "
                            "LIMIT :limit "
                            "FOR UPDATE OF kd SKIP LOCKED"
                        ),
                        {
                            "limit": max_docs,
                            "incl_hist": False,
                            **scope_params,
                        },
                    )
                ).scalars().all()

                for doc_id in docs:
                    processed += 1
                    try:
                        async with db.begin_nested():
                            result = await _reembedar_doc(db, doc_id, False)
                        if result == "ok":
                            succeeded += 1
                        else:
                            failed += 1
                    except Exception:
                        failed += 1
    except Exception as exc:
        problems.append(f"transação canário falhou:{_exception_code(exc)}")

    data.update(
        {
            "documentos_processados": processed,
            "documentos_ok": succeeded,
            "documentos_com_erro": failed,
        }
    )
    try:
        after = await _db_metrics()
        data.update(after)
        data["novos_chunks_governados_com_embedding"] = max(
            0,
            int(after["knowledge_chunks_governados_com_embedding"])
            - int(before["knowledge_chunks_governados_com_embedding"]),
        )
    except Exception as exc:
        problems.append(f"sonda pós-canário falhou:{_exception_code(exc)}")

    if processed > max_docs:
        problems.append("canário ultrapassou o limite de documentos")
    if failed:
        problems.append("um ou mais documentos falharam no canário")
    if processed and not succeeded:
        problems.append("canário não concluiu nenhum documento selecionado")
    return _emit("canary", data, problems)


async def proof(require_continuity: bool = True) -> int:
    data, problems = _config_metrics()
    data["continuidade_exigida"] = require_continuity
    if not data["EMBEDDINGS_ENABLED"]:
        problems.append("EMBEDDINGS_ENABLED não está efetivamente ligado")

    try:
        data.update(await _db_metrics())
    except Exception as exc:
        problems.append(f"sonda do banco falhou:{_exception_code(exc)}")

    if data.get("embedding_dim_coluna") != EXPECTED_DIM:
        problems.append("coluna knowledge_chunks.embedding não é vector(1024)")

    total = int(data.get("knowledge_chunks_vigentes_total") or 0)
    embedded = int(data.get("knowledge_chunks_vigentes_com_embedding") or 0)
    pending = int(data.get("knowledge_chunks_vigentes_pendentes") or 0)
    governed_total = int(data.get("knowledge_chunks_governados_total") or 0)
    governed_embedded = int(
        data.get("knowledge_chunks_governados_com_embedding") or 0
    )
    data["cobertura_vigente_percentual"] = (
        round(embedded * 100 / total, 4) if total else 100.0
    )
    data["cobertura_governada_percentual"] = (
        round(governed_embedded * 100 / governed_total, 4)
        if governed_total
        else (100.0 if total == 0 else 0.0)
    )

    if total and not embedded:
        problems.append("corpus vigente existe, mas nenhum chunk vigente foi vetorizado")
    if total and not governed_total:
        problems.append("corpus vigente existe, mas nenhum chunk é elegível pela governança")
    if governed_total and not governed_embedded:
        problems.append("corpus governado existe, mas nenhum chunk elegível foi vetorizado")
    if require_continuity and pending and not (
        data["ENABLE_SCHEDULER"] and data["RAG_AUTO_REEMBED_ENABLED"]
    ):
        problems.append(
            "há chunks vigentes pendentes sem scheduler e auto-reembed efetivos"
        )

    try:
        vector = await _probe_vector()
        data["probe_consulta_ok"] = True
        data["probe_consulta_dim"] = len(vector)
        data["probe_pgvector_ok"] = await _probe_pgvector(vector)
        if not data["probe_pgvector_ok"]:
            problems.append("pgvector não aceitou o vetor de consulta")
        if governed_embedded:
            data["probe_busca_semantica_governada_ok"] = (
                await _probe_semantic_search()
            )
            if not data["probe_busca_semantica_governada_ok"]:
                problems.append(
                    "recuperação semântica governada não retornou linha elegível"
                )
        else:
            data["probe_busca_semantica_governada_ok"] = total == 0
    except Exception as exc:
        data["probe_consulta_ok"] = False
        data["probe_consulta_dim"] = None
        data["probe_pgvector_ok"] = False
        data["probe_busca_semantica_governada_ok"] = False
        problems.append(f"probe final falhou:{_exception_code(exc)}")

    # Alias agregado mantido para consumidores/relatórios anteriores.
    data["probe_busca_semantica_ok"] = data.get(
        "probe_busca_semantica_governada_ok", False
    )
    return _emit("proof", data, problems)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("runtime")
    subparsers.add_parser("preflight")
    canary_parser = subparsers.add_parser("canary")
    canary_parser.add_argument("--max-docs", type=int, default=5)
    proof_parser = subparsers.add_parser("proof")
    proof_parser.add_argument(
        "--skip-continuity",
        action="store_true",
        help="prova o caminho governado antes de liberar o scheduler",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.mode == "runtime":
        return asyncio.run(runtime())
    if args.mode == "preflight":
        return asyncio.run(preflight())
    if args.mode == "canary":
        if not 1 <= args.max_docs <= 50:
            raise SystemExit("--max-docs deve ficar entre 1 e 50")
        return asyncio.run(canary(args.max_docs))
    return asyncio.run(proof(require_continuity=not args.skip_continuity))


if __name__ == "__main__":
    raise SystemExit(main())
