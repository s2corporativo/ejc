# ── app/services/ai/agent/tools/leitura.py ───────────────────────────────────
# Ferramentas READ-ONLY do agente (requer_confirmacao=False → execução
# automática). CADA uma re-verifica RBAC/ownership (verificar_acesso_caso) — o
# gate de entrada do router não basta (defense-in-depth). Elas apenas EMBRULHAM
# serviços existentes do núcleo (RAG isolado por cliente; dossiê estratégico).
from __future__ import annotations

import logging

from app.core.ownership import verificar_acesso_caso
from app.services.ai.agent.tools.context import AgentContext
from app.services.ai.agent.tools.registry import registrar_tool

logger = logging.getLogger("ejc.ai.agent.leitura")


@registrar_tool(
    name="buscar_precedentes",
    description=(
        "Busca precedentes/jurisprudência e conhecimento interno na base RAG, "
        "ISOLADA ao cliente do caso em contexto. Use para FUNDAMENTAR análise e "
        "estratégia. Retorna trechos com título, categoria, fonte e score. "
        "NUNCA invente fonte: use apenas o que voltar desta ferramenta."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "consulta": {"type": "string", "description": "Termos/tese a pesquisar."},
            "area": {"type": "string", "description": "Categoria/área opcional (ex.: trabalhista, civel)."},
        },
        "required": ["consulta"],
    },
    requer_confirmacao=False,
)
async def buscar_precedentes(args: dict, ctx: AgentContext) -> dict:
    # Re-checagem de ownership (fail-closed): nunca confiar só no gate do router.
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso

    consulta = (args.get("consulta") or "").strip()
    if not consulta:
        return {"erro": "consulta vazia", "total": 0, "trechos": []}
    categorias = None
    area = (args.get("area") or "").strip()
    if area:
        categorias = [area]
    # Escopo de isolamento do RAG = client_id do PRÓPRIO caso (nunca de outro).
    scope = await _escopo_cliente_do_caso(ctx.db, ctx.case_id)
    trechos = await buscar_contexto_rag(
        ctx.db, consulta, limite=6, categorias=categorias,
        modo_or=True, scope_client_id=scope,
        # C4: conteúdo privado restrito ao CASO em contexto (não só ao cliente).
        scope_case_id=ctx.case_id,
    )
    # I5/B4: as fontes ficam no contexto do agente para o gate de citações
    # final e para a trilha do AILog (fontes_rag).
    ctx.registrar_fontes(trechos)
    resumo = [{
        "titulo": t.get("titulo"),
        "categoria": t.get("categoria"),
        "fonte": t.get("fonte"),
        "score": t.get("score"),
        "trecho": (t.get("conteudo") or "")[:1200],
    } for t in (trechos or [])]
    return {"total": len(resumo), "trechos": resumo}


