# ── app/services/dossie_service.py ────────────────────────────────────────────
# Montagem do Dossiê Estratégico — agrega dados do caso + IA (via AI Gateway).
# Resultado = rascunho (DossieStatus.rascunho / HITL obrigatório).
# Enriquecimento IA: dossiê narrativo + SWOT + probabilidade de êxito +
# próximos passos acionáveis + jurisprudência relacionada (RAG).
# LGPD: todo dado enviado ao provedor passa por sanitizar_pii/validar_sem_pii.
from __future__ import annotations
import json
import logging
from uuid import uuid4
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dossie_estrategico import DossieEstrategico, DossieStatus
from app.models.atendimento import Atendimento
from app.models.checklist import CaseChecklist, CaseChecklistItem, ChecklistStatus
from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.modules.auditoria.middleware import registrar_acao
from app.services.sanitizer import sanitizar_pii, validar_sem_pii
from app.services.ai_cost import estimar_custo_brl

logger = logging.getLogger("ejc.dossie")

# Import do gateway real (função `chat`). Mantém-se opcional para testes,
# mas agora aponta para o símbolo CORRETO — não há mais `chamar_ia`.
try:
    from app.services.ai_gateway import chat as gw_chat
    _IA_OK = True
except ImportError:  # pragma: no cover
    _IA_OK = False


async def _resumo_financeiro(db: AsyncSession, case_id: str) -> dict:
    """Resumo de centro de custos (receitas/despesas) — exclui soft-deleted."""
    try:
        from app.models.centro_custo import CentroCusto, CentroCustoTipo
        receitas = (await db.execute(
            select(func.coalesce(func.sum(CentroCusto.valor), 0))
            .where(CentroCusto.case_id == case_id,
                   CentroCusto.tipo == CentroCustoTipo.receita,
                   CentroCusto.deleted_at.is_(None))
        )).scalar()
        despesas = (await db.execute(
            select(func.coalesce(func.sum(CentroCusto.valor), 0))
            .where(CentroCusto.case_id == case_id,
                   CentroCusto.tipo == CentroCustoTipo.despesa,
                   CentroCusto.deleted_at.is_(None))
        )).scalar()
        return {
            "total_receitas": float(receitas),
            "total_despesas": float(despesas),
            "lucro_bruto":    float(receitas) - float(despesas),
        }
    except Exception:
        return {}


async def _checklists_pendentes(db: AsyncSession, case_id: str) -> list[dict]:
    """Pendências obrigatórias por checklist em UMA única query (sem N+1)."""
    pend_subq = (
        select(
            CaseChecklistItem.case_checklist_id.label("ck_id"),
            func.count(CaseChecklistItem.id).label("pendentes"),
        )
        .where(CaseChecklistItem.concluido.is_(False),
               CaseChecklistItem.obrigatorio.is_(True))
        .group_by(CaseChecklistItem.case_checklist_id)
        .subquery()
    )
    rows = (await db.execute(
        select(
            CaseChecklist.nome,
            CaseChecklist.itens_ok,
            CaseChecklist.total_itens,
            func.coalesce(pend_subq.c.pendentes, 0).label("pendentes"),
        )
        .join(pend_subq, pend_subq.c.ck_id == CaseChecklist.id)
        .where(CaseChecklist.case_id == case_id,
               CaseChecklist.status == ChecklistStatus.em_andamento)
    )).all()

    return [
        {
            "checklist":             r.nome,
            "obrigatorios_pendentes": r.pendentes,
            "progresso":             f"{r.itens_ok}/{r.total_itens}",
        }
        for r in rows if r.pendentes
    ]


async def _ultimos_atendimentos(db: AsyncSession, case_id: str, limit: int = 5) -> list[dict]:
    rows = (await db.execute(
        select(Atendimento)
        .where(Atendimento.case_id == case_id)
        .order_by(Atendimento.data_atendimento.desc())
        .limit(limit)
    )).scalars().all()
    return [
        {
            "data":   r.data_atendimento.strftime("%d/%m/%Y") if r.data_atendimento else None,
            "tipo":   r.tipo.value if hasattr(r.tipo, "value") else r.tipo,
            "resumo": (r.resumo or "")[:300],
        }
        for r in rows
    ]


