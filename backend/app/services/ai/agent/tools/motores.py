# ── app/services/ai/agent/tools/motores.py ───────────────────────────────────
# FASE 6 (Orquestrador Jurídico) — ferramentas do agente que EMBRULHAM os
# motores DETERMINÍSTICOS já existentes do núcleo. Nada aqui inventa base
# legal/prazo/valor: as tools devolvem VERBATIM o que os motores retornam
# (CATALOGO_PECAS, evento_processual, rito_engine, deadline_calculator,
# taxonomia, geracao_documental, TabelaOABHonorario) — a IA NUNCA reformula.
#
# Padrão IDÊNTICO a leitura.py/escrita.py:
#   • LEITURA  (requer_confirmacao=False) → execução automática no loop.
#   • ESCRITA  (requer_confirmacao=True)  → o loop PAUSA e exige aprovação
#     humana (HITL) vinculada aos ARGS exatos antes de executar (H1).
#   • CADA tool re-verifica RBAC/ownership (verificar_acesso_caso) — o gate de
#     entrada do router não basta (defense-in-depth).
#
# REGRAS INVIOLÁVEIS:
#   • `calcular_prazo` SEMPRE devolve termo_inicial_confirmado=False e NUNCA
#     cria Deadline — prazo fatal só nasce via `criar_prazo_confirmado`, após
#     aprovação humana na pausa HITL (gates de checklist/termo do Motor de
#     Peça reusados via motor_peca_service.confirmar_e_criar_prazo).
#   • Tools determinísticas: nenhuma chamada de LLM acontece aqui.
from __future__ import annotations

import logging
from datetime import date

from app.core.ownership import verificar_acesso_caso
from app.services.ai.agent.tools.context import AgentContext
from app.services.ai.agent.tools.registry import registrar_tool
# Mesma fonte única de papéis sênior das tools de escrita existentes (L9).
from app.services.ai.agent.tools.escrita import _PAPEIS_ESCRITA

logger = logging.getLogger("ejc.ai.agent.motores")

AVISO_CONFIRMACAO_PRAZO = (
    "Prazo PROJETADO deterministicamente — termo_inicial_confirmado=False. "
    "NENHUM prazo (Deadline) foi criado: a confirmação humana do advogado é "
    "OBRIGATÓRIA (após validar o termo nos autos, use criar_prazo_confirmado)."
)


def _iso(v):
    """date/datetime → ISO; demais valores passam intactos."""
    return v.isoformat() if hasattr(v, "isoformat") else v


def _parse_date(valor, campo: str) -> date | None:
    """Converte string ISO em date — ESTRITO: aceita SOMENTE `YYYY-MM-DD` exato
    (len==10 + fromisoformat). None/vazio → None. Alimenta prazo FATAL: valor
    com hora/timezone/ruído levanta ValueError claro (vira {"erro": ...}) em
    vez de ser truncado silenciosamente."""
    if valor in (None, ""):
        return None
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    if len(s) != 10:
        raise ValueError(
            f"{campo} inválido — use EXATAMENTE o formato ISO YYYY-MM-DD")
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise ValueError(
            f"{campo} inválido — use EXATAMENTE o formato ISO YYYY-MM-DD")


def _evento_dict(info: dict | None) -> dict | None:
    """Saída de resolver_termo_inicial com as datas serializadas (verbatim)."""
    if not info:
        return None
    return {**info,
            "data_evento": _iso(info.get("data_evento")),
            "termo_inicial": _iso(info.get("termo_inicial")),
            "inicio_contagem": _iso(info.get("inicio_contagem"))}


def _val(x):
    return x.value if hasattr(x, "value") else x


async def _rito_do_caso(ctx: AgentContext, case, texto: str | None = None) -> dict:
    """Rito determinístico com os MESMOS sinais do Motor de Peça (rito_engine).
    Fonte do texto: texto explícito > OCR dos documentos > descrição dos fatos."""
    from app.services import motor_peca_service as mps
    from app.services.rito_engine import identificar_rito

    texto_base = await mps.texto_base_do_caso(ctx.db, case, texto)
    return identificar_rito({
        "area": _val(getattr(case, "area", None)),
        "texto": (texto_base or "")[:8000],
        "fase": _val(getattr(case, "fase", None)),
        "tribunal": getattr(case, "tribunal", None),
    })


# ══════════════════════════════════════════════════════════════════════════════
# LEITURA / ANÁLISE (sem pausa HITL — determinísticas, sem efeito colateral)
# ══════════════════════════════════════════════════════════════════════════════

