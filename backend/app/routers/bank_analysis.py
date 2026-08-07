# ── app/routers/bank_analysis.py ─────────────────────────────────────────────
# Módulo de Análise Bancária (extratos) — upload → parse → detecta cobranças
# abusivas → Excel + documentos jurídicos. Determinístico (sem IA).
from __future__ import annotations
import os
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Body
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi.responses import StreamingResponse
import json

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.bank_analysis import BankAnalysis, BankTransaction, BankAbusiveCharge
from app.services.bank_statement import parse_extrato, detectar_abusivas
from app.services import bank_report
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.core.rate_limit import rate_limit
import logging

logger = logging.getLogger("ejc.bank_analysis")
router = APIRouter(prefix="/bank-analysis", tags=["Análise Bancária (Extratos)"])
settings = get_settings()


def _fmt_de_nome(nome: str) -> str:
    ext = os.path.splitext(nome or "")[1].lower().lstrip(".")
    return {"ofx": "ofx", "csv": "csv", "txt": "csv", "pdf": "pdf"}.get(ext, "")


@router.post("/upload", status_code=201)
async def upload(
    file: UploadFile = File(...),
    banco: str = Form(""),
    formato: str = Form(""),
    case_id: str = Form(""),
    client_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # IDOR: análise vinculada a caso exige acesso ao caso ANTES de persistir.
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)
    # IDOR (pente fino 2026-07-25): client_id do form também exige visibilidade
    # de carteira — antes era persistido sem checagem, permitindo vincular dado
    # financeiro sensível a cliente alheio. 404 uniforme (não confirma existência).
    if client_id:
        from app.core.client_ownership import obter_cliente_autorizado
        await obter_cliente_autorizado(db, cu, client_id)
    fmt = (formato or _fmt_de_nome(file.filename or "")).lower()
    if fmt not in ("ofx", "csv", "pdf"):
        raise HTTPException(422, "Formato não suportado (use PDF, OFX ou CSV)")
    conteudo = await file.read()
    if len(conteudo) > 25 * 1024 * 1024:
        raise HTTPException(413, "Arquivo excede 25MB")

    aid = str(uuid4())
    try:
        if fmt == "pdf":
            os.makedirs(f"{settings.UPLOAD_DIR}/bank", exist_ok=True)
            caminho = f"{settings.UPLOAD_DIR}/bank/{aid}.pdf"
            with open(caminho, "wb") as f:
                f.write(conteudo)
            transacoes = parse_extrato("pdf", caminho)
        else:
            try:
                texto = conteudo.decode("utf-8")
            except UnicodeDecodeError:
                texto = conteudo.decode("latin-1", errors="ignore")
            transacoes = parse_extrato(fmt, texto)
    except Exception as e:
        raise HTTPException(422, f"Falha ao ler o extrato: {e}")

    if not transacoes:
        raise HTTPException(422, "Nenhuma transação reconhecida no arquivo. "
                                 "Para PDF, tente exportar em OFX/CSV do app do banco.")

    # ids p/ ligar cobranças às transações
    for t in transacoes:
        t["_id"] = str(uuid4())
    cobrancas = detectar_abusivas(transacoes)

    datas = [t["data"] for t in transacoes if t.get("data")]
    creditos = sum(t["valor"] for t in transacoes if t["tipo"] == "credito" and t["valor"])
    debitos = sum(t["valor"] for t in transacoes if t["tipo"] == "debito" and t["valor"])
    total_abusivo = sum(c["valor"] for c in cobrancas if c.get("valor"))

    db.add(BankAnalysis(
        id=aid, case_id=case_id or None, client_id=client_id or None,
        banco=banco or None, formato=fmt, arquivo_nome=(file.filename or "")[:255],
        periodo_inicio=min(datas) if datas else None,
        periodo_fim=max(datas) if datas else None,
        total_transacoes=len(transacoes),
        total_creditos=round(creditos, 2), total_debitos=round(debitos, 2),
        total_abusivo=round(total_abusivo, 2), qtd_abusivas=len(cobrancas),
        status="concluido", created_by=cu.id,
    ))
    for t in transacoes:
        db.add(BankTransaction(
            id=t["_id"], analysis_id=aid, data=t.get("data"),
            descricao=t.get("descricao"), valor=t.get("valor"),
            tipo=t.get("tipo"), saldo=t.get("saldo"),
        ))
    for c in cobrancas:
        db.add(BankAbusiveCharge(
            id=str(uuid4()), analysis_id=aid,
            transaction_id=(c.get("transaction") or {}).get("_id"),
            regra=c.get("regra"), titulo=c.get("titulo"),
            descricao=c.get("descricao"), base_legal=c.get("base_legal"),
            prioridade=c.get("prioridade"), valor=c.get("valor"),
        ))
    await db.commit()
    return await detalhe(aid, db, cu)


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user),
):
    # IDOR (auditoria 2026-06-30): não-gestão só vê as próprias análises
    # (extrato bancário = dado sensível do cliente).
    escopo = "" if is_gestao(cu) else " AND created_by = :uid"
    params = {"l": page_size, "o": (page - 1) * page_size}
    if not is_gestao(cu):
        params["uid"] = cu.id
    total = (await db.execute(
        text(f"SELECT count(*) FROM bank_analyses WHERE deleted_at IS NULL{escopo}"),
        ({"uid": cu.id} if not is_gestao(cu) else {}),
    )).scalar()
    rows = (await db.execute(text(f"""
        SELECT id, banco, formato, arquivo_nome, periodo_inicio, periodo_fim,
               total_transacoes, total_abusivo, qtd_abusivas, status, created_at
        FROM bank_analyses WHERE deleted_at IS NULL{escopo}
        ORDER BY created_at DESC LIMIT :l OFFSET :o
    """), params)).mappings().all()
    return {"total": total, "page": page, "data": [dict(r) for r in rows]}


