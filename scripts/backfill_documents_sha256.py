#!/usr/bin/env python3
"""Backfill de `documents.sha256` a partir do hash de INGESTÃO. Dry-run por padrão.

    docker exec -i ejc_backend python - < scripts/backfill_documents_sha256.py
    docker exec -i ejc_backend python - --aplicar < scripts/backfill_documents_sha256.py

Auditoria de 22/08/2026 (Issue #1237), achado 31.

## Por que existe

A migration 147 criou `documents.sha256` e a correção do achado 30 fez os cinco
caminhos de criação de `Document` preencherem a coluna. Isso resolve o futuro e
não toca o passado: todo documento anterior à migration continua com `NULL`.

A maquinaria de rescan (`document_rescan_service`, épico #1019 A3.2) calcula o
SHA-256 do acervo, mas grava em `document_hash_rescan_items.sha256_calculado` —
ela nasceu para DETECTAR DIVERGÊNCIA, não para preencher uma coluna que ainda
não existia. Sem este backfill, o acervo legado fica sem prova de integridade
para sempre.

## A decisão de projeto que sustenta este script

**Nunca inventar hash.** Para um documento sem registro de intake, calcular o
SHA-256 do arquivo HOJE e gravá-lo na coluna registraria o estado atual como se
fosse o original. Se aquele arquivo tivesse sido adulterado em algum momento, o
backfill carimbaria a adulteração como íntegra — e um sistema de prova
documental passaria a atestar exatamente o que deveria denunciar.

`NULL` é a resposta honesta nesse caso: significa "não há prova de integridade
para este documento", que é a verdade. Um hash inventado significaria "este
arquivo é o original", que não sabemos.

Por isso a única fonte aceita é `document_intake_items.sha256`, calculado NA
INGESTÃO e, portanto, prova de origem. Documento sem intake é contado e
reportado, nunca preenchido.

## O que o script faz

1. Conta os documentos com `sha256 IS NULL` (não excluídos).
2. Separa os que têm hash de intake dos que não têm.
3. Quando um documento tem MAIS DE UM intake com hashes divergentes, não
   escolhe: reporta e pula. Divergência entre registros de ingestão do mesmo
   arquivo é achado para humano, não empate a desempatar por heurística.
4. Em `--aplicar`, grava só onde `sha256 IS NULL` — idempotente por construção:
   rodar de novo não altera nada e não sobrescreve hash existente.

Saída: um único JSON. Nenhum `filepath`, nome de arquivo ou dado pessoal é
impresso (LGPD) — apenas contagens e ids.
"""
from __future__ import annotations

import asyncio
import json
import sys

APLICAR = "--aplicar" in sys.argv
LIMITE_EXEMPLOS = 10


async def _principal() -> dict:
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    relatorio: dict = {"modo": "aplicar" if APLICAR else "dry_run"}

    async with AsyncSessionLocal() as db:
        total_docs = (await db.execute(text(
            "SELECT count(*) FROM documents WHERE deleted_at IS NULL"
        ))).scalar()

        sem_hash = (await db.execute(text(
            "SELECT count(*) FROM documents "
            "WHERE deleted_at IS NULL AND sha256 IS NULL"
        ))).scalar()

        com_hash = (await db.execute(text(
            "SELECT count(*) FROM documents "
            "WHERE deleted_at IS NULL AND sha256 IS NOT NULL"
        ))).scalar()

        # Candidatos: sem hash na coluna, COM hash de ingestão, e um só valor
        # distinto entre os intakes daquele documento.
        candidatos = (await db.execute(text("""
            SELECT i.document_id, min(i.sha256) AS sha256
              FROM document_intake_items i
              JOIN documents d ON d.id = i.document_id
             WHERE d.deleted_at IS NULL
               AND d.sha256 IS NULL
               AND i.sha256 IS NOT NULL
             GROUP BY i.document_id
            HAVING count(DISTINCT i.sha256) = 1
        """))).all()

        # Documentos cujos intakes DISCORDAM entre si — não se resolve por
        # heurística: o mesmo arquivo registrado com dois hashes diferentes é
        # achado de integridade, e preencher um dos dois esconderia o problema.
        conflitantes = (await db.execute(text("""
            SELECT i.document_id
              FROM document_intake_items i
              JOIN documents d ON d.id = i.document_id
             WHERE d.deleted_at IS NULL
               AND d.sha256 IS NULL
               AND i.sha256 IS NOT NULL
             GROUP BY i.document_id
            HAVING count(DISTINCT i.sha256) > 1
        """))).scalars().all()

        preenchiveis = len(candidatos)
        sem_intake = sem_hash - preenchiveis - len(conflitantes)

        relatorio.update({
            "documentos_vigentes": int(total_docs or 0),
            "ja_com_sha256": int(com_hash or 0),
            "sem_sha256": int(sem_hash or 0),
            "preenchiveis_pelo_intake": preenchiveis,
            "intakes_conflitantes": len(conflitantes),
            "sem_prova_de_origem": max(0, sem_intake),
            "exemplos_conflitantes": list(conflitantes[:LIMITE_EXEMPLOS]),
        })

        if APLICAR and candidatos:
            # `AND sha256 IS NULL` no UPDATE, e não só na seleção: garante que
            # uma escrita concorrente entre o SELECT e o UPDATE não seja
            # sobrescrita por um valor calculado com base em estado velho.
            atualizados = 0
            for document_id, sha in candidatos:
                r = await db.execute(
                    text("UPDATE documents SET sha256 = :sha "
                         "WHERE id = :id AND sha256 IS NULL"),
                    {"sha": sha, "id": document_id},
                )
                atualizados += r.rowcount or 0
            await db.commit()
            relatorio["atualizados"] = atualizados
        elif APLICAR:
            relatorio["atualizados"] = 0

    relatorio["acao_humana_necessaria"] = []
    if relatorio["sem_prova_de_origem"] > 0:
        relatorio["acao_humana_necessaria"].append(
            f"{relatorio['sem_prova_de_origem']} documento(s) sem registro de "
            "ingestao: NAO ha hash de origem conhecido e o script NAO inventa "
            "um a partir do arquivo atual. Continuam NULL de proposito."
        )
    if relatorio["intakes_conflitantes"] > 0:
        relatorio["acao_humana_necessaria"].append(
            f"{relatorio['intakes_conflitantes']} documento(s) com hashes de "
            "ingestao DIVERGENTES entre si — conferir manualmente."
        )
    if not APLICAR and relatorio["preenchiveis_pelo_intake"] > 0:
        relatorio["acao_humana_necessaria"].append(
            "dry-run: rode com --aplicar para gravar."
        )
    return relatorio


def main() -> int:
    try:
        relatorio = asyncio.run(_principal())
    except Exception as erro:  # noqa: BLE001 — a saída é sempre um JSON
        print(json.dumps({"erro": f"{type(erro).__name__}: {erro}"[:300]},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    # Exit != 0 quando resta ação humana, para o script servir em pipeline.
    return 1 if relatorio.get("acao_humana_necessaria") else 0


if __name__ == "__main__":
    sys.exit(main())
