#!/usr/bin/env python
# ── scripts/curadoria_vigencia_lote.py ───────────────────────────────────────
# Curadoria de VIGÊNCIA em lote, com trilha (auditoria RAG 04/09, achado C-1).
#
# POR QUE ESTE SCRIPT EXISTE
#
# O gate `_FILTRO_VIGENCIA_VERIFICADA_RAG` só deixa legislação fundamentar
# direito atual com prova positiva de vigência: `legal_status='vigente'`,
# origem, data de verificação e nenhum carimbo de inferência. Nenhum ingestor
# produz essa prova — o silêncio do texto compilado NÃO prova vigência — e o
# único caminho era o painel, diploma a diploma (`PATCH /rag/governanca/docs`).
# Com os defaults de produção, todo o corpus de legislação ficava fora da IA.
#
# Este script NÃO afirma vigência sozinho. Ele aplica, em lote, decisões que
# um curador humano já tomou e registrou numa planilha, exigindo para CADA
# linha: fonte oficial HTTPS (mesmo critério de `fonte_oficial`), data da
# conferência (não futura), notas e um curador identificado com papel de
# governança. Cada documento recebe a mesma trilha do painel
# (`legal_status_origem = curadoria:<id>`) mais a referência do lote, e um
# registro em `audit_logs`.
#
# FORMATO DO CSV (cabeçalho obrigatório, separador vírgula, UTF-8):
#     doc_id,legal_status,link_oficial,conferido_em,notas
#     3f0c...,vigente,https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm,2026-10-03,"Conferido texto compilado"
#
# `legal_status` ∈ vigente | parcialmente_revogada | revogada | suspensa.
# Só documentos VIGENTES (versão atual), não excluídos e de categoria
# legislativa são alterados. `rag_status` NÃO é tocado: aprovação para o RAG
# continua sendo decisão separada (`/revisar`).
#
# ⚠ PRÉ-REQUISITO antes de `--aplicar`: BACKUP do banco (`scripts/backup.sh`).
#   A execução é ATO HUMANO no VPS.
#
# Execução (container ejc_backend):
#     docker exec -it ejc_backend python -m scripts.curadoria_vigencia_lote planilha.csv --curador <user_id>
#     docker exec -it ejc_backend python -m scripts.curadoria_vigencia_lote planilha.csv --curador <user_id> --aplicar
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger("curadoria_vigencia_lote")

STATUS_ACEITOS = {"vigente", "parcialmente_revogada", "revogada", "suspensa"}
PAPEIS_CURADORIA = {"superadmin", "admin", "socio"}
COLUNAS = ("doc_id", "legal_status", "link_oficial", "conferido_em", "notas")
PALAVRA_CONFIRMACAO = "CURADORIA"


@dataclass
class Linha:
    numero: int
    doc_id: str
    legal_status: str
    link_oficial: str
    conferido_em: str
    notas: str


def validar_linha(numero: int, bruta: dict, hoje: date | None = None) -> tuple[Linha | None, str | None]:
    """Valida uma linha do CSV. Devolve (linha, None) ou (None, motivo)."""
    from app.services.knowledge_governance import fonte_oficial

    hoje = hoje or datetime.now(timezone.utc).date()
    campos = {c: str((bruta or {}).get(c) or "").strip() for c in COLUNAS}
    if not campos["doc_id"]:
        return None, "doc_id vazio"
    status = campos["legal_status"].lower()
    if status not in STATUS_ACEITOS:
        return None, f"legal_status inválido: {campos['legal_status']!r}"
    link = campos["link_oficial"]
    if not link.lower().startswith("https://") or not fonte_oficial(link):
        return None, "link_oficial precisa ser HTTPS em domínio oficial (OFFICIAL_HOST_SUFFIXES)"
    try:
        conferido = date.fromisoformat(campos["conferido_em"][:10])
    except ValueError:
        return None, "conferido_em deve ser data ISO (AAAA-MM-DD)"
    if conferido > hoje:
        return None, "conferido_em no futuro"
    if len(campos["notas"]) < 5:
        return None, "notas obrigatórias (mínimo 5 caracteres)"
    return Linha(numero, campos["doc_id"], status, link,
                 conferido.isoformat(), campos["notas"][:2000]), None


def ler_planilha(caminho: Path, hoje: date | None = None) -> tuple[list[Linha], list[str], str]:
    """Lê e valida o CSV inteiro. Devolve (válidas, erros, sha256 do arquivo)."""
    bruto = caminho.read_bytes()
    digest = hashlib.sha256(bruto).hexdigest()
    leitor = csv.DictReader(bruto.decode("utf-8-sig").splitlines())
    faltando = [c for c in COLUNAS if c not in (leitor.fieldnames or [])]
    if faltando:
        return [], [f"cabeçalho sem as colunas: {', '.join(faltando)}"], digest
    validas: list[Linha] = []
    erros: list[str] = []
    vistos: set[str] = set()
    for i, bruta in enumerate(leitor, start=2):
        linha, erro = validar_linha(i, bruta, hoje)
        if erro:
            erros.append(f"linha {i}: {erro}")
            continue
        if linha.doc_id in vistos:
            erros.append(f"linha {i}: doc_id repetido no lote")
            continue
        vistos.add(linha.doc_id)
        validas.append(linha)
    return validas, erros, digest


