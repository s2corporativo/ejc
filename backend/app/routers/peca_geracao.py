"""
Router: Geração de peças jurídicas com pipeline 7 etapas + SSE streaming.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core import calculo_recibo
from app.core.homologacao_ferramentas import mapa_status, status_ferramenta
from app.models.user import User
from app.models.ai_log import AILog
from app.models.legal_doc import LegalDoc, PecaTipo, PecaStatus
from app.services.peca_service import (
    gerar_peca_pipeline,
    TIPOS_PECA,
    TIPOS_PECA_VALIDOS,
    TIPOS_PECA_GRUPO,
    AREAS_DIREITO,
    AREAS_DIREITO_LABEL,
    NIVEIS_COMPLEXIDADE,
)
from app.services.system_prompts.blocos_condicionais import (
    FLAGS_VALIDAS,
    montar_instrucao_blocos,
)
from app.services.advogado_style_service import montar_instrucoes_estilo_para_prompt
from app.schemas.peca_workflow import ProducaoModoRequest
from app.services.peca_workflow_service import preparar_modo_producao
from app.services.deep_research_service import DeepResearchInput, executar_deep_research
from datetime import date
from uuid import uuid4

router = APIRouter(prefix="/pecas", tags=["Geração de Peças"])
logger = logging.getLogger(__name__)


class GerarPecaRequest(BaseModel):
    tipo_peca: str = Field(..., description=f"Tipo: {', '.join(TIPOS_PECA.keys())}")
    area_direito: str = Field(..., description=f"Área: {', '.join(AREAS_DIREITO)}")
    descricao_fatos: str = Field(..., min_length=50, max_length=10000)
    pedidos: str = Field(..., min_length=10, max_length=3000)
    nomes_proteger: list[str] = Field(default=[], description="Nomes para anonimizar (LGPD)")
    case_id: Optional[str] = None
    instrucoes_adicionais: Optional[str] = Field(None, max_length=1000)
    # Fase B (#3): grau de complexidade da peça — validado contra NIVEIS_COMPLEXIDADE
    # no handler (422 se inválido). Default "comum" (procedimento comum padrão).
    nivel_complexidade: str = Field(
        default="comum",
        description=f"Complexidade: {', '.join(NIVEIS_COMPLEXIDADE)}",
    )
    # Fase B (#2): flags de teses selecionadas MANUALMENTE pelo advogado (override/
    # adição às determinísticas). Flags desconhecidas são ignoradas silenciosamente.
    flags_teses: list[str] = Field(
        default=[],
        description=f"Teses condicionais: {', '.join(sorted(FLAGS_VALIDAS))}",
    )
    # Modos controlados de produção (Livre/Guiado/Molde/Agente — docs/ai/
    # PECAS_MODOS_PRODUCAO_CONTROLADOS.md). Opcional: ausente = modo livre
    # legado. Quando presente, preparar_modo_producao valida ANTES do stream
    # (409 em bloqueio) e as instruções determinísticas entram no pipeline.
    modo_producao: Optional[ProducaoModoRequest] = None


@router.get("/meta")
async def meta_pecas(
    cu: User = Depends(get_current_user),
):
    """Catálogo (fonte única) para o formulário de geração de peças: tipos
    agrupados, áreas do direito e níveis de complexidade. Elimina o espelhamento
    manual desses metadados no frontend. Piso de role igual ao /gerar."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")

    return {
        "tipos": [
            {
                "value": value,
                "label": TIPOS_PECA[value],
                "grupo": TIPOS_PECA_GRUPO[value],
            }
            for value in TIPOS_PECA_VALIDOS
        ],
        "areas": [
            {"value": area, "label": AREAS_DIREITO_LABEL.get(area, area)}
            for area in AREAS_DIREITO
        ],
        "niveis_complexidade": list(NIVEIS_COMPLEXIDADE),
    }