@registrar_tool(
    name="montar_cronologia",
    description=(
        "Monta a CRONOLOGIA determinística do caso em contexto: movimentos, "
        "prazos, documentos e honorários, em ordem cronológica (mais antigo "
        "primeiro). Agrega apenas dados REAIS já registrados — nada é inferido "
        "ou inventado. Use para situar o caso no tempo antes de decidir."
    ),
    input_schema={"type": "object", "properties": {}},
    requer_confirmacao=False,
)
async def montar_cronologia(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services.visual_law_core import montar_eventos_caso

    eventos = await montar_eventos_caso(ctx.db, ctx.case_id)
    # montar_eventos_caso devolve mais recente primeiro; cronologia = ascendente.
    eventos.reverse()
    itens = [{
        "data": _iso(e.get("data")),
        "categoria": e.get("categoria"),
        "tipo": e.get("tipo"),
        "descricao": (e.get("descricao") or "")[:240],
    } for e in eventos[:150]]
    return {"total": len(eventos), "ordenacao": "cronologica_ascendente",
            "eventos": itens}


@registrar_tool(
    name="identificar_rito_e_fase",
    description=(
        "Identifica DETERMINISTICAMENTE (rito_engine, sem IA) o rito provável e "
        "a fase/etapa atual do caso em contexto, com etapas da jornada, fontes "
        "normativas base e alertas. Aceita `texto` opcional (ex.: trecho de "
        "intimação) como sinal adicional. O resultado SEMPRE exige confirmação "
        "humana — repita as fontes VERBATIM, nunca as reformule."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "texto": {"type": "string",
                      "description": "Texto opcional (documento/intimação) como sinal adicional."},
        },
    },
    requer_confirmacao=False,
)
async def identificar_rito_e_fase(args: dict, ctx: AgentContext) -> dict:
    case = await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    rito = await _rito_do_caso(ctx, case, (args.get("texto") or "").strip() or None)
    return {"rito": rito, "fase_atual": rito["etapa_atual"],
            "requer_confirmacao_humana": True}


@registrar_tool(
    name="detectar_providencias",
    description=(
        "Detecta DETERMINISTICAMENTE as providências/peças cabíveis para o caso "
        "em contexto (mapa rito+etapa → peças do Motor de Peça), cada uma com "
        "base legal e prazo VERBATIM do catálogo — é PROIBIDO reformular base "
        "legal ou prazo. Lista vazia = sem mapeamento seguro (seleção manual do "
        "advogado; nunca invente peça). Aceita `texto` opcional como sinal."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "texto": {"type": "string",
                      "description": "Texto opcional (documento/intimação) como sinal adicional."},
        },
    },
    requer_confirmacao=False,
)
async def detectar_providencias(args: dict, ctx: AgentContext) -> dict:
    case = await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import motor_peca_service as mps

    rito = await _rito_do_caso(ctx, case, (args.get("texto") or "").strip() or None)
    codigos = mps.pecas_cabiveis(rito["codigo"], rito["etapa_atual"])
    pecas = [mps.descrever_peca(c, rito["codigo"]) for c in codigos]
    return {
        "rito": {"codigo": rito["codigo"], "nome": rito["nome"],
                 "etapa_atual": rito["etapa_atual"], "confianca": rito["confianca"],
                 "alertas": rito["alertas"]},
        "pecas_cabiveis": pecas,
        "pecas_aviso": (None if pecas else
                        "Nenhuma peça mapeada deterministicamente para este "
                        "rito/etapa — selecione a peça manualmente."),
        "requer_confirmacao_humana": True,
    }