@registrar_tool(
    name="ler_dossie",
    description=(
        "Lê o dossiê estratégico JÁ EXISTENTE do caso em contexto (fatos, "
        "financeiro, andamentos, checklists e enriquecimento por IA da última "
        "versão salva). Use para uma visão geral antes de decidir a estratégia. "
        "Se ainda não houver dossiê salvo, informa isso (não gera um novo)."
    ),
    input_schema={"type": "object", "properties": {}},
    requer_confirmacao=False,
)
async def ler_dossie(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import dossie_service

    # S3/M2: LEITURA PURA — lê a ÚLTIMA versão persistida SEM regenerar. Antes esta
    # tool chamava gerar_dossie, que PERSISTE um DossieEstrategico + AILog (escrita
    # sob rótulo de leitura). Agora nenhuma escrita/IA/AILog ocorre numa tool de
    # leitura (efeito colateral zero, coerente com requer_confirmacao=False).
    dossie = await dossie_service.ler_ultimo_dossie(ctx.db, ctx.case_id)
    if dossie is None:
        return {
            "existe": False,
            "conteudo": "",
            "nota": "Nenhum dossiê estratégico salvo para este caso. "
                    "Gere um dossiê pela tela do caso antes de consultá-lo aqui.",
        }
    conteudo = (
        getattr(dossie, "conteudo_texto", None)
        or getattr(dossie, "conteudo_html", None)
        or ""
    )
    return {
        "existe": True,
        "versao": getattr(dossie, "versao", None),
        "titulo": getattr(dossie, "titulo", None),
        "conteudo": conteudo[:8000],
    }


# ══════════════════════════════════════════════════════════════════════════════
# LEITURA PROFUNDA DOS AUTOS (2026-09-05, decisão do titular): o agente passa a
# poder ler o que o advogado lê — documentos do caso na íntegra, busca textual
# nos autos, movimentação processual e verificação de citações. Todas embrulham
# serviços/modelos existentes; nenhuma cria dado. RBAC/ownership re-checado em
# cada uma; confidencialidade de documento respeita document_access_policy.
# ══════════════════════════════════════════════════════════════════════════════

_MAX_TEXTO_DOCUMENTO = 20_000     # chars devolvidos por leitura (o loop pagina se precisar)
_MAX_DOCUMENTOS_LISTA = 100
_MAX_DOCS_BUSCA = 20
_MAX_TRECHOS_POR_DOC = 3
_JANELA_TRECHO = 220
_MAX_MOVIMENTOS = 60


def _like_escape(termo: str) -> str:
    """Escapa curingas do LIKE para o termo ser tratado literalmente."""
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _palavras_busca(consulta: str) -> list[str]:
    """Palavras com ≥3 chars, sem duplicatas, na ordem informada (máx. 6)."""
    vistas: list[str] = []
    for p in (consulta or "").split():
        p = p.strip().strip(",.;:!?()[]{}\"'").lower()
        if len(p) >= 3 and p not in vistas:
            vistas.append(p)
    return vistas[:6]


def _trechos(texto: str, palavras: list[str], *, max_trechos: int = _MAX_TRECHOS_POR_DOC,
             janela: int = _JANELA_TRECHO) -> list[str]:
    """Recorta janelas de contexto em torno das primeiras ocorrências das palavras."""
    if not texto or not palavras:
        return []
    baixo = texto.lower()
    saida: list[str] = []
    cursor = 0
    for palavra in palavras:
        pos = baixo.find(palavra, cursor)
        if pos < 0:
            pos = baixo.find(palavra)
        if pos < 0:
            continue
        ini = max(0, pos - janela)
        fim = min(len(texto), pos + len(palavra) + janela)
        trecho = ("…" if ini > 0 else "") + texto[ini:fim].strip() + ("…" if fim < len(texto) else "")
        if trecho not in saida:
            saida.append(trecho)
        cursor = fim
        if len(saida) >= max_trechos:
            break
    return saida


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


@registrar_tool(
    name="listar_documentos",
    description=(
        "Lista os documentos do caso em contexto (id, título, tipo, versão e se "
        "há texto extraído). Use ANTES de `ler_documento` para escolher o que ler. "
        "Respeita a confidencialidade: só devolve o que o advogado pode ver."
    ),
    input_schema={"type": "object", "properties": {}},
    requer_confirmacao=False,
)
async def listar_documentos(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from sqlalchemy import select
    from app.models.document import Document
    from app.services.document_access_policy import confidencialidades_visiveis

    q = (
        select(Document)
        .where(
            Document.case_id == ctx.case_id,
            Document.deleted_at.is_(None),
            Document.confidencialidade.in_(confidencialidades_visiveis(ctx.user)),
        )
        .order_by(Document.created_at.desc())
        .limit(_MAX_DOCUMENTOS_LISTA)
    )
    docs = (await ctx.db.execute(q)).scalars().all()
    return {
        "total": len(docs),
        "documentos": [{
            "id": d.id,
            "titulo": d.titulo,
            "tipo": d.tipo,
            "versao": getattr(d, "versao", None),
            "tem_texto": bool(d.ocr_text),
            "criado_em": _iso(getattr(d, "created_at", None)),
        } for d in docs],
    }


@registrar_tool(
    name="ler_documento",
    description=(
        "Lê o TEXTO INTEGRAL (extraído/OCR) de um documento do caso em contexto, "
        "pelo id devolvido por `listar_documentos`. Use para fundamentar análise "
        "em prova real (contrato, decisão, laudo), não em resumo. Documentos "
        "longos vêm truncados em 20 mil caracteres, com aviso."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "documento_id": {"type": "string", "description": "Id do documento (de listar_documentos)."},
        },
        "required": ["documento_id"],
    },
    requer_confirmacao=False,
)
async def ler_documento(args: dict, ctx: AgentContext) -> dict:
    from fastapi import HTTPException
    from app.services.document_access_policy import exigir_documento_acessivel_no_caso

    documento_id = (args.get("documento_id") or "").strip()
    if not documento_id:
        return {"erro": "documento_id vazio"}
    try:
        # Valida ownership do caso E os invariantes documento↔caso/confidencialidade.
        doc = await exigir_documento_acessivel_no_caso(
            ctx.db, ctx.user, document_id=documento_id, case_id=ctx.case_id)
    except HTTPException as e:
        # Mensagem genérica (não revela a que caso/cliente pertence o id).
        return {"erro": "documento_inacessivel", "status": e.status_code}
    texto = doc.ocr_text or ""
    if not texto.strip():
        return {
            "id": doc.id, "titulo": doc.titulo, "tipo": doc.tipo, "tem_texto": False,
            "nota": "Documento sem texto extraído (OCR pendente ou arquivo não textual).",
        }
    return {
        "id": doc.id,
        "titulo": doc.titulo,
        "tipo": doc.tipo,
        "versao": getattr(doc, "versao", None),
        "tem_texto": True,
        "total_caracteres": len(texto),
        "truncado": len(texto) > _MAX_TEXTO_DOCUMENTO,
        "texto": texto[:_MAX_TEXTO_DOCUMENTO],
    }


@registrar_tool(
    name="buscar_nos_autos",
    description=(
        "Busca palavras/termos no TEXTO dos documentos do caso em contexto e "
        "devolve, por documento, trechos com o contexto em volta. Use para "
        "localizar cláusula, data, valor ou fato específico antes de afirmar "
        "que ele existe (ou não) nos autos. Todas as palavras (≥3 letras) "
        "precisam ocorrer no documento."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "consulta": {"type": "string", "description": "Palavras a localizar (ex.: 'cláusula penal multa')."},
        },
        "required": ["consulta"],
    },
    requer_confirmacao=False,
)
async def buscar_nos_autos(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from sqlalchemy import select
    from app.models.document import Document
    from app.services.document_access_policy import confidencialidades_visiveis

    palavras = _palavras_busca(args.get("consulta") or "")
    if not palavras:
        return {"erro": "consulta sem palavras com 3+ letras", "total": 0, "resultados": []}
    q = select(Document).where(
        Document.case_id == ctx.case_id,
        Document.deleted_at.is_(None),
        Document.ocr_text.is_not(None),
        Document.confidencialidade.in_(confidencialidades_visiveis(ctx.user)),
    )
    for p in palavras:
        q = q.where(Document.ocr_text.ilike(f"%{_like_escape(p)}%", escape="\\"))
    q = q.order_by(Document.created_at.desc()).limit(_MAX_DOCS_BUSCA)
    docs = (await ctx.db.execute(q)).scalars().all()
    resultados = [{
        "documento_id": d.id,
        "titulo": d.titulo,
        "tipo": d.tipo,
        "trechos": _trechos(d.ocr_text or "", palavras),
    } for d in docs]
    return {"palavras": palavras, "total": len(resultados), "resultados": resultados}


@registrar_tool(
    name="verificar_citacoes",
    description=(
        "Verifica CADA citação jurídica de um texto (súmula, artigo de lei, nº "
        "CNJ, precedente) contra a base oficial interna e devolve o status de "
        "cada uma (confirmada / identificada / não localizada / superada). Use "
        "ANTES de concluir uma minuta ou análise: citação não confirmada deve "
        "virar 'verificar fonte' no texto final, nunca afirmação."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "texto": {"type": "string", "description": "Texto (minuta/análise) cujas citações serão verificadas."},
        },
        "required": ["texto"],
    },
    requer_confirmacao=False,
)
async def verificar_citacoes(args: dict, ctx: AgentContext) -> dict:
    await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from app.services import verificador_jurisprudencia as vj

    texto = (args.get("texto") or "").strip()
    if not texto:
        return {"erro": "texto vazio"}
    # consultar_datajud=False: verificação DETERMINÍSTICA e local (base oficial
    # interna); a confirmação externa de nº CNJ fica para o fluxo de auditoria.
    return await vj.verificar_jurisprudencia(ctx.db, texto[:60_000], consultar_datajud=False)