async def _dados_caso(db: AsyncSession, case_id: str) -> dict:
    from app.models.case import Case
    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not caso:
        return {}
    return {
        # Nomes de coluna REAIS do modelo Case (case.py)
        "numero":      caso.numero_interno or "",
        "titulo":      caso.titulo or "",
        "status":      caso.status.value if hasattr(caso.status, "value") else str(caso.status),
        "area":        caso.area.value if hasattr(caso.area, "value") else str(caso.area or ""),
        "descricao":   (caso.descricao_fatos or "")[:500],
        "data_inicio": caso.created_at.strftime("%d/%m/%Y") if caso.created_at else None,
        "client_id":   caso.client_id,  # Bloco 5: escopo do RAG (não exposto no dossiê final)
        "case_id":     caso.id,         # C4: escopo por caso do RAG (idem)
    }


async def _jurisprudencia_relacionada(db: AsyncSession, dados: dict) -> list[dict]:
    """Busca jurisprudência/legislação relacionada via RAG (pgvector + textual)."""
    try:
        from app.services.ai_service import buscar_contexto_rag
        caso = dados.get("caso", {})
        consulta = f"{caso.get('area', '')} {caso.get('titulo', '')} {caso.get('descricao', '')}"[:300]
        fontes = await buscar_contexto_rag(
            db, consulta, limite=4,
            scope_client_id=caso.get("client_id"),
            # C4: intimação de OUTRO caso do mesmo cliente não entra no dossiê.
            scope_case_id=caso.get("case_id"),
        )
        return [
            {"titulo": f["titulo"], "categoria": f["categoria"],
             "chunk_id": f["chunk_id"], "trecho": (f["conteudo"] or "")[:400]}
            for f in fontes
        ]
    except Exception as e:
        logger.warning(f"RAG jurisprudência falhou: {e}")
        return []


def _montar_prompt(dados: dict, rag: list[dict]) -> str:
    linhas = [
        "Você é um assistente jurídico estratégico. Gere um dossiê estruturado para o seguinte caso:",
        "",
        f"## CASO: {dados.get('caso', {}).get('titulo', 'N/D')}",
        f"Número: {dados.get('caso', {}).get('numero', 'N/D')}",
        f"Área: {dados.get('caso', {}).get('area', 'N/D')}",
        f"Status: {dados.get('caso', {}).get('status', 'N/D')}",
        f"Descrição: {dados.get('caso', {}).get('descricao', '')}",
        "",
    ]
    fin = dados.get("financeiro", {})
    if fin:
        linhas += [
            "## SITUAÇÃO FINANCEIRA",
            f"Receitas: R$ {fin.get('total_receitas', 0):.2f}",
            f"Despesas: R$ {fin.get('total_despesas', 0):.2f}",
            f"Resultado: R$ {fin.get('lucro_bruto', 0):.2f}",
            "",
        ]
    atend = dados.get("atendimentos", [])
    if atend:
        linhas.append("## ÚLTIMOS ATENDIMENTOS")
        for a in atend:
            linhas.append(f"- {a.get('data')} ({a.get('tipo')}): {a.get('resumo')}")
        linhas.append("")
    cl = dados.get("checklists_pendentes", [])
    if cl:
        linhas.append("## CHECKLISTS COM PENDÊNCIAS")
        for c in cl:
            linhas.append(f"- {c.get('checklist')}: {c.get('obrigatorios_pendentes')} item(ns) obrigatório(s) pendente(s) ({c.get('progresso')})")
        linhas.append("")
    if rag:
        linhas.append("## JURISPRUDÊNCIA E LEGISLAÇÃO RELACIONADAS (base interna)")
        for i, f in enumerate(rag, start=1):
            linhas.append(f"[Fonte {i}] {f.get('titulo')} ({f.get('categoria')})\n{f.get('trecho')}")
        linhas.append("")

    linhas += [
        "Com base EXCLUSIVAMENTE nos dados acima, gere um dossiê estratégico com as seguintes seções:",
        "1. Identificação do Caso",
        "2. Status Atual e Análise",
        "3. Situação Financeira e Projeção",
        "4. Histórico de Comunicações",
        "5. Pendências e Próximos Passos Acionáveis (lista objetiva, com responsável e prazo sugerido)",
        "6. Análise SWOT Estratégica (Forças, Fraquezas, Oportunidades, Ameaças)",
        "7. Probabilidade de Êxito (baixa/média/alta, COM justificativa baseada nos dados — NUNCA prometa resultado)",
        "8. Jurisprudência Relacionada (cite [Fonte N] das fontes fornecidas; se não houver, escreva 'sem base na biblioteca interna')",
        "9. Recomendações Estratégicas da IA",
        "",
        "REGRAS: não invente fatos, julgados ou artigos; cite [Fonte N] para material da base; "
        "nunca prometa resultado ('vai ganhar'/'garantido').",
        "Formate em Markdown claro e profissional.",
        "IMPORTANTE: Este é um RASCUNHO para revisão humana obrigatória antes de uso.",
    ]
    return "\n".join(linhas)


