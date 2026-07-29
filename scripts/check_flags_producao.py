#!/usr/bin/env python3
"""Sonda somente-leitura das flags EFETIVAS do EJC em produção.

Enviada por STDIN ao Python do container:
    docker exec -i ejc_backend python - < scripts/check_flags_producao.py

Existe porque `.env` e realidade divergem com facilidade: valor comentado, typo,
ou default de código que mudou entre versões produzem um sistema que "parece"
configurado. A fonte de verdade é `get_settings()` DENTRO do processo — é ela
que o RAG, o gateway de IA e o citation gate consultam.

Além de ler as flags, confere o que elas PROMETEM. `EMBEDDINGS_ENABLED=true`
com dimensão de modelo diferente da coluna `knowledge_chunks.embedding` é pior
que desligado: só falha na hora da ingestão. E ligado com zero chunks vetorizados
significa RAG semanticamente inerte, sem nenhum sintoma na interface.

Saída: um único JSON. Nenhum valor de chave, senha, token ou DSN é impresso —
apenas booleanos, nome de modelo e contagens. Exit != 0 quando há problema
acionável.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

_FLAGS_BOOL = (
    "EMBEDDINGS_ENABLED",
    "CITACOES_MODO_ESTRITO",
    "AI_REQUIRE_HITL",
    "RATE_LIMIT_REDIS_ENABLED",
    "ENABLE_SCHEDULER",
)


async def _estado_do_banco(resultado: dict[str, Any]) -> None:
    """Dimensão declarada da coluna pgvector e quantos chunks têm vetor."""
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # pgvector guarda a dimensão crua em atttypmod (sem o -4 dos varlena).
        linha = (
            await db.execute(
                text(
                    "SELECT a.atttypmod FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "WHERE c.relname = 'knowledge_chunks' AND a.attname = 'embedding'"
                )
            )
        ).first()
        resultado["embedding_dim_coluna"] = int(linha[0]) if linha and linha[0] else None

        resultado["knowledge_chunks_total"] = int(
            (await db.execute(text("SELECT COUNT(*) FROM knowledge_chunks"))).scalar_one()
        )
        resultado["knowledge_chunks_com_embedding"] = int(
            (
                await db.execute(
                    text("SELECT COUNT(*) FROM knowledge_chunks WHERE embedding IS NOT NULL")
                )
            ).scalar_one()
        )


def _estado_do_modelo(resultado: dict[str, Any]) -> None:
    """Reusa a validação oficial do serviço — não baixa pesos (auditoria O-2)."""
    from app.services import embedding_service as emb

    resultado["EMBEDDINGS_MODEL"] = emb.MODEL_NAME
    resultado["EMBEDDINGS_PROVIDER"] = emb._provider()
    resultado["embedding_dim_configurada"] = emb.EMBED_DIM
    modelo_ok, detalhe = emb.validar_modelo_local()
    resultado["modelo_valido"] = bool(modelo_ok)
    resultado["modelo_detalhe"] = detalhe
    resultado["embeddings_disponivel"] = bool(emb.disponivel())


async def main() -> int:
    from app.core.config import get_settings

    settings = get_settings()
    resultado: dict[str, Any] = {"ok": True, "problemas": []}
    problemas: list[str] = resultado["problemas"]

    for nome in _FLAGS_BOOL:
        resultado[nome] = bool(getattr(settings, nome, False))

    # As duas coletas são independentes: uma falhar não pode cegar a outra.
    try:
        await _estado_do_banco(resultado)
    except Exception as exc:
        problemas.append(f"sonda do banco falhou: {type(exc).__name__}: {str(exc)[:200]}")
    try:
        _estado_do_modelo(resultado)
    except Exception as exc:
        problemas.append(f"sonda do modelo falhou: {type(exc).__name__}: {str(exc)[:200]}")

    if resultado["EMBEDDINGS_ENABLED"]:
        dim_col = resultado.get("embedding_dim_coluna")
        dim_cfg = resultado.get("embedding_dim_configurada")
        if dim_col and dim_cfg and dim_col != dim_cfg:
            problemas.append(
                f"coluna é vector({dim_col}) mas EMBEDDINGS_DIM={dim_cfg} — "
                "a ingestão do RAG vai falhar na gravação"
            )
        if resultado.get("modelo_valido") is False:
            problemas.append(f"modelo de embeddings inválido: {resultado.get('modelo_detalhe')}")
        if resultado.get("embeddings_disponivel") is False:
            problemas.append(
                "EMBEDDINGS_ENABLED=true mas embedding_service.disponivel() é "
                "False — provider não configurado; o RAG cai para busca textual"
            )
        total = resultado.get("knowledge_chunks_total") or 0
        if total and not (resultado.get("knowledge_chunks_com_embedding") or 0):
            problemas.append(
                "há chunks na base e NENHUM tem embedding — busca semântica inerte; "
                "rode a reingestão (scripts/ingestao_rag.sh)"
            )
    else:
        # Não é erro, é uma escolha — mas precisa aparecer: degrada o RAG para
        # pg_trgm/FTS sem nenhum sintoma visível para o usuário.
        problemas.append(
            "EMBEDDINGS_ENABLED=false — RAG sem busca semântica (degradação silenciosa)"
        )

    if not resultado["AI_REQUIRE_HITL"]:
        problemas.append("AI_REQUIRE_HITL=false — peça gerada sem revisão humana obrigatória")

    resultado["ok"] = not problemas
    print(json.dumps(resultado, ensure_ascii=False, sort_keys=True))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