@registrar_tool(
    name="calcular_prazo",
    description=(
        "PROJETA o prazo de uma peça do catálogo determinístico do Motor de "
        "Peça a partir de um evento processual (evento+data_evento → termo "
        "inicial via catálogo de eventos, base legal citada) ou de um "
        "termo_inicial explícito informado pelo advogado. NUNCA cria prazo "
        "(Deadline) e SEMPRE devolve termo_inicial_confirmado=false — a "
        "confirmação humana é obrigatória. Repita base legal, datas e avisos "
        "VERBATIM; é PROIBIDO recalcular ou reformular."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "peca_codigo": {"type": "string",
                            "description": "Código da peça no catálogo (ex.: contestacao, apelacao)."},
            "evento": {"type": "string",
                       "description": ("Evento processual do catálogo (ex.: publicacao_dje, "
                                       "juntada_ar, intimacao_eletronica).")},
            "data_evento": {"type": "string",
                            "description": "Data do evento (ISO YYYY-MM-DD)."},
            "meio": {"type": "string",
                     "description": "Qualificador do evento (ex.: consulta, ciencia_em_audiencia)."},
            "termo_inicial": {"type": "string",
                              "description": ("Termo inicial explícito informado pelo advogado "
                                              "(ISO YYYY-MM-DD); tem precedência sobre o evento.")},
            "em_dobro": {"type": "boolean",
                         "description": "Prazo em dobro (CPC arts. 180/183/186)."},
        },
        "required": ["peca_codigo"],
    },
    requer_confirmacao=False,
)
async def calcular_prazo(args: dict, ctx: AgentContext) -> dict:
    case = await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import motor_peca_service as mps

    peca_codigo = (args.get("peca_codigo") or "").strip()
    if peca_codigo not in mps.CATALOGO_PECAS:
        return {"erro": "peca_desconhecida",
                "pecas_validas": sorted(mps.CATALOGO_PECAS.keys())}
    try:
        termo_inicial = _parse_date(args.get("termo_inicial"), "termo_inicial")
        data_evento = _parse_date(args.get("data_evento"), "data_evento")
    except ValueError as e:
        return {"erro": str(e)}

    # Evento processual → termo DERIVADO deterministicamente (base legal citada);
    # termo_inicial explícito tem precedência (regra ÚNICA do Motor de Peça).
    evento = (args.get("evento") or "").strip()
    if evento and not data_evento:
        return {"erro": "evento informado sem data_evento (ISO YYYY-MM-DD)"}
    evento_info, termo_inicial, termo_origem = mps.resolver_termo_evento(
        evento, data_evento, args.get("meio"), termo_inicial)

    # Rito recomputado do caso (overrides por rito — ex.: JEC/trabalhista).
    rito = await _rito_do_caso(ctx, case)
    projecao = mps.calcular_prazo_projetado(
        peca_codigo, rito["codigo"], termo_inicial,
        tribunal=getattr(case, "tribunal", None),
        em_dobro=bool(args.get("em_dobro")),
    )
    projecao["termo_inicial_origem"] = termo_origem
    projecao["rito_codigo"] = rito["codigo"]
    projecao["evento_processual"] = _evento_dict(evento_info)
    # INVARIANTE: nunca confirmado automaticamente; nenhum Deadline criado.
    projecao["termo_inicial_confirmado"] = False
    projecao["pendente_confirmacao_humana"] = True
    projecao["aviso_confirmacao"] = AVISO_CONFIRMACAO_PRAZO
    return projecao


@registrar_tool(
    name="consultar_tabela_oab",
    description=(
        "Consulta os itens VIGENTES da Tabela OAB/MG de honorários para uma "
        "área (ou a área do caso em contexto). Devolve os itens VERBATIM com "
        "fonte — referência NÃO vinculante; o advogado define o valor final. "
        "Sem item aplicável → lista vazia (NUNCA invente valor)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "area": {"type": "string",
                     "description": "Área jurídica (opcional; default = área do caso)."},
        },
    },
    requer_confirmacao=False,
)
async def consultar_tabela_oab(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.core.taxonomia import normalizar_area
    from app.services.geracao_documental import (
        AVISO_SEM_ITEM_OAB, _item_dict, _itens_oab_vigentes,
    )

    bruta = (args.get("area") or "").strip() or (ctx.area or "")
    area = normalizar_area(bruta) or bruta.strip().lower()
    if not area:
        return {"erro": "área não informada e caso sem área definida",
                "total": 0, "itens": []}
    itens = await _itens_oab_vigentes(ctx.db, area, date.today())
    return {
        "area": area,
        "total": len(itens),
        "itens": [_item_dict(i) for i in itens],
        "aviso": ("Referencia da tabela OAB/MG — nao vinculante; o advogado "
                  "define o valor final." if itens else AVISO_SEM_ITEM_OAB),
    }


@registrar_tool(
    name="ler_checklist_peca",
    description=(
        "Monta o CHECKLIST BLOQUEANTE de uma peça do catálogo do Motor de Peça "
        "para o caso em contexto (qualificação do cliente, procuração vigente, "
        "base fática) e informa se está PRONTO para geração. Determinístico — "
        "os itens pendentes bloqueiam criar_prazo_confirmado."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "peca_codigo": {"type": "string",
                            "description": "Código da peça no catálogo (ex.: contestacao)."},
        },
        "required": ["peca_codigo"],
    },
    requer_confirmacao=False,
)
async def ler_checklist_peca(args: dict, ctx: AgentContext) -> dict:
    case = await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import motor_peca_service as mps

    peca_codigo = (args.get("peca_codigo") or "").strip()
    if peca_codigo not in mps.CATALOGO_PECAS:
        return {"erro": "peca_desconhecida",
                "pecas_validas": sorted(mps.CATALOGO_PECAS.keys())}
    texto_base = await mps.texto_base_do_caso(ctx.db, case, None)
    itens, pronto = await mps.montar_checklist(ctx.db, case, peca_codigo, texto_base)
    info = mps.CATALOGO_PECAS[peca_codigo]
    return {
        "peca_codigo": peca_codigo,
        "peca_nome": info["nome"],
        "pressupostos": list(info.get("pressupostos") or []),
        "itens": itens,
        "pronto": pronto,
    }