async def ler_ultimo_dossie(
    db:      AsyncSession,
    case_id: str,
) -> Optional[DossieEstrategico]:
    """LEITOR PURO (achado S3/M2) — retorna a ÚLTIMA versão persistida do dossiê
    do caso, SEM regenerar nada: nenhuma chamada de IA, nenhuma escrita, nenhum
    AILog. É o que uma tool de LEITURA do agente deve usar (efeito colateral
    zero). Retorna None se o caso ainda não tem dossiê."""
    return (await db.execute(
        select(DossieEstrategico)
        .where(DossieEstrategico.case_id == case_id)
        .order_by(DossieEstrategico.versao.desc())
        .limit(1)
    )).scalar_one_or_none()


async def gerar_dossie(
    db:      AsyncSession,
    case_id: str,
    user_id: str,
    titulo:  Optional[str] = None,
) -> DossieEstrategico:
    """
    Agrega dados do caso, enriquece via IA (Gateway) e persiste como
    DossieEstrategico (status=rascunho). Registra AILog (HITL) e custo.
    Revisão humana é obrigatória antes de aprovar.
    """
    dados = {
        "caso":                 await _dados_caso(db, case_id),
        "financeiro":           await _resumo_financeiro(db, case_id),
        "atendimentos":         await _ultimos_atendimentos(db, case_id),
        "checklists_pendentes": await _checklists_pendentes(db, case_id),
    }
    rag = await _jurisprudencia_relacionada(db, dados)

    # Determina próxima versão
    ultima = (await db.execute(
        select(func.max(DossieEstrategico.versao))
        .where(DossieEstrategico.case_id == case_id)
    )).scalar() or 0

    modelo_ia = "—"
    provedor_ia = "—"
    conteudo_md = ""
    tokens = 0
    tokens_in = None
    tokens_out = None
    custo = None
    pii_removida = False
    prompt_sanitizado_log = ""   # o que efetivamente foi enviado (sem PII)
    ai_log_id: Optional[str] = None

    if _IA_OK:
        try:
            prompt = _montar_prompt(dados, rag)
            # LGPD: sanitiza o prompt inteiro antes de qualquer envio ao provedor.
            prompt_limpo, pii_removida = sanitizar_pii(prompt)
            residual = validar_sem_pii(prompt_limpo)
            if residual:
                raise ValueError(
                    f"PII residual após sanitização: {', '.join(residual)} — "
                    "abortando envio ao provedor."
                )
            prompt_sanitizado_log = prompt_limpo

            # Nomes próprios do caso (cliente/empresa/parte contrária/advogado)
            # → marcadores consistentes e REVERSÍVEIS antes do provider externo
            # (task estrategia = EXTERNO_PSEUDONIMIZADO). A pré-sanitização acima
            # cobre a PII estrutural; `entidades` cobre os nomes.
            from app.services.ai.entidades_caso import entidades_do_caso
            entidades = await entidades_do_caso(db, case_id)

            resp = await gw_chat(
                messages=[
                    {"role": "system",
                     "content": "Você é um assistente jurídico estratégico profissional. "
                                "Responda somente com o dossiê em Markdown. "
                                "Toda saída é rascunho sob revisão humana."},
                    {"role": "user", "content": prompt_limpo},
                ],
                task_type="estrategia",  # task_type REAL do gateway
                temperature=0.3,
                max_tokens=3500,
                entidades=entidades or None,
            )
            conteudo_md = resp.texto
            modelo_ia   = resp.modelo
            provedor_ia = resp.provedor
            tokens_in   = resp.input_tokens
            tokens_out  = resp.output_tokens
            tokens      = (tokens_in or 0) + (tokens_out or 0)
            custo       = estimar_custo_brl(resp.provedor, tokens_in, tokens_out)
        except Exception as exc:
            logger.error(f"Falha na geração IA do dossiê (caso {case_id}): {exc}")
            conteudo_md = (
                f"[Erro ao gerar via IA: {exc}]\n\nDados brutos:\n"
                f"```json\n{json.dumps(dados, ensure_ascii=False, indent=2)}\n```"
            )
    else:
        conteudo_md = (
            f"# Dossiê Estratégico\n\nIA indisponível. Dados do caso:\n"
            f"```json\n{json.dumps(dados, ensure_ascii=False, indent=2)}\n```"
        )

    # Monta secoes_json com dados brutos (auditabilidade)
    secoes = {
        "identificacao":        dados.get("caso", {}),
        "financeiro":           dados.get("financeiro", {}),
        "atendimentos":         dados.get("atendimentos", []),
        "checklists_pendentes": dados.get("checklists_pendentes", []),
        "jurisprudencia_rag":   rag,
    }

    dossie = DossieEstrategico(
        id=str(uuid4()),
        case_id=case_id,
        versao=ultima + 1,
        titulo=titulo or f"Dossiê Estratégico v{ultima + 1} — {dados.get('caso', {}).get('titulo', case_id)}",
        conteudo_texto=conteudo_md,
        conteudo_html=None,     # geração HTML opcional (weasyprint no endpoint PDF)
        secoes_json=json.dumps(secoes, ensure_ascii=False),
        status=DossieStatus.rascunho,
        modelo_ia=modelo_ia,
        provedor_ia=provedor_ia,
        tokens_usados=tokens,
        gerado_por=user_id,
    )
    db.add(dossie)
    await db.flush()

    # AI LOG (HITL rastreável) — só quando a IA efetivamente respondeu.
    # Grava o prompt SANITIZADO (sem PII) — nunca o original.
    if _IA_OK and modelo_ia not in ("—", ""):
        ai_log_id = str(uuid4())
        log = AILog(
            id=ai_log_id,
            user_id=user_id,
            case_id=case_id,
            tipo_uso=AITipoUso.analise_caso,
            modelo=modelo_ia,
            prompt_sanitizado=prompt_sanitizado_log[:8000],
            pii_removida=pii_removida,
            resposta=conteudo_md,
            fontes_rag="; ".join(f["chunk_id"] for f in rag) if rag else None,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            custo_estimado=custo,
            status_hitl=AIStatusHITL.gerado,
        )
        db.add(log)

    await db.commit()

    await registrar_acao(
        db, user_id, "criar", "dossie_estrategico", dossie.id,
        f"Dossiê v{dossie.versao} gerado para caso {case_id} "
        f"(IA: {provedor_ia}/{modelo_ia}; ai_log={ai_log_id or 'n/a'})",
    )
    return dossie
