# ── app/services/case_context.py ─────────────────────────────────────────────
# AGREGADOR DE CONTEXTO DO CASO — interliga todos os dados para a IA "entender"
# o sistema inteiro. Dado um case_id, monta um dossiê consolidado lendo:
#   Caso base → Cliente → Ramo especializado (1 dos 6 + ambiental) →
#   Prazos ativos → Honorários → Peças → Movimentações.
#
# REGRAS:
#   • Tudo passa pelo sanitizador LGPD antes de ir à IA (nomes, CPF, CNPJ, proc).
#   • Visibilidade respeita o perfil (advogado só vê seus casos — validado no router).
#   • Saída em texto estruturado [DOSSIÊ] pronto para injeção no prompt da IA.
#   • Nenhum dado inventado: campos vazios são omitidos, não preenchidos.
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseMovimento
from app.models.client import Client
from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee import Fee
from app.models.legal_doc import LegalDoc
from app.models.environmental import EnvironmentalCase
from app.models.especializado import (
    EmpresarialCase, CivelCase, PenalCase,
    TrabalhistaCase, AdminCase, BancarioCase,
)
from app.services.sanitizer import sanitizar_pii


# Mapa: área do caso → (modelo satélite, rótulo legível, label do ramo)
_RAMO_MAP = {
    "ambiental":   (EnvironmentalCase, "Ambiental"),
    "empresarial": (EmpresarialCase,   "Empresarial"),
    "civil":       (CivelCase,         "Cível"),
    "consumidor":  (CivelCase,         "Cível/Consumidor"),
    "familia":     (CivelCase,         "Cível/Família"),
    "criminal":    (PenalCase,         "Penal"),
    "trabalhista": (TrabalhistaCase,   "Trabalhista"),
    "tributario":  (AdminCase,         "Administrativo/Tributário"),
    # Áreas próprias desde a migration 083 (antes: satélite aproximada ou
    # detecção indireta — o comentário antigo sobre "bancário sem área" caiu):
    "administrativo": (AdminCase,      "Administrativo"),
    "bancario":       (BancarioCase,   "Bancário"),
    "imobiliario":    (CivelCase,      "Cível/Imobiliário"),
    "sucessoes":      (CivelCase,      "Cível/Sucessões"),
    "constitucional": (AdminCase,      "Administrativo/Constitucional"),
    "digital_lgpd":   (CivelCase,      "Cível/Digital-LGPD"),
    "transito":       (AdminCase,      "Administrativo/Trânsito"),
}


def _fmt_val(v) -> str:
    """Formata valores para leitura — datas, decimais, enums, None."""
    if v is None:
        return "—"
    # Enums → valor legível (ex: BancarioTipo.busca_apreensao → "busca apreensao")
    if hasattr(v, "value") and not isinstance(v, (int, float, bool)):
        return str(v.value).replace("_", " ")
    if isinstance(v, Decimal):
        from app.utils.format import formatar_brl  # #41: formatador BRL único
        return formatar_brl(v)
    if isinstance(v, (date, datetime)):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    return str(v)


