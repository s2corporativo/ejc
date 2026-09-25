# ── app/services/case_context.py ─────────────────────────────────────────────
# AGREGADOR DE CONTEXTO DO CASO — interliga todos os dados para a IA "entender"
# o sistema inteiro. Dado um case_id, monta um dossiê consolidado lendo:
#   Caso base → Cliente → contexto especializado compatível (quando houver) →
#   Dossiê documental canônico → Prazos → Honorários → Peças → Movimentações.
#
# REGRAS:
#   • Tudo passa pelo sanitizador LGPD antes de ir à IA (nomes, CPF, CNPJ, proc).
#   • Visibilidade respeita o perfil (advogado só vê seus casos — validado no router).
#   • Fatos documentais vêm dos originais/hash/páginas; IA não altera essa camada.
#   • Saída em texto estruturado [DOSSIÊ] pronto para injeção no prompt da IA.
#   • Nenhum dado inventado: campos vazios são omitidos, não preenchidos.
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseMovimento
from app.models.client import Client
from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee import Fee
from app.models.legal_doc import LegalDoc
from app.modules.legacy_verticals.case_context_adapter import (
    load_specialized_case_context,
)
from app.services.legal_case_context import (
    format_context_value,
    legal_area_context_label,
)
from app.services.sanitizer import sanitizar_pii