def extra_com_curadoria(extra: dict | None, linha: Linha, curador_id: str, lote: str) -> dict:
    """Mesmo contrato do PATCH do painel, acrescido da referência do lote."""
    novo = dict(extra or {})
    novo["legal_status"] = linha.legal_status
    novo["legal_status_origem"] = f"curadoria:{curador_id}"
    novo["legal_status_verificado_em"] = linha.conferido_em
    novo.pop("legal_status_inferido_em", None)
    novo["link_official"] = linha.link_oficial
    novo["legal_status_lote"] = {
        "arquivo_sha256": lote,
        "linha": linha.numero,
        "notas": linha.notas,
        "aplicado_em": datetime.now(timezone.utc).isoformat(),
    }
    return novo


async def executar(caminho: Path, curador_id: str, aplicar: bool) -> int:
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.audit_log import criar_audit_log
    from app.models.rag import KnowledgeDoc
    from app.models.user import User

    validas, erros, lote = ler_planilha(caminho)
    for erro in erros:
        logger.warning("REJEITADA %s", erro)
    if erros:
        logger.error("%d linha(s) inválida(s): corrija a planilha; nada foi aplicado.", len(erros))
        return 1
    if not validas:
        logger.info("Planilha sem linhas.")
        return 0

    async with AsyncSessionLocal() as db:
        curador = await db.get(User, curador_id)
        papel = getattr(getattr(curador, "role", None), "value", getattr(curador, "role", None))
        if curador is None or papel not in PAPEIS_CURADORIA:
            logger.error("Curador inexistente ou sem papel de governança (%s).",
                         ", ".join(sorted(PAPEIS_CURADORIA)))
            return 1

        docs = {
            d.id: d for d in (await db.execute(
                select(KnowledgeDoc).where(KnowledgeDoc.id.in_([l.doc_id for l in validas]))
            )).scalars().all()
        }
        plano: list[tuple[Linha, KnowledgeDoc]] = []
        for linha in validas:
            doc = docs.get(linha.doc_id)
            motivo = None
            if doc is None:
                motivo = "documento não encontrado"
            elif doc.deleted_at is not None:
                motivo = "documento excluído"
            elif not doc.vigente:
                motivo = "versão histórica (vigente=false)"
            elif "legisl" not in (doc.categoria or "").lower():
                motivo = f"categoria não legislativa ({doc.categoria})"
            if motivo:
                logger.warning("IGNORADA linha %d (%s): %s", linha.numero, linha.doc_id, motivo)
                continue
            anterior = (doc.extra or {}).get("legal_status") or "—"
            logger.info("linha %d  %s  [%s]  %s → %s", linha.numero, doc.id,
                        (doc.titulo or "")[:60], anterior, linha.legal_status)
            plano.append((linha, doc))

        logger.info("RESUMO: %d documento(s) a atualizar; lote sha256=%s", len(plano), lote[:16])
        if not aplicar:
            logger.info("DRY-RUN — nada foi alterado. Use --aplicar para efetivar.")
            return 0
        confirmacao = input(f'Digite "{PALAVRA_CONFIRMACAO}" para confirmar: ').strip()
        if confirmacao != PALAVRA_CONFIRMACAO:
            logger.warning("Confirmação incorreta — abortado sem alterar nada.")
            return 1
        for linha, doc in plano:
            antes = (doc.extra or {}).get("legal_status")
            doc.extra = extra_com_curadoria(doc.extra, linha, curador_id, lote)
            await criar_audit_log(
                db, user_id=curador_id, user_role=papel, acao="CURADORIA_VIGENCIA_LOTE",
                entidade="knowledge_docs", registro_id=doc.id,
                detalhes=(f"legal_status {antes or '—'} → {linha.legal_status}; "
                          f"lote={lote[:16]}; linha={linha.numero}"),
            )
        await db.commit()
        logger.info("Aplicado: %d documento(s) com vigência curada.", len(plano))
        return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Curadoria de vigência em lote (C-1)")
    ap.add_argument("planilha", type=Path)
    ap.add_argument("--curador", required=True, help="users.id do curador (sócio/admin)")
    ap.add_argument("--aplicar", action="store_true",
                    help="efetiva as alterações (exige confirmação digitada)")
    args = ap.parse_args()
    return asyncio.run(executar(args.planilha, args.curador, args.aplicar))


if __name__ == "__main__":
    raise SystemExit(main())
