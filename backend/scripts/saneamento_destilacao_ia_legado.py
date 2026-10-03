#!/usr/bin/env python
# ── scripts/saneamento_destilacao_ia_legado.py ───────────────────────────────
# Saneia o ESTOQUE criado pela rota antiga `POST /rag/ingerir-ai-log`
# (auditoria RAG 04/09, achado A-2; security-auditor do pente fino de 03/10).
#
# POR QUE ESTE SCRIPT EXISTE
#
# A rota antiga gravava cada output de IA destilado como documento GLOBAL
# (`client_id IS NULL`) e já `rag_status='aprovado'` — sem curadoria e sem
# escopo. As correções da rota (PRs #1981/#1951) impedem novos casos, mas não
# revertem o que já foi gravado: um output gerado sobre o caso de um cliente
# continua recuperável no contexto de qualquer outro.
#
# O QUE FAZ (por documento `chave_origem LIKE 'ai_log\_%'`, global, não excluído)
#   1. rebaixa para `rag_status='pendente'` com `requires_human_review=true` e
#      remove a marca de revisão humana — volta à fila da curadoria;
#   2. quando o `ai_logs.case_id` de origem existe e o caso está ativo, aplica
#      o escopo do caso (`client_id`, `case_id`, `base_rag='caso'`), o mesmo que
#      a rota corrigida aplica a ingestões novas;
#   3. grava `saneamento_a2` no extra e um registro em `audit_logs`.
#
# Nada é apagado. O estado anterior fica em `saneamento_a2.antes`.
#
# ⚠ PRÉ-REQUISITO antes de `--aplicar`: BACKUP do banco (`scripts/backup.sh`).
#   A execução é ATO HUMANO no VPS.
#
# Execução (container ejc_backend):
#     docker exec -it ejc_backend python -m scripts.saneamento_destilacao_ia_legado
#     docker exec -it ejc_backend python -m scripts.saneamento_destilacao_ia_legado --aplicar --responsavel <user_id>
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("saneamento_destilacao_ia_legado")

PALAVRA_CONFIRMACAO = "SANEAR"
PAPEIS_GOVERNANCA = {"superadmin", "admin", "socio"}
PREFIXO_CHAVE = "ai_log_"


def log_id_da_chave(chave: str | None) -> str | None:
    chave = (chave or "").strip()
    if not chave.startswith(PREFIXO_CHAVE):
        return None
    resto = chave[len(PREFIXO_CHAVE):].strip()
    return resto or None


def extra_saneado(extra: dict | None, *, escopo: str, responsavel: str) -> dict:
    """Volta o documento à fila da curadoria, registrando o estado anterior."""
    novo = dict(extra or {})
    antes = {k: novo.get(k) for k in ("rag_status", "human_reviewed", "aprovado_por")}
    novo["rag_status"] = "pendente"
    novo["requires_human_review"] = True
    for campo in ("human_reviewed", "human_reviewed_at", "human_reviewed_by"):
        novo.pop(campo, None)
    novo["saneamento_a2"] = {
        "aplicado_em": datetime.now(timezone.utc).isoformat(),
        "responsavel": responsavel,
        "escopo": escopo,
        "antes": antes,
    }
    return novo


async def executar(aplicar: bool, responsavel: str | None) -> int:
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.ai_log import AILog
    from app.models.audit_log import criar_audit_log
    from app.models.case import Case
    from app.models.rag import BaseRag, KnowledgeDoc

    if aplicar and not responsavel:
        logger.error("--aplicar exige --responsavel <user_id> (trilha de auditoria).")
        return 2

    async with AsyncSessionLocal() as db:
        papel = None
        if aplicar:
            from app.models.user import User
            usuario = await db.get(User, responsavel)
            papel = getattr(getattr(usuario, "role", None), "value",
                            getattr(usuario, "role", None))
            if usuario is None or papel not in PAPEIS_GOVERNANCA:
                logger.error("Responsável inexistente ou sem papel de governança (%s).",
                             ", ".join(sorted(PAPEIS_GOVERNANCA)))
                return 2
        docs = (await db.execute(
            select(KnowledgeDoc).where(
                KnowledgeDoc.chave_origem.like(f"{PREFIXO_CHAVE}%"),
                KnowledgeDoc.client_id.is_(None),
                KnowledgeDoc.deleted_at.is_(None),
            )
        )).scalars().all()
        if not docs:
            logger.info("Nenhum documento legado da destilação de IA no escopo global.")
            return 0

        plano = []
        for doc in docs:
            log_id = log_id_da_chave(doc.chave_origem)
            caso = None
            if log_id:
                log = await db.get(AILog, log_id)
                case_id = getattr(log, "case_id", None)
                if case_id:
                    c = await db.get(Case, case_id)
                    if c is not None and c.deleted_at is None and c.client_id:
                        # Índice único (client_id, chave_origem): se a rota nova
                        # já gravou a versão escopada, só rebaixa esta.
                        conflito = (await db.execute(
                            select(KnowledgeDoc.id).where(
                                KnowledgeDoc.chave_origem == doc.chave_origem,
                                KnowledgeDoc.client_id == c.client_id,
                                KnowledgeDoc.deleted_at.is_(None),
                            )
                        )).first()
                        caso = None if conflito else c
            escopo = f"caso:{caso.id}" if caso else "publica (caso de origem indisponível)"
            logger.info("%s  [%s]  rag_status=%s  → pendente; escopo %s",
                        doc.id, (doc.titulo or "")[:60],
                        (doc.extra or {}).get("rag_status"), escopo)
            plano.append((doc, caso, escopo))

        com_caso = sum(1 for _, c, _ in plano if c)
        logger.info("RESUMO: %d documento(s) voltam à curadoria; %d recebem escopo do caso.",
                    len(plano), com_caso)
        if not aplicar:
            logger.info("DRY-RUN — nada foi alterado. Use --aplicar --responsavel <id>.")
            return 0
        confirmacao = input(f'Digite "{PALAVRA_CONFIRMACAO}" para confirmar: ').strip()
        if confirmacao != PALAVRA_CONFIRMACAO:
            logger.warning("Confirmação incorreta — abortado sem alterar nada.")
            return 1
        for doc, caso, escopo in plano:
            doc.extra = extra_saneado(doc.extra, escopo=escopo, responsavel=responsavel)
            if caso is not None:
                doc.client_id = str(caso.client_id)
                doc.case_id = str(caso.id)
                doc.base_rag = BaseRag.caso
            await criar_audit_log(
                db, user_id=responsavel, user_role=papel, acao="SANEAMENTO_RAG_A2",
                entidade="knowledge_docs", registro_id=doc.id,
                detalhes=f"Destilação de IA legada → pendente; escopo {escopo}",
            )
        await db.commit()
        logger.info("Aplicado: %d documento(s) saneado(s).", len(plano))
        return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Saneamento do estoque legado da destilação de IA (A-2)")
    ap.add_argument("--aplicar", action="store_true",
                    help="efetiva o saneamento (exige confirmação digitada)")
    ap.add_argument("--responsavel", help="users.id de quem executa (audit log)")
    args = ap.parse_args()
    return asyncio.run(executar(args.aplicar, args.responsavel))


if __name__ == "__main__":
    raise SystemExit(main())
