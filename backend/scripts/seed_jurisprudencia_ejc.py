"""Seed idempotente da rodada-piloto de jurisprudência oficial do EJC.

Carrega somente `processos_v4.jsonl`, composto por julgados TJMG com URL oficial
específica e conferência documental direta. Os registros entram em quarentena de
curadoria (`rag_status=quarentena`) e não ficam disponíveis para citações até a
aprovação no fluxo de governança.

O frame completo, os metadados V2 e o staging não entram no RAG por este seed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

FONTE_SLUG = "juris_piloto_betim_contagem_2026_08"
DESCRICAO = "Rodada-piloto TJMG — Betim e Contagem — V4 direto em quarentena"
SEED_DIR = _BACKEND / "seeds" / "jurisprudencia_ejc" / "rodada_piloto_2026_08"
SEED_FILE = SEED_DIR / "processos_v4.jsonl"


def carregar_julgados(path: Path = SEED_FILE) -> list[dict]:
    docs: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL inválido na linha {line_no}: {exc}") from exc
            if doc.get("categoria") != "jurisprudencia":
                raise ValueError(f"Categoria inválida na linha {line_no}")
            extra = doc.get("extra") or {}
            if extra.get("validation_tier") != "V4_DIRETO":
                raise ValueError(f"Documento sem V4_DIRETO na linha {line_no}")
            if extra.get("rag_status") != "quarentena":
                raise ValueError(f"Documento fora de quarentena na linha {line_no}")
            docs.append(doc)
    if not docs:
        raise ValueError(f"Seed vazio: {path}")
    return docs


async def executar_seed(db, *, embutir_vetores: bool = True) -> dict:
    from app.services.ingestion_service import (
        marcar_execucao,
        registrar_fonte,
        upsert_documento,
    )

    docs = carregar_julgados()
    await registrar_fonte(db, FONTE_SLUG, DESCRICAO, categoria_rag="jurisprudencia")
    await db.commit()

    contagem = {"novo": 0, "atualizado": 0, "inalterado": 0, "erro": 0}
    detalhe: list[dict[str, str]] = []
    for doc in docs:
        try:
            extra = dict(doc.get("extra") or {})
            extra.update({
                "rag_status": "quarentena",
                "fonte_validada": True,
                "ficticio": False,
                "uso_autorizado": "revisao_curadoria",
            })
            resultado = await upsert_documento(
                db,
                titulo=doc["titulo"],
                categoria="jurisprudencia",
                conteudo=doc["conteudo"],
                chave_origem=doc["chave_origem"],
                fonte=extra.get("url_fonte") or doc.get("fonte") or FONTE_SLUG,
                tribunal=extra.get("tribunal", "TJMG"),
                confianca="alta",
                extra=extra,
                embutir_vetores=embutir_vetores,
            )
            contagem[resultado] = contagem.get(resultado, 0) + 1
            detalhe.append({"chave_origem": doc["chave_origem"], "resultado": resultado})
            await db.commit()
        except Exception as exc:  # um item com erro não desfaz os anteriores
            await db.rollback()
            contagem["erro"] += 1
            detalhe.append({
                "chave_origem": doc.get("chave_origem", ""),
                "resultado": f"erro:{type(exc).__name__}",
            })

    status = "erro" if contagem["erro"] and not contagem["novo"] else (
        "parcial" if contagem["erro"] else "sucesso"
    )
    await marcar_execucao(
        db,
        FONTE_SLUG,
        status=status,
        novos=contagem["novo"],
        total=len(docs),
    )
    await db.commit()
    return {"total": len(docs), **contagem, "documentos": detalhe}


async def main(embutir_vetores: bool) -> None:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        resumo = await executar_seed(db, embutir_vetores=embutir_vetores)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed do piloto TJMG no RAG EJC")
    parser.add_argument(
        "--sem-vetores",
        action="store_true",
        help="não gerar embeddings; manter vetorização para job posterior",
    )
    args = parser.parse_args()
    asyncio.run(main(embutir_vetores=not args.sem_vetores))