@router.post("/gerar")
async def gerar_peca(
    req: GerarPecaRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Pipeline 7 etapas para geração de peças jurídicas com SSE streaming.
    Retorna Server-Sent Events: step(1-7) → concluido com o documento completo.
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")

    if req.tipo_peca not in TIPOS_PECA:
        raise HTTPException(422, f"Tipo inválido. Use: {', '.join(TIPOS_PECA.keys())}")

    if req.area_direito not in AREAS_DIREITO:
        raise HTTPException(422, f"Área inválida. Use: {', '.join(AREAS_DIREITO)}")

    if req.nivel_complexidade not in NIVEIS_COMPLEXIDADE:
        raise HTTPException(
            422, f"Nível inválido. Use: {', '.join(NIVEIS_COMPLEXIDADE)}"
        )

    escopo_cli = None
    ficha_resumo = ""
    ficha = None
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
        from app.services.ai_service import _escopo_cliente_do_caso
        escopo_cli = await _escopo_cliente_do_caso(db, req.case_id)

        # Ficha de triagem CONFIRMADA do caso: fonte dos sinais determinísticos das
        # teses (#2) E âncora da peça. Carregada sempre que houver caso — o gate
        # abaixo só é fatal quando FICHA_TRIAGEM_OBRIGATORIA.
        from app.services import ficha_triagem_service as fts
        ficha = await fts.ficha_confirmada(db, req.case_id)

        # GATE de qualidade: a peça só nasce ancorada numa ficha de triagem
        # CONFIRMADA (evita "bom modelo no caso errado"). Geração AVULSA (sem
        # case_id) NUNCA é gateada. 409 ANTES de abrir o stream.
        if get_settings().FICHA_TRIAGEM_OBRIGATORIA and ficha is None:
            raise HTTPException(409, detail={
                "detail": "Confirme a Ficha de Triagem do caso antes de gerar "
                          "a peça (gate de qualidade).",
                "need_ficha_triagem": True,
                "case_id": req.case_id,
            })
        if ficha is not None:
            ficha_resumo = fts.resumo_para_prompt(ficha)

    # Fase B (#2) — flags de teses condicionais. DETERMINÍSTICAS a partir de sinais
    # confiáveis (área + ficha CONFIRMADA) + adição/override MANUAL do advogado.
    # União validada contra FLAGS_VALIDAS (desconhecidas ignoradas). Geração avulsa
    # (sem case_id → sem ficha) usa só área + flags manuais.
    flags_teses: set[str] = set()
    if req.area_direito == "consumidor":
        flags_teses.add("relacao_consumo")
    if ficha is not None:
        if ficha.tutela_urgencia:
            flags_teses.add("pedido_tutela")
        if (ficha.provas_disponiveis or "").strip():
            flags_teses.add("prova_documental_suficiente")
    flags_teses.update(req.flags_teses or [])
    flags_teses &= FLAGS_VALIDAS
    bloco_teses = montar_instrucao_blocos(flags_teses)

    # ── Modos controlados (Guiado/Molde/Agente) — contrato ANTES do stream ────
    # A camada é determinística (sem IA, sem banco). Bloqueio = 409 imediato:
    # Guiado com campo obrigatório vazio, Molde sem versão/hash ou com campo
    # simultaneamente preservado e substituído, Agente sem caso autorizado,
    # sem documento considerado ou sem aprovação explícita do plano.
    instrucoes_modo = ""
    if req.modo_producao is not None:
        modo_req = req.modo_producao.model_copy(update={
            # Fonte única: o request externo manda; evita divergência de contrato.
            "case_id": req.case_id,
            "tipo_peca": req.tipo_peca,
            "area_direito": req.area_direito,
        })
        prep = preparar_modo_producao(modo_req)
        if prep.bloqueios:
            raise HTTPException(409, detail={
                "detail": "Produção bloqueada pelo modo selecionado.",
                "modo": prep.modo.value,
                "bloqueios": prep.bloqueios,
                "alertas": prep.alertas,
            })
        instrucoes_modo = prep.instrucoes_pipeline or ""
        # Auditoria exigida pelo contrato: modo, referência do molde e aprovação
        # — só IDs/versão/hash, nunca conteúdo (sem dado sensível em log).
        from app.models.audit_log import criar_audit_log
        molde_ref = None
        if prep.molde is not None:
            molde_ref = {
                "documento_id": prep.molde.referencia.documento_id,
                "versao": prep.molde.referencia.versao,
                "hash_conteudo": prep.molde.referencia.hash_conteudo,
            }
        await criar_audit_log(
            db, cu.id, cu.role.value, "GERAR_PECA_MODO", "pecas",
            req.case_id or "avulsa",
            detalhes=f"Modo de produção {prep.modo.value} validado para geração",
            dados_depois={
                "modo": prep.modo.value,
                "molde": molde_ref,
                "aprovado_para_redacao": modo_req.aprovado_para_redacao,
                "documentos_considerados": [
                    d.documento_id for d in prep.documentos_considerados
                ],
            },
        )

    async def stream():
        try:
            instrucoes = req.instrucoes_adicionais or ""
            if instrucoes_modo:
                # Instruções DETERMINÍSTICAS do modo (preparar_modo_producao):
                # primeiro bloco, antes de ficha/estilo/teses.
                bloco_modo = instrucoes_modo[:2500]
                instrucoes = (
                    f"{bloco_modo}\n\n{instrucoes}" if instrucoes else bloco_modo
                )
            if ficha_resumo:
                # Ancora a peça na triagem confirmada (respeitando o limite).
                bloco = f"[FICHA DE TRIAGEM CONFIRMADA]\n{ficha_resumo}"[:2000]
                instrucoes = (f"{instrucoes}\n\n{bloco}" if instrucoes else bloco)
            estilo = await montar_instrucoes_estilo_para_prompt(db, cu.id)
            if estilo:
                instrucoes = (
                    f"{instrucoes}\n\n[ESTILO DO ADVOGADO]\n{estilo}"
                    if instrucoes else f"[ESTILO DO ADVOGADO]\n{estilo}"
                )[:2500]
            # Teses condicionais (#2) — bloco próprio, DEPOIS do cap do estilo para
            # não ser truncado; auto-limitado (poucas teses + regra curta).
            if bloco_teses:
                bloco_teses_cap = bloco_teses[:2000]
                instrucoes = (
                    f"{instrucoes}\n\n{bloco_teses_cap}" if instrucoes
                    else bloco_teses_cap
                )

            async for chunk in gerar_peca_pipeline(
                db=db,
                user_id=cu.id,
                tipo_peca=req.tipo_peca,
                area_direito=req.area_direito,
                descricao_fatos=req.descricao_fatos,
                pedidos=req.pedidos,
                scope_client_id=escopo_cli,
                nomes_proteger=req.nomes_proteger,
                case_id=req.case_id,
                instrucoes_adicionais=instrucoes,
                nivel_complexidade=req.nivel_complexidade,
            ):
                yield chunk
        except Exception as e:
            import json
            # Detalhe técnico só no log — a UI não deve expor infra interna
            # (nomes de env vars/provedores) ao advogado.
            logger.error("[PecaGeracao] pipeline falhou: %s", e)
            yield (
                "event: erro\ndata: "
                + json.dumps(
                    {"detail": "IA indisponível no momento. Tente novamente "
                               "em instantes ou contate o administrador."},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/")
async def listar_pecas(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    case_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista peças geradas pelo usuário (logs com tipo elaboracao_peca)."""
    from app.models.ai_log import AITipoUso
    from sqlalchemy import func as sqlfunc

    q = select(AILog).where(AILog.tipo_uso == AITipoUso.redacao_peca)

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
            {
                "id": l.id,
                "case_id": l.case_id,
                "modelo": l.modelo,
                "status_hitl": l.status_hitl.value,
                "pii_removida": l.pii_removida,
                "tokens_input": l.tokens_input,
                "tokens_output": l.tokens_output,
                "created_at": l.created_at,
            }
            for l in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class DeepResearchRequest(BaseModel):
    tese: str = Field(..., min_length=10, max_length=1000)
    fatos: str = Field(..., min_length=20, max_length=6000)
    area: Optional[str] = Field(None, max_length=80)
    case_id: Optional[str] = None
    numero_cnj: Optional[str] = Field(None, max_length=30)
    fontes_externas: list[str] = Field(default_factory=lambda: ["lexml", "tjmg"])
    max_subquestoes: int = Field(5, ge=3, le=8)


@router.post("/deep-research/juridica", dependencies=[Depends(rate_limit("deep_research_juridica", 6))])
async def deep_research_juridica(
    req: DeepResearchRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Executa Deep Research jurídica v1 com RAG, precedentes e IA central."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")

    scope_client_id = None
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)
        from app.services.ai_service import _escopo_cliente_do_caso
        scope_client_id = await _escopo_cliente_do_caso(db, req.case_id)

    entrada = DeepResearchInput(
        tese=req.tese,
        fatos=req.fatos,
        area=req.area,
        case_id=req.case_id,
        scope_client_id=scope_client_id,
        numero_cnj=req.numero_cnj,
        fontes_externas=req.fontes_externas,
        max_subquestoes=req.max_subquestoes,
    )
    return await executar_deep_research(db, entrada, user_id=cu.id)


@router.get("/ferramentas/homologacao")
async def listar_homologacao_ferramentas(cu: User = Depends(get_current_user)):
    """Status de homologação por ferramenta (endpoint → status).

    A UI usa isto para sinalizar cada calculadora e desabilitar a geração de
    demonstrativo. Ferramenta ausente do mapa é NÃO homologada (fail-closed).
    """
    return {"status": mapa_status(), "default": "em_revisao"}


class DemonstrativoRequest(BaseModel):
    titulo: str = Field(..., min_length=2, max_length=200)
    base_legal: Optional[str] = Field(None, max_length=300)
    case_id: Optional[str] = None
    # Recibo assinado pelo servidor na execução da calculadora. É a ÚNICA fonte
    # do endpoint de origem e dos números da memória de cálculo: rótulos podem
    # vir do cliente, valores não. Ver app/core/calculo_recibo.py.
    recibo: str = Field(..., min_length=16, max_length=20000)


@router.post("/demonstrativo", status_code=201)
async def gerar_demonstrativo(
    req: DemonstrativoRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Converte o resultado de uma calculadora em um Demonstrativo de Cálculo
    salvo como peça (LegalDoc) rascunho — vinculável a um caso. Reusa a esteira
    de peças existente; resultado é MINUTA (revisão humana obrigatória)."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")
    # PROVENIÊNCIA: o endpoint e os números vêm do recibo assinado na execução da
    # calculadora — não do corpo da requisição. Sem isso, bastaria alegar uma
    # ferramenta homologada para materializar qualquer número (review do PR #495).
    assinado = calculo_recibo.validar(req.recibo)
    if assinado is None:
        raise HTTPException(
            422,
            "Recibo de cálculo ausente, inválido ou expirado. Execute a calculadora "
            "novamente e gere o demonstrativo a partir do resultado exibido.",
        )
    # GATE DE HOMOLOGAÇÃO (auditoria 2026-07-26): calculadora não homologada
    # calcula, mas NÃO vira documento formal — corta o caminho
    # "regra errada → resultado plausível → peça → uso externo".
    hom = status_ferramenta(assinado["endpoint"])
    if hom.status != "homologada":
        raise HTTPException(
            409,
            f"Ferramenta não homologada ({hom.status}): o cálculo serve como apoio, "
            f"mas não pode virar documento formal. "
            + (f"Motivo: {hom.nota} " if hom.nota else "")
            + "A liberação depende de homologação do advogado responsável pela área.",
        )
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)

    # Memória de cálculo derivada do RESULTADO ASSINADO (não do corpo enviado).
    linhas = calculo_recibo.linhas_do_resultado(assinado["resultado"])
    linhas_txt = "\n".join(f"  • {label}: {valor}" for label, valor in linhas) or "  (sem itens)"
    partes = [
        f"DEMONSTRATIVO DE CÁLCULO — {req.titulo}",
        f"\nElaborado em {date.today().strftime('%d/%m/%Y')} por {cu.full_name}"
        + (f" (OAB {cu.oab_number})" if getattr(cu, "oab_number", None) else ""),
        "\nMEMÓRIA DE CÁLCULO:\n" + linhas_txt,
    ]
    if req.base_legal:
        partes.append(f"\nFUNDAMENTO: {req.base_legal}")
    rodape = calculo_recibo.rodape_do_resultado(assinado["resultado"])
    if rodape:
        partes.append(f"\n{rodape}")
    partes.append(
        "\n____________________________________________________________\n"
        "MINUTA gerada a partir de calculadora — revisão humana obrigatória. "
        "Conferir índices, datas-base, correção monetária e juros antes de qualquer uso."
    )
    conteudo = "\n".join(partes)

    doc = LegalDoc(
        id=str(uuid4()),
        titulo=f"Demonstrativo — {req.titulo}"[:255],
        tipo_peca=PecaTipo.outro,
        status=PecaStatus.rascunho,
        conteudo=conteudo,
        ai_generated=False,
        case_id=req.case_id or None,
        created_by=cu.id,
    )
    db.add(doc)
    await db.commit()
    return {"id": doc.id, "titulo": doc.titulo, "conteudo": conteudo,
            "detail": "Demonstrativo salvo como rascunho em Peças."}