@registrar_tool(
    name="classificar_area",
    description=(
        "Classifica um texto/rótulo livre para uma ÁREA CANÔNICA do direito "
        "(taxonomia determinística do EJC — sem IA). Devolve a área canônica "
        "ou nulo quando não há correspondência juridicamente segura (a decisão "
        "fica com o advogado; NUNCA presuma área)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "texto": {"type": "string",
                      "description": "Rótulo/termo a normalizar (ex.: 'Direito do Trabalho')."},
        },
        "required": ["texto"],
    },
    requer_confirmacao=False,
)
async def classificar_area(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.core.taxonomia import areas_validas, normalizar_area

    texto = (args.get("texto") or "").strip()
    if not texto:
        return {"erro": "texto vazio", "area": None, "reconhecida": False}
    area = normalizar_area(texto)
    out: dict = {
        "area": area,
        "reconhecida": area is not None,
        "metodo": "taxonomia_deterministica",
    }
    if area is None:
        out["aviso"] = ("Sem correspondência juridicamente segura na taxonomia "
                        "canônica — a classificação fica com o advogado (HITL).")
        out["areas_validas"] = areas_validas()
    return out


# ══════════════════════════════════════════════════════════════════════════════
# ESCRITA (requer_confirmacao=True → o loop PAUSA e exige aprovação humana/HITL
# vinculada aos ARGS exatos antes de executar — H1). Papéis sênior apenas (L9).
# ══════════════════════════════════════════════════════════════════════════════

@registrar_tool(
    name="criar_prazo_confirmado",
    description=(
        "Cria o PRAZO FATAL (Deadline) de uma peça do catálogo do Motor de "
        "Peça. EFEITO COLATERAL REAL — o sistema PAUSA e exige aprovação "
        "humana dos argumentos exatos (a aprovação do advogado É a confirmação "
        "do termo inicial). Reusa os gates INVIOLÁVEIS do Motor de Peça: "
        "checklist bloqueante e termo determinável (evento do catálogo ou "
        "termo_inicial explícito; prazo 'verificar' exige data_prazo_manual). "
        "Antes de propor, projete com calcular_prazo e confira o checklist."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "peca_codigo": {"type": "string",
                            "description": "Código da peça no catálogo (ex.: contestacao)."},
            "termo_inicial": {"type": "string",
                              "description": ("Termo inicial (dies a quo) validado nos autos "
                                              "(ISO YYYY-MM-DD); precedência sobre o evento.")},
            "evento": {"type": "string",
                       "description": "Evento processual do catálogo que deriva o termo."},
            "data_evento": {"type": "string", "description": "Data do evento (ISO YYYY-MM-DD)."},
            "meio": {"type": "string",
                     "description": "Qualificador do evento (ex.: consulta, ciencia_em_audiencia)."},
            "data_prazo_manual": {"type": "string",
                                  "description": ("Data fatal manual (ISO) — obrigatória quando o "
                                                  "prazo da peça/rito é contagem='verificar'.")},
            "em_dobro": {"type": "boolean",
                         "description": "Prazo em dobro (CPC arts. 180/183/186)."},
        },
        "required": ["peca_codigo"],
    },
    requer_confirmacao=True,
    roles=_PAPEIS_ESCRITA,
)
async def criar_prazo_confirmado(args: dict, ctx: AgentContext) -> dict:
    case = await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import motor_peca_service as mps

    try:
        termo_inicial = _parse_date(args.get("termo_inicial"), "termo_inicial")
        data_evento = _parse_date(args.get("data_evento"), "data_evento")
        data_prazo_manual = _parse_date(args.get("data_prazo_manual"), "data_prazo_manual")
    except ValueError as e:
        return {"erro": str(e)}

    try:
        # Este handler SÓ roda após a aprovação humana na pausa HITL (o loop
        # vincula a aprovação aos ARGS exatos — H1): a aprovação do advogado É
        # a confirmação do termo inicial (termo_inicial_confirmado=True).
        # Os DEMAIS gates do Motor de Peça (checklist, termo determinável)
        # seguem valendo dentro do service — fonte única com o router /gerar.
        confirmado = await mps.confirmar_e_criar_prazo(
            ctx.db, ctx.user, case,
            peca_codigo=(args.get("peca_codigo") or "").strip(),
            termo_inicial=termo_inicial,
            evento=(args.get("evento") or "").strip() or None,
            data_evento=data_evento,
            meio=args.get("meio"),
            termo_inicial_confirmado=True,
            data_prazo_manual=data_prazo_manual,
            em_dobro=bool(args.get("em_dobro")),
            # A tool NÃO redige peça — base fática não é exigida para o prazo.
            exigir_base_fatica=False,
            origem="agente_juridico",
        )
    except mps.GateBloqueado as e:
        # Mesmo payload estruturado que o router devolve em 422 — o agente
        # relata ao advogado o que falta (nada foi persistido).
        return {"criado": False, "erro": "gate_bloqueado", "detalhe": e.detail}

    deadline = confirmado["deadline"]
    prazo_info = confirmado["prazo_info"]
    logger.info("[agent] prazo confirmado criado no caso %s (deadline %s)",
                ctx.case_id, deadline.id)
    return {
        "criado": True,
        "deadline": {
            "id": deadline.id,
            "titulo": deadline.titulo,
            "data_prazo": _iso(confirmado["data_prazo"]),
            "base_legal": deadline.base_legal,
            "tipo": _val(deadline.tipo),
            "confirmado": True,
            "termo_inicial": _iso(confirmado["termo_inicial"]),
        },
        "rito_codigo": confirmado["rito_codigo"],
        "evento_processual": _evento_dict(confirmado["evento_info"]),
        "prazo_info": {**prazo_info},
        "termo_inicial_confirmado": True,
        "aviso": ("Prazo criado após confirmação humana (HITL). Conferir "
                  "intimação/citação nos autos."),
    }