async def montar_dossie(
    db: AsyncSession,
    case_id: str,
    incluir_pecas: bool = True,
    sanitizar: bool = True,
) -> Optional[dict]:
    """
    Monta o dossiê consolidado do caso. Retorna dict com:
      - 'texto': string [DOSSIÊ] pronta para o prompt da IA (sanitizada)
      - 'meta':  dados estruturados (não sanitizados — uso interno/UI)
      - 'nomes_proteger': lista de nomes próprios a mascarar no resto do prompt
    Retorna None se o caso não existir.
    """
    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not caso:
        return None

    # ── Cliente ───────────────────────────────────────────────────────────────
    cliente = (await db.execute(
        select(Client).where(Client.id == caso.client_id)
    )).scalar_one_or_none()

    nomes_proteger: list[str] = []
    if cliente:
        for n in (cliente.nome, cliente.razao_social, cliente.nome_fantasia):
            if n:
                nomes_proteger.append(n)
    if caso.parte_contraria:
        nomes_proteger.append(caso.parte_contraria)

    # ── Contexto especializado legado ─────────────────────────────────────────
    # O Core não conhece mais models/tabelas por ramo. Durante a migração #1843,
    # um adapter isolado converte eventual satélite legado para contrato neutro.
    area_base = legal_area_context_label(caso.area)
    specialized_context = await load_specialized_case_context(db, case_id, caso.area)
    ramo_label = specialized_context.label if specialized_context else area_base

    # ── Dossiê documental canônico ───────────────────────────────────────────
    # Fonte distinta do campo editável de fatos e de qualquer interpretação de IA.
    from app.services.dossie_documental_canonico import montar_dossie_documental_canonico
    dossie_documental = await montar_dossie_documental_canonico(db, case_id)

    # ── Prazos ativos ─────────────────────────────────────────────────────────
    prazos = (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id,
            Deadline.status != DeadlineStatus.concluido,
            Deadline.deleted_at.is_(None),
        ).order_by(Deadline.data_prazo.asc()).limit(10)
    )).scalars().all()

    # ── Honorários ────────────────────────────────────────────────────────────
    honorarios = (await db.execute(
        select(Fee).where(Fee.case_id == case_id, Fee.deleted_at.is_(None))
    )).scalars().all()

    # ── Peças ─────────────────────────────────────────────────────────────────
    pecas = []
    if incluir_pecas:
        pecas = (await db.execute(
            select(LegalDoc).where(LegalDoc.case_id == case_id, LegalDoc.deleted_at.is_(None))
            .order_by(LegalDoc.created_at.desc()).limit(8)
        )).scalars().all()

    # ── Movimentações recentes ────────────────────────────────────────────────
    movimentos = (await db.execute(
        select(CaseMovimento).where(CaseMovimento.case_id == case_id)
        .order_by(CaseMovimento.data_evento.desc()).limit(8)
    )).scalars().all()

    # ════════════════════════════════════════════════════════════════════════
    # MONTAGEM DO TEXTO [DOSSIÊ]
    # ════════════════════════════════════════════════════════════════════════
    L: list[str] = []
    L.append("[DOSSIÊ DO CASO — dados internos do escritório]")
    L.append(f"Número interno: {caso.numero_interno or '—'}")
    L.append(f"Título: {caso.titulo}")
    L.append(f"Área: {ramo_label}")
    L.append(f"Status: {format_context_value(caso.status)} | Fase: {format_context_value(caso.fase)} | Prioridade: {format_context_value(caso.prioridade)}")
    if caso.risco:
        L.append(f"Risco avaliado: {caso.risco}")
    if caso.valor_causa:
        L.append(f"Valor da causa: {format_context_value(caso.valor_causa)}")
    # Fase 2: fonte canônica (processes) com fallback para campo legado
    from app.services.processo_service import processo_principal as _get_proc
    _proc = await _get_proc(case_id, db)
    _numero = (_proc.get("numero_cnj") if _proc else None) or caso.numero_processo
    _trib = (_proc.get("tribunal") if _proc else None) or caso.tribunal or "—"
    _com = (_proc.get("comarca") if _proc else None) or caso.comarca or "—"
    _vara = (_proc.get("vara") if _proc else None) or caso.vara or "—"
    if _numero:
        L.append(f"Processo: {_numero} ({_trib} / {_com} / {_vara})")
    if caso.parte_contraria:
        # Incluído aqui para que sanitizar=True o mascare via nomes_proteger.
        # sanitizar=False retorna o dado bruto (uso diagnóstico/interno).
        L.append(f"Parte contrária: {caso.parte_contraria}")

    # Cliente (tipo, sem expor documento — sanitizador depois mascara nomes)
    if cliente:
        tipo_cli = "PJ" if (cliente.razao_social or cliente.cnpj_enc) else "PF"
        L.append("")
        L.append(f"[CLIENTE] Tipo {tipo_cli}"
                 + (f" · {cliente.cidade}/{cliente.estado}" if cliente.cidade else ""))
        if cliente.profissao:
            L.append(f"Profissão/atividade: {cliente.profissao}")

    # A camada documental é priorizada no contexto para impedir que relato ou
    # interpretação derivada substituam fatos vinculados aos originais.
    if dossie_documental:
        L.append("")
        L.append(dossie_documental["texto_contexto"])

    # Relato editável do caso: preservado, mas não confundido com prova documental.
    if caso.descricao_fatos:
        L.append("")
        L.append(f"[RELATO/FATOS REGISTRADOS — CAMPO EDITÁVEL]\n{caso.descricao_fatos}")

    if caso.tese_principal:
        L.append(f"[TESE PRINCIPAL — INTERPRETAÇÃO JURÍDICA]\n{caso.tese_principal}")
    if caso.pontos_fortes:
        L.append(f"[PONTOS FORTES — INTERPRETAÇÃO] {caso.pontos_fortes}")
    if caso.pontos_fracos:
        L.append(f"[PONTOS FRACOS — INTERPRETAÇÃO] {caso.pontos_fracos}")

    # Prescrição
    if caso.data_prescricao:
        L.append(f"[PRESCRIÇÃO] {caso.tipo_acao_prescricao or 'prazo'} → {format_context_value(caso.data_prescricao)}"
                 + (f" (causa interruptiva: {caso.causa_interruptiva})" if caso.causa_interruptiva else ""))

    # Contexto especializado legado — já convertido para contrato neutro.
    if specialized_context is not None and specialized_context.fields:
        L.append("")
        L.append(f"[DADOS ESPECIALIZADOS — {ramo_label}]")
        for rotulo, valor in specialized_context.fields:
            L.append(f"  • {rotulo}: {valor}")

    # Prazos
    if prazos:
        L.append("")
        L.append("[PRAZOS ATIVOS]")
        hoje = date.today()
        for p in prazos:
            dias = (p.data_prazo - hoje).days
            urg = "VENCIDO" if dias < 0 else (f"{dias}d restantes")
            L.append(f"  • {p.titulo} → {format_context_value(p.data_prazo)} ({urg})"
                     + (f" — {p.base_legal}" if p.base_legal else ""))

    # Honorários (resumo financeiro — sem expor valores nominais sensíveis em detalhe)
    if honorarios:
        total = sum((h.valor or Decimal(0)) for h in honorarios)
        pendentes = [h for h in honorarios if format_context_value(h.status) not in ("pago", "cancelado")]
        L.append("")
        L.append(f"[HONORÁRIOS] {len(honorarios)} lançamento(s), "
                 f"{len(pendentes)} pendente(s). Total contratado: {format_context_value(total)}")

    # Peças produzidas
    if pecas:
        L.append("")
        L.append("[PEÇAS PRODUZIDAS]")
        for pc in pecas:
            flag = " [IA — requer revisão]" if (pc.ai_generated and not pc.human_reviewed) else ""
            L.append(f"  • {pc.titulo} ({format_context_value(pc.tipo_peca)}, {format_context_value(pc.status)}){flag}")

    # Movimentações
    if movimentos:
        L.append("")
        L.append("[HISTÓRICO RECENTE]")
        for m in movimentos:
            L.append(f"  • {format_context_value(m.data_evento)} [{m.tipo}] {m.descricao[:120]}")

    texto_bruto = "\n".join(L)

    # ── Sanitização LGPD ──────────────────────────────────────────────────────
    if sanitizar:
        texto_final, _ = sanitizar_pii(texto_bruto, nomes_proteger)
    else:
        texto_final = texto_bruto

    return {
        "texto": texto_final,
        "nomes_proteger": nomes_proteger,
        "meta": {
            "case_id": case_id,
            "numero_interno": caso.numero_interno,
            "area": ramo_label,
            "tem_ramo_especializado": specialized_context is not None,
            "qtd_prazos_ativos": len(prazos),
            "qtd_pecas": len(pecas),
            "qtd_honorarios": len(honorarios),
            "dossie_documental_versao": dossie_documental.get("versao") if dossie_documental else None,
            "dossie_documental_sha256": dossie_documental.get("sha256_manifesto") if dossie_documental else None,
            "qtd_documentos_total_ged": dossie_documental.get("qtd_documentos_total_ged", 0) if dossie_documental else 0,
            "qtd_documentos_canonicos": dossie_documental.get("qtd_documentos", 0) if dossie_documental else 0,
            "qtd_documentos_sigilosos_omitidos": dossie_documental.get("qtd_documentos_sigilosos_omitidos", 0) if dossie_documental else 0,
            "qtd_fontes_documentais": dossie_documental.get("qtd_paginas_com_texto", 0) if dossie_documental else 0,
            "dossie_documental_truncado": dossie_documental.get("truncado", False) if dossie_documental else False,
        },
    }