def _campos_relevantes(obj, omitir: set[str]) -> list[tuple[str, str]]:
    """Extrai campos preenchidos de um modelo satélite (omite vazios e meta)."""
    linhas = []
    base_omit = {"id", "case_id", "created_at", "updated_at", "deleted_at"} | omitir
    for col in obj.__table__.columns:
        if col.key in base_omit:
            continue
        val = getattr(obj, col.key, None)
        if val is None or val == "" or val is False:
            continue
        rotulo = col.key.replace("_", " ").capitalize()
        linhas.append((rotulo, _fmt_val(val)))
    return linhas


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

    # ── Ramo especializado ────────────────────────────────────────────────────
    ramo_obj = None
    ramo_label = caso.area.value if hasattr(caso.area, "value") else str(caso.area)
    modelo_info = _RAMO_MAP.get(ramo_label)
    if modelo_info:
        Modelo, label = modelo_info
        ramo_obj = (await db.execute(
            select(Modelo).where(Modelo.case_id == case_id, Modelo.deleted_at.is_(None))
        )).scalar_one_or_none()
        ramo_label = label
    # Bancário: detectar mesmo sem área própria
    if ramo_obj is None:
        ban = (await db.execute(
            select(BancarioCase).where(BancarioCase.case_id == case_id, BancarioCase.deleted_at.is_(None))
        )).scalar_one_or_none()
        if ban:
            ramo_obj, ramo_label = ban, "Bancário/Financeiro"

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
    L.append(f"Status: {_fmt_val(caso.status)} | Fase: {_fmt_val(caso.fase)} | Prioridade: {_fmt_val(caso.prioridade)}")
    if caso.risco:
        L.append(f"Risco avaliado: {caso.risco}")
    if caso.valor_causa:
        L.append(f"Valor da causa: {_fmt_val(caso.valor_causa)}")
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
        tipo_cli = "PJ" if (cliente.razao_social or cliente.cnpj) else "PF"
        L.append("")
        L.append(f"[CLIENTE] Tipo {tipo_cli}"
                 + (f" · {cliente.cidade}/{cliente.estado}" if cliente.cidade else ""))
        if cliente.profissao:
            L.append(f"Profissão/atividade: {cliente.profissao}")

    # Estratégia já registrada
    if caso.descricao_fatos:
        L.append("")
        L.append(f"[FATOS REGISTRADOS]\n{caso.descricao_fatos}")
    if caso.tese_principal:
        L.append(f"[TESE PRINCIPAL]\n{caso.tese_principal}")
    if caso.pontos_fortes:
        L.append(f"[PONTOS FORTES] {caso.pontos_fortes}")
    if caso.pontos_fracos:
        L.append(f"[PONTOS FRACOS] {caso.pontos_fracos}")

    # Prescrição
    if caso.data_prescricao:
        L.append(f"[PRESCRIÇÃO] {caso.tipo_acao_prescricao or 'prazo'} → {_fmt_val(caso.data_prescricao)}"
                 + (f" (causa interruptiva: {caso.causa_interruptiva})" if caso.causa_interruptiva else ""))

    # Ramo especializado
    if ramo_obj is not None:
        campos = _campos_relevantes(ramo_obj, omitir=set())
        if campos:
            L.append("")
            L.append(f"[DADOS ESPECIALIZADOS — {ramo_label}]")
            for rotulo, valor in campos:
                L.append(f"  • {rotulo}: {valor}")

    # Prazos
    if prazos:
        L.append("")
        L.append("[PRAZOS ATIVOS]")
        hoje = date.today()
        for p in prazos:
            dias = (p.data_prazo - hoje).days
            urg = "VENCIDO" if dias < 0 else (f"{dias}d restantes")
            L.append(f"  • {p.titulo} → {_fmt_val(p.data_prazo)} ({urg})"
                     + (f" — {p.base_legal}" if p.base_legal else ""))

    # Honorários (resumo financeiro — sem expor valores nominais sensíveis em detalhe)
    if honorarios:
        total = sum((h.valor or Decimal(0)) for h in honorarios)
        pendentes = [h for h in honorarios if _fmt_val(h.status) not in ("pago", "cancelado")]
        L.append("")
        L.append(f"[HONORÁRIOS] {len(honorarios)} lançamento(s), "
                 f"{len(pendentes)} pendente(s). Total contratado: {_fmt_val(total)}")

    # Peças produzidas
    if pecas:
        L.append("")
        L.append("[PEÇAS PRODUZIDAS]")
        for pc in pecas:
            flag = " [IA — requer revisão]" if (pc.ai_generated and not pc.human_reviewed) else ""
            L.append(f"  • {pc.titulo} ({_fmt_val(pc.tipo_peca)}, {_fmt_val(pc.status)}){flag}")

    # Movimentações
    if movimentos:
        L.append("")
        L.append("[HISTÓRICO RECENTE]")
        for m in movimentos:
            L.append(f"  • {_fmt_val(m.data_evento)} [{m.tipo}] {m.descricao[:120]}")

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
            "tem_ramo_especializado": ramo_obj is not None,
            "qtd_prazos_ativos": len(prazos),
            "qtd_pecas": len(pecas),
            "qtd_honorarios": len(honorarios),
        },
    }