@registrar_tool(
    name="gerar_kit_documental",
    description=(
        "Gera o KIT DOCUMENTAL inicial do caso (procuração + contrato de "
        "honorários com referência da Tabela OAB/MG + checklist documental) por "
        "preenchimento DETERMINÍSTICO de template — sem redação por IA. "
        "EFEITO COLATERAL REAL (persiste rascunhos LegalDoc) — o sistema PAUSA "
        "e exige aprovação humana. Tudo nasce RASCUNHO sujeito a revisão; "
        "poderes especiais do CPC art. 105 só com tipo_poderes explícito."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tipo_poderes": {"type": "string",
                             "description": ("ad_judicia (default), ad_judicia_et_extra "
                                             "ou especiais.")},
            "permite_substabelecimento": {"type": "boolean",
                                          "description": "Default true."},
            "poderes_especiais": {"type": "string",
                                  "description": "Texto dos poderes especiais (se tipo=especiais)."},
        },
    },
    requer_confirmacao=True,
    roles=_PAPEIS_ESCRITA,
)
async def gerar_kit_documental(args: dict, ctx: AgentContext) -> dict:
    case = await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.models.client import Client
    from app.services.geracao_documental import gerar_kit_inicial

    tipo_poderes = (args.get("tipo_poderes") or "ad_judicia").strip().lower()
    validos = {"ad_judicia", "ad_judicia_et_extra", "especiais"}
    if tipo_poderes not in validos:
        return {"erro": "tipo_poderes_invalido", "validos": sorted(validos)}

    cli = await ctx.db.get(Client, case.client_id) if case.client_id else None
    if cli is None or getattr(cli, "deleted_at", None) is not None:
        return {"erro": "cliente_do_caso_nao_encontrado"}

    kit = await gerar_kit_inicial(
        ctx.db, case, cli, ctx.user,
        tipo_poderes=tipo_poderes,
        permite_substabelecimento=bool(args.get("permite_substabelecimento", True)),
        poderes_especiais=(args.get("poderes_especiais") or "").strip() or None,
    )
    logger.info("[agent] kit documental gerado no caso %s (rascunhos)", ctx.case_id)
    # Resumo para o loop (os textos completos ficam nos LegalDoc rascunhos):
    return {
        "criado": True,
        "status": kit.get("status"),
        "aviso": kit.get("aviso"),
        "procuracao": {k: v for k, v in (kit.get("procuracao") or {}).items()
                       if k != "conteudo"},
        "contrato": {k: v for k, v in (kit.get("contrato") or {}).items()
                     if k != "conteudo"},
        "checklist": {k: v for k, v in (kit.get("checklist") or {}).items()
                      if k != "conteudo"},
    }
