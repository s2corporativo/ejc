# ── app/routers/ai.py ────────────────────────────────────────────────────────
# IA: análise de caso (sugestão de teses), resumo de documento, status HITL.
# Pipeline LGPD/OAB já enforçado em ai_service.py.
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.case import Case
from app.models.ai_log import AILog, AIStatusHITL
from app.services.ai_service import analisar_caso, resumir_documento
from app.services.case_context import montar_dossie
from app.schemas.ai import AnalisarCasoRequest, ResumirDocRequest, HITLRevisaoRequest

router = APIRouter(prefix="/ai", tags=["Inteligência Artificial"])


@router.post("/analisar-caso")
async def analisar(
    req: AnalisarCasoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Sugestão de teses a partir dos fatos.
    Sanitização LGPD automática. Resposta SEMPRE é rascunho (HITL).
    """
    if len(req.descricao_fatos.strip()) < 30:
        raise HTTPException(
            status_code=422,
            detail="Descreva os fatos com mais detalhes (mín. 30 caracteres)",
        )
    resultado = await analisar_caso(
        db, cu.id, req.descricao_fatos, req.area,
        nomes_proteger=req.nomes_proteger, case_id=req.case_id,
    )
    if "erro" in resultado:
        raise HTTPException(status_code=502, detail=resultado["erro"])
    return resultado


@router.get("/dossie/{case_id}")
async def dossie_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Retorna o dossiê consolidado do caso — exatamente o contexto que a IA "enxerga".
    Interliga cliente, ramo especializado, prazos, honorários, peças e histórico.
    Transparência (HITL): o advogado vê o que será enviado à IA antes de analisar.
    Visibilidade por perfil: advogado comum só acessa seus próprios casos.
    """
    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not caso:
        raise HTTPException(404, "Caso não encontrado")
    # Controle de acesso: abaixo de 'socio' só vê o próprio caso
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        if caso.advogado_responsavel_id != cu.id:
            raise HTTPException(403, "Sem permissão para este caso")

    dossie = await montar_dossie(db, case_id, incluir_pecas=True, sanitizar=True)
    if not dossie:
        raise HTTPException(404, "Caso não encontrado")
    return dossie


@router.post("/resumir-documento")
async def resumir(
    req: ResumirDocRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    if len(req.texto.strip()) < 50:
        raise HTTPException(status_code=422, detail="Texto muito curto")
    resultado = await resumir_documento(db, cu.id, req.texto, case_id=req.case_id)
    if "erro" in resultado:
        raise HTTPException(status_code=502, detail=resultado["erro"])
    return resultado


@router.get("/logs")
async def listar_logs(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    case_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Histórico de uso da IA (rastreabilidade)."""
    q = select(AILog)
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        q = q.where(AILog.user_id == cu.id)
    if case_id:
        q = q.where(AILog.case_id == case_id)
    q = q.order_by(AILog.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [
            {"id": l.id, "tipo_uso": l.tipo_uso.value, "modelo": l.modelo,
             "status_hitl": l.status_hitl.value, "pii_removida": l.pii_removida,
             "case_id": l.case_id, "created_at": l.created_at,
             "resposta": l.resposta}
            for l in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.patch("/logs/{log_id}/hitl")
async def atualizar_hitl(
    log_id: str, req: HITLRevisaoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Advogado marca a saída da IA como revisada/aplicada/descartada."""
    if req.status not in ("revisado", "aplicado", "descartado"):
        raise HTTPException(status_code=422, detail="Status HITL inválido")

    log = (await db.execute(
        select(AILog).where(AILog.id == log_id)
    )).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    if log.user_id != cu.id and ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        raise HTTPException(status_code=403, detail="Sem permissão para revisar este log")

    log.status_hitl = AIStatusHITL(req.status)
    log.revisado_por = cu.id
    log.revisado_em = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": f"Status HITL: {req.status}"}


# ═══ ECJ: Teses Ocultas · Auditor de Peças · Preparação de Audiência ═══
from app.services.ai_service import detectar_teses_ocultas, auditar_peca, preparar_audiencia, analisar_contrato
from pydantic import BaseModel as _BM, Field as _Field
from typing import Optional as _Opt, List as _List


class TesesOcultasReq(_BM):
    descricao_fatos: str
    area: str
    tese_principal: _Opt[str] = None
    nomes_proteger: _List[str] = []
    case_id: _Opt[str] = None


class AuditarPecaReq(_BM):
    conteudo: _Opt[str] = None           # texto direto OU...
    peca_id:  _Opt[str] = None           # ...id de LegalDoc (busca no GED)
    tipo_peca: str
    case_id: _Opt[str] = None


class AudienciaReq(_BM):
    resumo_caso: str
    tipo_audiencia: str = "instrução"
    nomes_proteger: _List[str] = []
    case_id: _Opt[str] = None


class AnaliseContratoReq(_BM):
    texto_contrato: str
    tipo_contrato: str = "geral"
    nomes_proteger: _List[str] = []
    case_id: _Opt[str] = None
    texto_contrato_2: _Opt[str] = None   # segunda minuta (modo comparação)
    modo: _Opt[str] = None               # "comparacao" → compara cláusula a cláusula


@router.post("/teses-ocultas")
async def teses_ocultas(
    req: TesesOcultasReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Detector de Teses Ocultas (ECJ) — ranking de relevância."""
    if len(req.descricao_fatos.strip()) < 50:
        raise HTTPException(status_code=422, detail="Descreva os fatos (mín. 50 caracteres)")
    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
    escopo_cli = None
    if req.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai_service import _escopo_cliente_do_caso
        await verificar_acesso_caso(db, cu, req.case_id)
        escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)
    r = await detectar_teses_ocultas(
        db, cu.id, req.descricao_fatos, req.area,
        req.tese_principal, req.nomes_proteger, req.case_id,
        scope_client_id=escopo_cli,
    )
    if "erro" in r:
        raise HTTPException(status_code=502, detail=r["erro"])
    return r


@router.post("/auditar-peca")
async def auditar(
    req: AuditarPecaReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Auditor de Petições (ECJ) — pontuação + omissões + inconsistências.

    Aceita `conteudo` (texto direto) OU `peca_id` (LegalDoc do GED — com
    verificação de ownership pelo caso vinculado, mesmo padrão do arquivo).
    """
    conteudo = (req.conteudo or "").strip()
    case_id = req.case_id

    if not conteudo and req.peca_id:
        from app.models.legal_doc import LegalDoc
        doc = (await db.execute(
            select(LegalDoc).where(LegalDoc.id == req.peca_id,
                                   LegalDoc.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Peça não encontrada")
        # Ownership: pelo caso vinculado (padrão do arquivo — ver teses_ocultas);
        # peça sem caso: autor da peça ou sócio+.
        if doc.case_id:
            from app.core.ownership import verificar_acesso_caso
            await verificar_acesso_caso(db, cu, doc.case_id)
        elif doc.created_by != cu.id and ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
            raise HTTPException(status_code=403, detail="Sem permissão para esta peça")
        conteudo = (doc.conteudo or "").strip()
        case_id = case_id or doc.case_id

    if not conteudo:
        raise HTTPException(status_code=422, detail="Informe 'conteudo' ou 'peca_id'")
    if len(conteudo) < 100:
        raise HTTPException(status_code=422, detail="Peça muito curta para auditar")
    r = await auditar_peca(db, cu.id, conteudo, req.tipo_peca, case_id)
    if "erro" in r:
        raise HTTPException(status_code=502, detail=r["erro"])
    return r


@router.post("/preparar-audiencia")
async def audiencia(
    req: AudienciaReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Assistente de Audiência (ECJ) — kit de preparação."""
    if len(req.resumo_caso.strip()) < 50:
        raise HTTPException(status_code=422, detail="Forneça o resumo do caso")
    r = await preparar_audiencia(
        db, cu.id, req.resumo_caso, req.tipo_audiencia,
        req.nomes_proteger, req.case_id,
    )
    if "erro" in r:
        raise HTTPException(status_code=502, detail=r["erro"])
    return r


@router.post("/gateway/health")
async def gateway_health(cu: User = Depends(get_current_user)):
    """Status dos provedores de IA disponíveis (Ollama + Groq)."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["admin"]:
        raise HTTPException(403, "Apenas administradores")
    from app.services.ai_gateway import health as gw_health
    return await gw_health()


# ═══ ASSISTENTE ESTRATÉGICO DO CASO — IA contextual por processo ═══════════

SYSTEM_ASSISTENTE_CASO = """Você é o Assistente Estratégico do caso jurídico apresentado.
Você tem acesso completo ao dossiê: cliente, processo, partes, movimentações,
documentos, petições, prazos, honorários, jurisprudência relevante e legislação.

REGRAS INVIOLÁVEIS:
1. Trabalhe EXCLUSIVAMENTE sobre o contexto fornecido. Nunca invente fatos, julgados ou artigos.
2. Cite a fonte para cada afirmação (dossiê, fonte RAG, norma).
3. Nunca prometa resultado ("vai ganhar", "é garantido").
4. Toda saída é RASCUNHO — revisão humana obrigatória (OAB).
5. Se perguntar algo fora do escopo do caso, diga: "Fora do contexto deste processo."

Você pode ser acionado para:
- Resumo executivo / dossiê do caso
- Análise de riscos e oportunidades
- Sugestão de teses e estratégias
- Revisão de petições
- Preparação de audiência (perguntas, quesitos, roteiro)
- Identificação de documentos faltantes
- Geração de memoriais
- Análise do próximo passo processual recomendado"""


class AssistenteCasoReq(_BM):
    pergunta: str = _Field(min_length=5, max_length=4000,
                           description="Pergunta ou instrução ao assistente do caso")
    modo: _Opt[str] = "geral"  # geral|resumo|riscos|teses|audiencia|documentos|peticao


@router.post("/casos/{case_id}/assistente")
async def assistente_estrategico(
    case_id: str,
    req: AssistenteCasoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    IA contextual vinculada ao caso específico.
    Acessa o dossiê completo automaticamente e responde apenas sobre aquele processo.
    Usa AI Gateway (Ollama local prioritário, Groq como fallback).
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403)

    # Verifica acesso ao caso
    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not caso:
        raise HTTPException(404, "Caso não encontrado")
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        if caso.advogado_responsavel_id != cu.id and getattr(caso, "advogado_auxiliar_id", None) != cu.id:
            raise HTTPException(403, "Sem permissão para este caso")

    # Monta dossiê completo (sanitizado para LGPD)
    from app.services.ai_service import buscar_contexto_rag
    from app.services.sanitizer import sanitizar_pii
    from app.services.ai_gateway import chat as gw_chat
    from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
    from uuid import uuid4

    dossie = await montar_dossie(db, case_id, incluir_pecas=True, sanitizar=True)
    dossie_txt = dossie["texto"] if dossie else f"Caso ID {case_id} — sem detalhes disponíveis."
    nomes_caso = dossie.get("nomes_proteger", []) if dossie else []

    # Busca jurisprudência e legislação relacionadas no RAG. Escopo por cliente
    # (Bloco 5): caso já validado por ownership acima → conteúdo restrito do
    # próprio cliente é recuperável; de outros clientes, nunca.
    consulta_rag = f"{getattr(caso.area, 'value', '')} {caso.titulo or ''}"
    fontes = await buscar_contexto_rag(db, consulta_rag[:300], limite=4, scope_client_id=caso.client_id)
    rag_txt = ""
    if fontes:
        linhas = [f"[Fonte {i+1}] {f['titulo']} ({f['categoria']})\n{f['conteudo'][:500]}"
                  for i, f in enumerate(fontes)]
        rag_txt = "\n\n[JURISPRUDÊNCIA E LEGISLAÇÃO RELACIONADAS]\n" + "\n\n".join(linhas)

    # Sanitiza pergunta
    pergunta_limpa, houve_pii = sanitizar_pii(req.pergunta, nomes_caso)

    user_msg = (
        f"[DOSSIÊ DO CASO]\n{dossie_txt}"
        f"{rag_txt}\n\n"
        f"[PERGUNTA DO ADVOGADO]\n{pergunta_limpa}"
    )

    # Mapeia modo para task_type do gateway
    task_map = {
        "geral":       "analise_juridica",
        "resumo":      "resumo",
        "riscos":      "analise_juridica",
        "teses":       "analise_juridica",
        "audiencia":   "elaboracao_peca",
        "documentos":  "analise_juridica",
        "peticao":     "elaboracao_peca",
    }
    task = task_map.get(req.modo or "geral", "analise_juridica")

    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": SYSTEM_ASSISTENTE_CASO},
                {"role": "user",   "content": user_msg},
            ],
            task_type=task,
            temperature=0.2,
            max_tokens=3000,
        )
    except Exception as e:
        raise HTTPException(502, f"IA indisponível: {str(e)[:200]}")

    # AI Log (HITL rastreável)
    log = AILog(
        id=str(uuid4()), user_id=cu.id, case_id=case_id,
        tipo_uso=AITipoUso.analise_caso,
        modelo=resp.modelo,
        prompt_sanitizado=user_msg[:8000],
        pii_removida=houve_pii,
        resposta=resp.texto,
        fontes_rag="; ".join(f["chunk_id"] for f in fontes) if fontes else None,
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    return {
        "ai_log_id": log.id,
        "resposta": resp.texto,
        "modelo": resp.modelo,
        "provedor": resp.provedor,
        "fallback": resp.fallback_ativado,
        "fontes_usadas": len(fontes),
        "pii_removida": houve_pii,
        "aviso": "⚠️ RASCUNHO gerado por IA — revisão por advogado OBRIGATÓRIA.",
    }


# ═══ MODO DUAL-IA — IA 1 analisa, IA 2 audita ════════════════════════════════

class DualIAReq(_BM):
    instrucao:  str = _Field(min_length=10, max_length=2000,
                             description="O que analisar no caso (ex: 'Liste os riscos processuais')")
    modo:       _Opt[str] = "analise"  # analise|estrategia|riscos|peticao
    model1:     _Opt[str] = None   # override modelo IA-1 (None = gateway decide)
    model2:     _Opt[str] = None   # override modelo IA-2


@router.post("/casos/{case_id}/dual")
async def dual_ia(
    case_id: str,
    req: DualIAReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Modo Dual-IA: IA 1 analisa o caso, IA 2 audita criticamente a análise.
    Retorna concordâncias, divergências e pontos ignorados por cada modelo.
    Ambas as análises são RASCUNHO — revisão humana obrigatória (HITL).
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Apenas advogados podem usar o Modo Dual-IA")

    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not caso:
        raise HTTPException(404, "Caso não encontrado")
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        if caso.advogado_responsavel_id != cu.id and getattr(caso, "advogado_auxiliar_id", None) != cu.id:
            raise HTTPException(403, "Sem permissão para este caso")

    from app.services.ai_gateway import chat as gw_chat
    from app.services.sanitizer import sanitizar_pii
    from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
    from uuid import uuid4

    dossie = await montar_dossie(db, case_id, incluir_pecas=False, sanitizar=True)
    dossie_txt = dossie["texto"] if dossie else f"Caso {case_id} — sem detalhes."

    instrucao_limpa, houve_pii = sanitizar_pii(req.instrucao, dossie.get("nomes_proteger", []) if dossie else [])

    task_map = {"analise": "analise_juridica", "estrategia": "analise_juridica",
                "riscos": "analise_juridica", "peticao": "elaboracao_peca"}
    task = task_map.get(req.modo or "analise", "analise_juridica")

    system1 = (
        "Você é a IA Analítica. Analise objetivamente o caso jurídico apresentado. "
        "Seja completo, direto e fundamente cada ponto. RASCUNHO — revisão humana obrigatória."
    )
    user1 = f"[DOSSIÊ]\n{dossie_txt[:5000]}\n\n[INSTRUÇÃO]\n{instrucao_limpa}"

    try:
        r1 = await gw_chat(
            messages=[{"role": "system", "content": system1}, {"role": "user", "content": user1}],
            task_type=task, temperature=0.2, max_tokens=2500,
            model_override=req.model1,
        )
    except Exception as e:
        raise HTTPException(502, f"IA-1 indisponível: {str(e)[:200]}")

    system2 = (
        "Você é a IA Crítica (revisora independente). Receberá o dossiê do caso e a análise "
        "produzida por outra IA. Sua missão:\n"
        "1. Confirme os pontos corretos da análise anterior.\n"
        "2. Identifique erros, omissões, argumentos frágeis ou riscos ignorados.\n"
        "3. Acrescente perspectivas não levadas em conta.\n"
        "Use o formato:\n"
        "## ✅ Concordâncias\n"
        "## ⚠️ Divergências e Correções\n"
        "## 🔍 Pontos Ignorados\n"
        "## 📋 Síntese Final\n"
        "Seja rigoroso — o objetivo é encontrar o que a IA-1 errou ou esqueceu."
    )
    user2 = (
        f"[DOSSIÊ]\n{dossie_txt[:3000]}\n\n"
        f"[ANÁLISE DA IA-1 — para auditar]\n{r1.texto}\n\n"
        f"[INSTRUÇÃO ORIGINAL]\n{instrucao_limpa}"
    )

    try:
        r2 = await gw_chat(
            messages=[{"role": "system", "content": system2}, {"role": "user", "content": user2}],
            task_type=task, temperature=0.3, max_tokens=2500,
            model_override=req.model2,
        )
    except Exception as e:
        raise HTTPException(502, f"IA-2 indisponível: {str(e)[:200]}")

    # Registra ambas no AI Log
    for modelo_usado, resposta_txt, sufixo in [
        (r1.modelo, r1.texto, "_dual_ia1"),
        (r2.modelo, r2.texto, "_dual_ia2"),
    ]:
        log = AILog(
            id=str(uuid4()), user_id=cu.id, case_id=case_id,
            tipo_uso=AITipoUso.analise_caso,
            modelo=modelo_usado,
            prompt_sanitizado=instrucao_limpa[:2000],
            pii_removida=houve_pii,
            resposta=resposta_txt,
            status_hitl=AIStatusHITL.gerado,
        )
        db.add(log)
    await db.commit()

    return {
        "analise_ia1":  r1.texto,
        "revisao_ia2":  r2.texto,
        "modelo_ia1":   r1.modelo,
        "modelo_ia2":   r2.modelo,
        "provedor_ia1": r1.provedor,
        "provedor_ia2": r2.provedor,
        "pii_removida": houve_pii,
        "aviso": (
            "⚠️ Modo Dual-IA ativo. Ambas as análises são RASCUNHOS. "
            "Divergências indicam pontos que exigem atenção especial do advogado."
        ),
    }


# ═══ VISUAL LAW — Diagramas Mermaid.js do caso ═══════════════════════════════

class VisualLawReq(_BM):
    tipo: str = "timeline"  # timeline|fluxo_status|partes|prazos


@router.post("/caso/{case_id}/visual-law")
async def visual_law(
    case_id: str,
    req: VisualLawReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Gera diagrama Mermaid.js a partir do dossiê do caso.
    O frontend renderiza o código com a biblioteca mermaid.js.
    Tipos: timeline | fluxo_status | partes | prazos
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403)

    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not caso:
        raise HTTPException(404, "Caso não encontrado")

    dossie = await montar_dossie(db, case_id, incluir_pecas=False, sanitizar=True)
    dossie_txt = dossie["texto"] if dossie else f"Caso {case_id}."

    from app.services.visual_law import gerar_diagrama, DiagramaTipo
    tipo_valido: DiagramaTipo = req.tipo if req.tipo in ("timeline", "fluxo_status", "partes", "prazos") else "timeline"  # type: ignore

    try:
        resultado = await gerar_diagrama(dossie_txt, tipo=tipo_valido)
    except Exception as e:
        raise HTTPException(502, f"Geração de diagrama falhou: {str(e)[:200]}")

    return resultado


# ═══ MOTOR DE ESTRATÉGIA LITIGIOSA — 3 cenários ════════════════════════════

class EstrategiaReq(_BM):
    foco: _Opt[str] = "geral"  # geral|defesa|recurso|acordo|execucao


@router.post("/caso/{case_id}/estrategia")
async def motor_estrategia(
    case_id: str,
    req: EstrategiaReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Motor de Estratégia Litigiosa: gera 3 cenários (conservador, moderado, agressivo).
    Cada cenário tem: abordagem, argumentos principais, riscos, probabilidade estimada
    e linha do tempo. RASCUNHO — revisão humana obrigatória (HITL).
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403)

    caso = (await db.execute(
        select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not caso:
        raise HTTPException(404, "Caso não encontrado")

    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["socio"]:
        if caso.advogado_responsavel_id != cu.id and getattr(caso, "advogado_auxiliar_id", None) != cu.id:
            raise HTTPException(403, "Sem permissão para este caso")

    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag
    from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
    from uuid import uuid4

    dossie = await montar_dossie(db, case_id, incluir_pecas=False, sanitizar=True)
    dossie_txt = dossie["texto"] if dossie else f"Caso {case_id}."

    fontes = await buscar_contexto_rag(db, f"{getattr(caso.area, 'value', '')} estrategia litigiosa", limite=3, scope_client_id=caso.client_id)
    rag_txt = ""
    if fontes:
        rag_txt = "\n[JURISPRUDÊNCIA RELEVANTE]\n" + "\n".join(
            f"- {f['titulo']}: {f['conteudo'][:200]}" for f in fontes
        )

    system = """Você é estrategista jurídico sênior. Elabore 3 cenários estratégicos para o caso.

FORMATO OBRIGATÓRIO:
## CENÁRIO 1 — CONSERVADOR
**Abordagem:** [estratégia de menor risco]
**Argumentos Principais:** [listar 3-5 argumentos]
**Riscos:** [principais riscos]
**Probabilidade Estimada:** [baixa/média/alta com breve justificativa]
**Linha do Tempo:** [estimativa de duração]
**Custo-Benefício:** [análise breve]

## CENÁRIO 2 — MODERADO
[mesmo formato]

## CENÁRIO 3 — AGRESSIVO
**Abordagem:** [estratégia de maior risco/retorno]
[mesmo formato]

## RECOMENDAÇÃO FINAL
[qual cenário recomenda e por quê]

REGRAS:
- Baseie-se EXCLUSIVAMENTE no dossiê fornecido
- Não prometa resultados ("vai ganhar")
- ⚠️ RASCUNHO — revisão do advogado OBRIGATÓRIA"""

    user_msg = f"[DOSSIÊ]\n{dossie_txt[:5000]}{rag_txt}\n\n[FOCO DA ESTRATÉGIA]: {req.foco or 'geral'}"

    # LGPD: sanitiza o input consolidado (o dossiê já vem sanitizado, mas o
    # RAG/foco podem carregar PII) e usa o retorno REAL na flag pii_removida.
    from app.services.sanitizer import sanitizar_pii
    user_msg, houve_pii = sanitizar_pii(user_msg)

    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_msg},
            ],
            task_type="analise_juridica",
            temperature=0.4,
            max_tokens=3500,
        )
    except Exception as e:
        raise HTTPException(502, f"IA indisponível: {str(e)[:200]}")

    log = AILog(
        id=str(uuid4()), user_id=cu.id, case_id=case_id,
        tipo_uso=AITipoUso.analise_caso,
        modelo=resp.modelo,
        prompt_sanitizado=user_msg[:4000],
        pii_removida=houve_pii,
        resposta=resp.texto,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()

    return {
        "ai_log_id":  log.id,
        "estrategia": resp.texto,
        "modelo":     resp.modelo,
        "provedor":   resp.provedor,
        "fallback":   resp.fallback_ativado,
        "aviso": "⚠️ Estratégias geradas por IA — RASCUNHO. Revisão e validação pelo advogado OBRIGATÓRIA.",
    }


@router.post("/analisar-contrato")
async def analisar_contrato_endpoint(
    req: AnaliseContratoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Análise de contrato (Bloco E) — riscos, cláusulas abusivas e lacunas.

    Sanitiza (LGPD) → recupera CC/CDC no RAG → Groq → minuta sob revisão (HITL).
    """
    if len(req.texto_contrato.strip()) < 100:
        raise HTTPException(status_code=422, detail="Contrato muito curto para análise")
    if (req.modo or "").strip().lower() == "comparacao":
        if len((req.texto_contrato_2 or "").strip()) < 100:
            raise HTTPException(
                status_code=422,
                detail="Modo comparação exige 'texto_contrato_2' (mín. 100 caracteres)",
            )
    r = await analisar_contrato(
        db, cu.id, req.texto_contrato, req.tipo_contrato,
        req.nomes_proteger, req.case_id,
        texto_contrato_2=req.texto_contrato_2, modo=req.modo,
    )
    if "erro" in r:
        raise HTTPException(status_code=502, detail=r["erro"])
    return r

@router.post("/detectar-prazos")
async def detectar_prazos(
    req: ResumirDocRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Extração de prazos por IA a partir de texto ou documento."""
    return await extrair_prazos_ia(db, cu.id, req.texto, req.case_id)