@router.get("/{analysis_id}")
async def detalhe(analysis_id: str, db: AsyncSession = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    a = (await db.execute(select(BankAnalysis).where(
        BankAnalysis.id == analysis_id, BankAnalysis.deleted_at.is_(None)))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Análise não encontrada")
    # IDOR: análise vinculada a caso exige acesso ao caso; órfã → gestão/criador.
    if a.case_id:
        await verificar_acesso_caso(db, cu, a.case_id)
    elif not (is_gestao(cu) or a.created_by == cu.id):
        raise HTTPException(403, "Sem permissão para esta análise")
    txs = (await db.execute(select(BankTransaction).where(
        BankTransaction.analysis_id == analysis_id).order_by(BankTransaction.data))).scalars().all()
    chs = (await db.execute(select(BankAbusiveCharge).where(
        BankAbusiveCharge.analysis_id == analysis_id))).scalars().all()
    return {
        "analise": {c.name: getattr(a, c.name) for c in a.__table__.columns},
        "transacoes": [{c.name: getattr(t, c.name) for c in t.__table__.columns} for t in txs],
        "cobrancas": [{c.name: getattr(x, c.name) for c in x.__table__.columns} for x in chs],
    }


@router.get("/{analysis_id}/excel")
async def excel(analysis_id: str, db: AsyncSession = Depends(get_db),
                cu: User = Depends(get_current_user)):
    d = await detalhe(analysis_id, db, cu)
    transacoes = [{"data": t["data"], "descricao": t["descricao"], "valor": float(t["valor"] or 0),
                   "tipo": t["tipo"], "saldo": (float(t["saldo"]) if t["saldo"] is not None else None)}
                  for t in d["transacoes"]]
    cobrancas = [{"regra": c["regra"], "titulo": c["titulo"], "base_legal": c["base_legal"],
                  "prioridade": c["prioridade"], "valor": float(c["valor"] or 0),
                  "transaction": {"data": c.get("data")}} for c in d["cobrancas"]]
    xls = bank_report.gerar_excel(d["analise"], transacoes, cobrancas)
    nome = f"analise_bancaria_{analysis_id[:8]}.xlsx"
    return Response(content=xls,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.post("/{analysis_id}/documento")
async def documento(analysis_id: str, payload: dict = Body(default={}),
                    db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    tipo = (payload.get("tipo") or "notificacao").lower()
    if tipo not in ("notificacao", "peticao", "bacen"):
        raise HTTPException(422, "tipo deve ser notificacao|peticao|bacen")
    d = await detalhe(analysis_id, db, cu)
    cobrancas = [{"titulo": c["titulo"], "base_legal": c["base_legal"], "valor": float(c["valor"] or 0),
                  "transaction": {"data": c.get("data")}} for c in d["cobrancas"]]
    html_doc = bank_report.gerar_documento(tipo, d["analise"], cobrancas, payload.get("dados") or {})
    return {"tipo": tipo, "html": html_doc}


def _fmt_brl(valor) -> str:
    from app.utils.format import formatar_brl  # #41: formatador BRL único
    return formatar_brl(valor)


def _montar_contexto_revisional(analise: dict, cobrancas: list[dict],
                                expurgo_texto: str | None = None) -> tuple[str, str]:
    """Monta (descricao_fatos, pedidos) para o gerador de peças a partir dos
    achados de cobranças abusivas. Apenas ESTRUTURA o contexto — a redação e a
    sanitização LGPD ficam a cargo de gerar_peca_pipeline (esteira de peças).
    ``expurgo_texto`` (opcional): parágrafo determinístico do motor de
    abusividade (abusividade_service.formatar_expurgo_para_peca) com os números
    do recálculo pela taxa média BACEN — quando presente, entra nos fatos e
    acrescenta o pedido de limitação dos juros à média de mercado."""
    banco = analise.get("banco") or "instituição financeira"
    pini = analise.get("periodo_inicio")
    pfim = analise.get("periodo_fim")
    periodo = (f" no período de {pini} a {pfim}" if pini and pfim else "")
    total_abusivo = analise.get("total_abusivo")

    linhas = []
    for c in cobrancas:
        prio = (c.get("prioridade") or "").strip()
        titulo = c.get("titulo") or c.get("regra") or "Cobrança"
        desc = (c.get("descricao") or "").strip()
        base = (c.get("base_legal") or "").strip()
        partes = [f"[{prio}] {titulo}" if prio else titulo]
        if desc:
            partes.append(desc)
        partes.append(f"Valor cobrado: {_fmt_brl(c.get('valor'))}")
        if base:
            partes.append(f"Base legal: {base}")
        linhas.append(" — ".join(partes))

    descricao_fatos = (
        f"Da análise do extrato bancário do consumidor junto ao(à) {banco}{periodo}, "
        f"foram identificadas {len(cobrancas)} cobrança(s) potencialmente abusiva(s), "
        f"totalizando {_fmt_brl(total_abusivo)} em débitos indevidos. "
        "As cobranças abusivas detectadas, com respectiva fundamentação, são:\n"
        + "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(linhas))
        + "\n\nTais lançamentos oneram indevidamente o consumidor, em desacordo com a "
        "legislação consumerista e as normas do Conselho Monetário Nacional/BACEN, "
        "justificando a revisão do contrato bancário e a repetição do indébito."
    )
    if expurgo_texto:
        descricao_fatos += "\n\n" + expurgo_texto

    pedidos = (
        "a) a declaração de abusividade e nulidade das cobranças acima discriminadas;\n"
        "b) a revisão do contrato bancário para expurgo dos encargos abusivos;\n"
        "c) a condenação da instituição financeira à repetição do indébito, com a "
        "devolução em dobro dos valores cobrados indevidamente, nos termos do art. 42, "
        f"parágrafo único, do CDC, totalizando {_fmt_brl(total_abusivo)} (a apurar em "
        "liquidação), acrescidos de correção monetária e juros legais;\n"
        "d) subsidiariamente, a devolução simples dos valores indevidamente debitados."
    )
    if expurgo_texto:
        pedidos += (
            "\ne) a limitação dos juros remuneratórios à taxa média de mercado "
            "divulgada pelo BACEN para a modalidade (REsp 1.061.530/RS, Tema 27/STJ), "
            "com o recálculo das parcelas conforme os valores determinísticos "
            "indicados nos fatos e a restituição do excedente."
        )
    return descricao_fatos, pedidos


@router.post("/{analysis_id}/gerar-peca",
             dependencies=[Depends(rate_limit("bank-gerar-peca", 5))])
async def gerar_peca(analysis_id: str, payload: dict | None = Body(default=None),
                     db: AsyncSession = Depends(get_db),
                     cu: User = Depends(get_current_user)):
    """Gera a MINUTA de uma ação revisional / repetição de indébito a partir das
    cobranças abusivas já detectadas na análise bancária.

    Reutiliza a esteira de peças (gerar_peca_pipeline, 7 etapas + SSE). A saída é
    RASCUNHO (HITL): revisão humana obrigatória (OAB). A sanitização LGPD ocorre
    dentro do pipeline. Retorna Server-Sent Events: step(1-7) → concluido com o
    documento e o legal_doc_id, no mesmo formato do gerador de peças.

    Body opcional: {"abusividade": <resposta de POST /analise-bancaria/abusividade>}
    — quando presente e com expurgo calculado, os números DETERMINÍSTICOS do
    recálculo pela taxa média BACEN entram nos fatos/pedidos da minuta (apenas
    valores numéricos validados são formatados; texto livre é descartado)."""
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Acesso negado")

    # Reutiliza detalhe(): já aplica ownership (verificar_acesso_caso se houver
    # case_id; senão gestão/criador) e carrega análise + cobranças.
    d = await detalhe(analysis_id, db, cu)
    cobrancas = d["cobrancas"]
    if not cobrancas:
        raise HTTPException(422, "Sem cobranças abusivas para peticionar nesta análise.")

    # Fail-safe: a esteira de peças depende de IA. Se nenhum provedor estiver
    # configurado, retorna erro limpo antes de abrir o stream.
    if (
        not settings.GROQ_API_KEY
        and not (settings.ANTHROPIC_ENABLED and settings.ANTHROPIC_API_KEY)
        and not (settings.MARITACA_ENABLED and settings.MARITACA_API_KEY)
    ):
        raise HTTPException(503, "Serviço de IA indisponível para geração de peças no momento.")

    analise = d["analise"]
    case_id = analise.get("case_id")
    expurgo_texto = None
    if payload and isinstance(payload.get("abusividade"), dict):
        from app.services.abusividade_service import formatar_expurgo_para_peca
        expurgo_texto = formatar_expurgo_para_peca(payload["abusividade"])
    descricao_fatos, pedidos = _montar_contexto_revisional(analise, cobrancas, expurgo_texto)

    escopo_cli = None
    if case_id:
        # ownership do caso já checado em detalhe(); aqui deriva o escopo do RAG.
        from app.services.ai_service import _escopo_cliente_do_caso
        escopo_cli = await _escopo_cliente_do_caso(db, case_id)

    from app.services.peca_service import gerar_peca_pipeline

    async def stream():
        try:
            async for chunk in gerar_peca_pipeline(
                db=db,
                user_id=cu.id,
                tipo_peca="peticao_inicial",
                area_direito="consumidor",
                descricao_fatos=descricao_fatos,
                pedidos=pedidos,
                scope_client_id=escopo_cli,
                nomes_proteger=[],
                case_id=case_id,
                instrucoes_adicionais=(
                    "Redija AÇÃO REVISIONAL DE CONTRATO BANCÁRIO cumulada com "
                    "REPETIÇÃO DE INDÉBITO, fundada nas cobranças abusivas apuradas "
                    "no extrato. Não invente valores além dos informados."
                ),
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Falha ao gerar peça da análise {analysis_id}: {e}", exc_info=True)
            yield (
                "event: erro\ndata: "
                + json.dumps(
                    {"detail": "Não foi possível gerar a minuta no momento."},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{analysis_id}")
async def remover(analysis_id: str, db: AsyncSession = Depends(get_db),
                  cu: User = Depends(get_current_user)):
    a = (await db.execute(select(BankAnalysis).where(
        BankAnalysis.id == analysis_id, BankAnalysis.deleted_at.is_(None)))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Análise não encontrada")
    # IDOR: só gestão, dono do caso ou criador pode apagar.
    if a.case_id:
        await verificar_acesso_caso(db, cu, a.case_id)
    elif not (is_gestao(cu) or a.created_by == cu.id):
        raise HTTPException(403, "Sem permissão para esta análise")
    await db.execute(text("UPDATE bank_analyses SET deleted_at = :n WHERE id = :i"),
                     {"n": datetime.now(timezone.utc), "i": analysis_id})
    await db.commit()
    return {"ok": True}