@registrar_tool(
    name="consultar_movimentacao",
    description=(
        "Devolve a movimentação processual do caso em contexto registrada no "
        "sistema (mais recente primeiro) e, se `incluir_tribunal` for true e o "
        "caso tiver nº CNJ, também os movimentos públicos do tribunal via "
        "DataJud/CNJ (quando a integração estiver ativa). Use para saber a fase "
        "real e a última decisão antes de propor providência."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "incluir_tribunal": {"type": "boolean",
                                 "description": "Consultar também o DataJud (padrão false)."},
        },
    },
    requer_confirmacao=False,
)
async def consultar_movimentacao(args: dict, ctx: AgentContext) -> dict:
    case = await verificar_acesso_caso(ctx.db, ctx.user, ctx.case_id)
    from sqlalchemy import select
    from app.models.case import CaseMovimento

    q = (
        select(CaseMovimento)
        .where(CaseMovimento.case_id == ctx.case_id)
        .order_by(CaseMovimento.data_evento.desc())
        .limit(_MAX_MOVIMENTOS)
    )
    movs = (await ctx.db.execute(q)).scalars().all()
    numero = getattr(case, "numero_processo", None)
    saida: dict = {
        "numero_processo": numero,
        "tribunal": getattr(case, "tribunal", None),
        "total_local": len(movs),
        "movimentos": [{
            "data": _iso(getattr(m, "data_evento", None)),
            "tipo": m.tipo,
            "descricao": (m.descricao or "")[:600],
        } for m in movs],
    }
    if args.get("incluir_tribunal"):
        if not numero:
            saida["tribunal_publico"] = {"indisponivel": True, "motivo": "caso sem número CNJ"}
        else:
            from app.services import datajud_service as dj
            try:
                tj = await dj.consultar_movimentos(numero)
                saida["tribunal_publico"] = {
                    "fonte": "DataJud/CNJ", "total": len(tj), "movimentos": tj[-40:],
                }
            except dj.DataJudDesabilitadoError:
                saida["tribunal_publico"] = {"indisponivel": True,
                                             "motivo": "integração DataJud desativada ou sem chave"}
            except dj.TribunalNaoMapeadoError:
                saida["tribunal_publico"] = {"indisponivel": True,
                                             "motivo": "tribunal do nº CNJ sem alias DataJud"}
            except Exception as e:  # rede/HTTP: degrada, nunca derruba o agente
                logger.warning("consultar_movimentacao: DataJud falhou: %s", str(e)[:160])
                saida["tribunal_publico"] = {"indisponivel": True, "motivo": "falha na consulta externa"}
    return saida
