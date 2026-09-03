# ── app/services/ai/core/context_builder.py ──────────────────────────────────
# BUILDER DE CONTEXTO do Núcleo Único de IA.
#
# O frontend envia apenas IDs + pergunta; o contexto REAL é montado AQUI, no
# backend, já sob RBAC/ownership (validados antes, no orchestrator).
#
# DOSSIÊ ESTRUTURADO (I3 da análise E2E de IA 2026-09-03) — seções em ordem
# ESTÁVEL, do que muda pouco para o que muda a cada pedido, para que o prefixo
# do prompt seja reaproveitado pelo prompt caching (AI_PROMPT_CACHING_ENABLED):
#   1. base legal da área (catálogo por ramo — estático);
#   2. identificação do caso e partes (case_context.montar_dossie, sanitizado);
#   3. documentos do caso classificados (título, tipo, resumo curto);
#   4. prazos abertos;
#   5. teses vinculadas ao caso;
#   6. intimações/andamentos do caso via RAG (scope_client_id + scope_case_id);
#   depois os blocos específicos do pedido — documento GED, processo e as
#   FONTES gerais do RAG — e, por último, (7) a pergunta/fatos do usuário, que
#   o orchestrator anexa após o [CONTEXTO] (não é duplicada aqui).
# Cada seção é truncada em AI_CONTEXTO_MAX_CHARS_SECAO e o conjunto em
# AI_CONTEXTO_MAX_CHARS. Documento de cofre (confidencialidade >= restrito)
# NUNCA entra em prompt de IA. Toda seção é best-effort: falha de leitura vira
# aviso + log da classe do erro (nunca PII), jamais aborta o pedido.
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.core.context")

# Orçamentos de caracteres por bloco (prompt enxuto e previsível).
_MAX_DOC = 18000
_MAX_RAG_CHUNK = 2000
_LIMITE_RAG = 10
_LIMITE_INTIMACOES = 5
_LIMITE_DOCUMENTOS = 40
_LIMITE_PRAZOS = 20
_LIMITE_TESES = 15

# Ordem canônica das seções (teste de invariante em tests/test_context_dossie_estruturado.py).
ORDEM_SECOES = (
    "base_legal", "identificacao", "documentos", "prazos", "teses",
    "intimacoes", "documento_ged", "processo", "fontes",
)
_TITULOS = {
    "base_legal": "[BASE LEGAL — ÁREA]",
    "identificacao": "[IDENTIFICAÇÃO DO CASO E PARTES]",
    "documentos": "[DOCUMENTOS DO CASO]",
    "prazos": "[PRAZOS ABERTOS]",
    "teses": "[TESES VINCULADAS AO CASO]",
    "intimacoes": "[INTIMAÇÕES E ANDAMENTOS DO CASO]",
    "fontes": "[FONTES — BASE DE CONHECIMENTO INTERNA]",
}


@dataclass
class ContextoMontado:
    texto: str = ""                                  # blocos prontos p/ prompt
    fontes: list[dict] = field(default_factory=list)  # chunks RAG (p/ citação)
    nomes_proteger: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)   # lacunas (ex.: doc de cofre)
    secoes: list[str] = field(default_factory=list)   # nomes das seções presentes, na ordem


def _limites() -> tuple[int, int]:
    """(teto por seção, teto total) lidos da config a cada chamada (testáveis)."""
    try:
        s = get_settings()
        secao = max(500, int(s.AI_CONTEXTO_MAX_CHARS_SECAO))
        total = max(500, int(s.AI_CONTEXTO_MAX_CHARS))
        return secao, total
    except Exception:  # noqa: BLE001 — config indisponível → defaults do I3
        return 6000, 60000


def _trunca(texto: str, limite: int) -> str:
    texto = texto or ""
    if len(texto) <= limite:
        return texto
    return texto[:limite] + "\n[... truncado para caber no contexto ...]"


def _fmt(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "value"):
        return str(v.value)
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%d/%m/%Y")
        except Exception:  # noqa: BLE001
            return str(v)
    return str(v)


def _normalizar_area(area) -> str:
    """'Cível/Consumidor' → 'civel'; CaseArea.civil → 'civil' (aliases do catálogo)."""
    bruto = _fmt(area).strip().lower()
    if not bruto:
        return ""
    bruto = bruto.split("/")[0].strip()
    sem_acento = unicodedata.normalize("NFKD", bruto).encode("ascii", "ignore").decode()
    return sem_acento.replace(" ", "_")


async def _acesso_caso_ok(db, user, alvo_case_id: str) -> bool:
    """Prova (fail-closed) que `user` pode acessar `alvo_case_id`.

    Reusa o gate canônico `verificar_acesso_caso` (mesma regra RBAC/ABAC e a
    mesma exceção do projeto), convertendo o 403/404 em False para o chamador
    apenas OMITIR o trecho — sem vazar existência do recurso cross-tenant.
    Sem `user` autenticado não há como provar o vínculo → nega.
    """
    if user is None or not alvo_case_id:
        return False
    from fastapi import HTTPException
    from app.core.ownership import verificar_acesso_caso
    try:
        await verificar_acesso_caso(db, user, alvo_case_id)
        return True
    except HTTPException:
        return False


async def _documento_autorizado(db, user, doc, case_id: str | None) -> bool:
    """Ownership de DOCUMENTO antes de injetar seu conteúdo no prompt (IDOR guard).

    - Vínculo por caso é a fonte primária: se o contexto trouxe `case_id`, o
      documento TEM de ser daquele caso (bloqueia doc de outro caso/cliente);
      além disso, prova o acesso do usuário ao caso do próprio documento.
    - Documento sem caso: só gestão ou o próprio uploader (fail-closed p/ o
      resto — validação por cliente sem caso fica em routers.documents._verificar_
      acesso_documento; não importável aqui sem acoplar service→router).
    """
    doc_case = getattr(doc, "case_id", None)
    if doc_case:
        if case_id and doc_case != case_id:
            return False
        return await _acesso_caso_ok(db, user, doc_case)
    if user is None:
        return False
    from app.core.ownership import is_gestao
    if is_gestao(user):
        return True
    uploader = getattr(doc, "uploaded_by", None)
    return bool(uploader) and uploader == getattr(user, "id", None)


async def _processo_autorizado(db, user, proc, case_id: str | None) -> bool:
    """Ownership de PROCESSO (Process.case_id é NOT NULL) antes do prompt."""
    proc_case = getattr(proc, "case_id", None)
    if not proc_case:
        return False
    if case_id and proc_case != case_id:
        return False
    return await _acesso_caso_ok(db, user, proc_case)


# ── Seções do dossiê estruturado (leituras já existentes nos models) ──────────

def _secao_base_legal(area) -> str:
    """Seção 1 — base da área pelo catálogo de ramos (estática por área)."""
    from app.services.ai.core.ejc_skill_catalog import LEGAL_AREA_ALIASES, _LEGAL_DATA
    chave = LEGAL_AREA_ALIASES.get(_normalizar_area(area))
    dados = _LEGAL_DATA.get(chave or "")
    if not dados:
        return ""
    nome, descricao, metodo = dados
    return (
        f"{_TITULOS['base_legal']} {nome}\n"
        f"Escopo: {descricao}\n"
        f"Método de análise: {metodo}"
    )


async def _area_do_caso(db, case_id: str):
    from sqlalchemy import select
    from app.models.case import Case
    return (await db.execute(
        select(Case.area).where(Case.id == case_id, Case.deleted_at.is_(None))
    )).scalar_one_or_none()


async def _secao_documentos(db, case_id: str) -> str:
    """Seção 3 — documentos do caso classificados (sem conteúdo; cofre excluído)."""
    from sqlalchemy import select
    from app.models.document import Document, DocConfidencialidade
    docs = (await db.execute(
        select(Document).where(
            Document.case_id == case_id,
            Document.deleted_at.is_(None),
            Document.confidencialidade.in_(
                [DocConfidencialidade.normal, DocConfidencialidade.interno]
            ),
        ).order_by(Document.created_at.desc()).limit(_LIMITE_DOCUMENTOS)
    )).scalars().all()
    if not docs:
        return ""
    linhas = [_TITULOS["documentos"]]
    for d in docs:
        resumo = (getattr(d, "descricao", None) or "").strip().replace("\n", " ")
        linha = f"  • {d.titulo} (tipo: {d.tipo or 'não classificado'})"
        if resumo:
            linha += f" — {resumo[:200]}"
        linhas.append(linha)
    return "\n".join(linhas)


async def _secao_prazos(db, case_id: str) -> str:
    """Seção 4 — prazos abertos (pendentes/vencidos), do mais próximo ao mais distante."""
    from sqlalchemy import select
    from app.models.deadline import Deadline, DeadlineStatus
    prazos = (await db.execute(
        select(Deadline).where(
            Deadline.case_id == case_id,
            Deadline.status.in_([DeadlineStatus.pendente, DeadlineStatus.vencido]),
        ).order_by(Deadline.data_prazo.asc()).limit(_LIMITE_PRAZOS)
    )).scalars().all()
    if not prazos:
        return ""
    linhas = [_TITULOS["prazos"]]
    for p in prazos:
        linha = (f"  • {_fmt(p.data_prazo)} — {p.titulo} "
                 f"[{_fmt(p.tipo)}/{_fmt(p.prioridade)}/{_fmt(p.status)}]")
        if getattr(p, "base_legal", None):
            linha += f" (base: {p.base_legal})"
        linhas.append(linha)
    return "\n".join(linhas)


async def _secao_teses(db, case_id: str) -> str:
    """Seção 5 — teses vinculadas ao caso (TeseCasoLink), com resultado."""
    from sqlalchemy import select
    from app.models.tese import Tese, TeseCasoLink
    rows = (await db.execute(
        select(Tese, TeseCasoLink.resultado)
        .join(TeseCasoLink, TeseCasoLink.tese_id == Tese.id)
        .where(TeseCasoLink.case_id == case_id, Tese.deleted_at.is_(None))
        .limit(_LIMITE_TESES)
    )).all()
    if not rows:
        return ""
    linhas = [_TITULOS["teses"]]
    for row in rows:
        tese, resultado = row[0], (row[1] if len(row) > 1 else None)
        linha = f"  • {tese.titulo} ({_fmt(tese.status) or 'ativa'}"
        if resultado:
            linha += f", resultado: {resultado}"
        linha += ")"
        fund = (getattr(tese, "fundamentacao", None) or "").strip().replace("\n", " ")
        if fund:
            linha += f" — {fund[:300]}"
        linhas.append(linha)
    return "\n".join(linhas)


def _formatar_fontes(titulo: str, fontes: list[dict]) -> str:
    linhas = [titulo]
    for i, f in enumerate(fontes, 1):
        nome = f.get("titulo") or "sem título"
        categoria = f.get("categoria") or ""
        trecho = _trunca(f.get("conteudo") or "", _MAX_RAG_CHUNK)
        linhas.append(f"[Fonte {i}] {nome}"
                      + (f" ({categoria})" if categoria else "") + f"\n{trecho}")
    return "\n\n".join(linhas)


async def montar_contexto(
    db,
    *,
    mensagem: str,
    case_id: str | None = None,
    document_id: str | None = None,
    process_id: str | None = None,
    user=None,
    usar_rag: bool = True,
    exige_fonte: bool = False,
) -> ContextoMontado:
    ctx = ContextoMontado()
    if db is None:
        return ctx
    max_secao, max_total = _limites()
    secoes: list[tuple[str, str]] = []   # (nome, texto) na ORDEM_SECOES
    scope_client_id: str | None = None
    area = None

    def _add(nome: str, texto: str) -> None:
        if texto and texto.strip():
            secoes.append((nome, _trunca(texto.strip(), max_secao)))

    async def _best_effort(nome: str, coro):
        """Leitura best-effort: falha vira aviso + classe do erro no log."""
        try:
            return await coro
        except Exception as exc:  # noqa: BLE001 — seção nunca derruba o pedido
            ctx.avisos.append(f"Seção '{nome}' indisponível — omitida do contexto.")
            logger.warning("Seção %s do contexto falhou: %s", nome, type(exc).__name__)
            return None

    # ── Caso: seções 1–6 do dossiê estruturado ───────────────────────────────
    if case_id:
        from app.services.case_context import montar_dossie
        dossie = await montar_dossie(db, case_id, sanitizar=True)
        if dossie:
            ctx.nomes_proteger = dossie.get("nomes_proteger") or []
            # O RAG restrito é client-scoped. Sem este escopo, o filtro
            # fail-closed exclui justamente precedentes internos, peças e
            # comunicações do próprio cliente, deixando o Núcleo Único sem a
            # memória institucional que deveria utilizar. Acesso ao caso já foi
            # provado pelo orchestrator; ainda assim, a resolução consulta apenas
            # caso ativo e nunca aceita client_id vindo do frontend.
            from app.services.ai_service import _escopo_cliente_do_caso
            scope_client_id = await _escopo_cliente_do_caso(db, case_id)

            # 1. Base legal da área (estática; área lida do caso, com fallback
            #    no rótulo do dossiê).
            area = await _best_effort("base_legal", _area_do_caso(db, case_id))
            if not area:
                area = (dossie.get("meta") or {}).get("area")
            _add("base_legal", _secao_base_legal(area))

            # 2. Identificação do caso e partes (já sanitizado por montar_dossie).
            _add("identificacao", f"{_TITULOS['identificacao']}\n{dossie.get('texto', '')}")

            # 3–5. Documentos, prazos e teses — sanitizados com os nomes do caso
            #      (mesma barreira do dossiê: nada de PII em texto livre).
            from app.services.sanitizer import sanitizar_pii
            for nome, coro in (
                ("documentos", _secao_documentos(db, case_id)),
                ("prazos", _secao_prazos(db, case_id)),
                ("teses", _secao_teses(db, case_id)),
            ):
                texto = await _best_effort(nome, coro)
                if texto:
                    texto, _ = sanitizar_pii(texto, ctx.nomes_proteger or None)
                    _add(nome, texto)

            # 6. Intimações/andamentos DO CASO via RAG (cliente + caso).
            if scope_client_id and (usar_rag or exige_fonte):
                from app.services.ai_service import buscar_contexto_rag
                intimacoes = await _best_effort("intimacoes", buscar_contexto_rag(
                    db, mensagem, limite=_LIMITE_INTIMACOES,
                    categorias=["comunicacao_processual"], modo_or=True,
                    scope_client_id=scope_client_id, scope_case_id=case_id,
                ))
                if intimacoes:
                    _add("intimacoes", _formatar_fontes(_TITULOS["intimacoes"], intimacoes))
        else:
            ctx.avisos.append("Caso não encontrado — contexto do caso omitido.")

    # ── Documento (GED) ──────────────────────────────────────────────────────
    if document_id:
        from sqlalchemy import select
        from app.models.document import Document, DocConfidencialidade
        doc = (await db.execute(
            select(Document).where(Document.id == document_id,
                                   Document.deleted_at.is_(None))
        )).scalar_one_or_none()
        if doc is None:
            ctx.avisos.append("Documento não encontrado — contexto documental omitido.")
        elif not await _documento_autorizado(db, user, doc, case_id):
            # IDOR guard: doc de outro caso/cliente (ou vínculo não provável)
            # é tratado como INEXISTENTE — mesma mensagem, sem vazar existência.
            ctx.avisos.append("Documento não encontrado — contexto documental omitido.")
        elif doc.confidencialidade not in (DocConfidencialidade.normal,
                                           DocConfidencialidade.interno):
            # Cofre (>= restrito): documento sigiloso jamais vira prompt de IA.
            ctx.avisos.append(
                "Documento em confidencialidade elevada (cofre) — conteúdo NÃO "
                "enviado à IA por política de sigilo."
            )
        elif not (doc.ocr_text or "").strip():
            ctx.avisos.append("Documento sem texto extraído (OCR pendente).")
        else:
            # Bloco do pedido: mantém o orçamento próprio (_MAX_DOC) — o teto
            # por seção vale para o dossiê; o total (AI_CONTEXTO_MAX_CHARS)
            # continua valendo para tudo.
            secoes.append((
                "documento_ged",
                f"[DOCUMENTO] {doc.titulo} (tipo: {doc.tipo or 'não classificado'})\n"
                + _trunca(doc.ocr_text, _MAX_DOC),
            ))

    # ── Processo (metadados) ─────────────────────────────────────────────────
    if process_id:
        from sqlalchemy import select
        from app.models.process import Process
        proc = (await db.execute(
            select(Process).where(Process.id == process_id)
        )).scalar_one_or_none()
        if proc is None:
            ctx.avisos.append("Processo não encontrado — contexto processual omitido.")
        elif not await _processo_autorizado(db, user, proc, case_id):
            # IDOR guard: processo de outro caso/cliente → tratado como inexistente.
            ctx.avisos.append("Processo não encontrado — contexto processual omitido.")
        else:
            partes = [f"[PROCESSO] status: {getattr(proc, 'status', '?')}"]
            for campo in ("tribunal", "vara", "comarca", "fase", "instancia", "rito"):
                valor = getattr(proc, campo, None)
                if valor:
                    partes.append(f"{campo}: {valor}")
            # numero_cnj propositalmente OMITIDO: é PII estrutural (sanitização
            # o mascararia de toda forma) e não agrega à análise.
            _add("processo", " | ".join(partes))

    # ── RAG (base de conhecimento com fontes) ────────────────────────────────
    if usar_rag or exige_fonte:
        from app.services.ai_service import buscar_contexto_rag
        try:
            ctx.fontes = await buscar_contexto_rag(
                db,
                mensagem,
                limite=_LIMITE_RAG,
                scope_client_id=scope_client_id,
                # Isolamento por caso: a comunicação processual de OUTRO caso
                # do mesmo cliente não é contexto deste (auditoria, dívida 5.5).
                scope_case_id=case_id,
            )
        except Exception as exc:
            ctx.fontes = []
            ctx.avisos.append("Busca RAG indisponível — resposta sem base interna.")
            # Observabilidade segura: registra apenas a classe, nunca consulta,
            # contexto ou detalhe de banco que possa conter PII.
            logger.warning("Busca RAG do context builder falhou: %s", type(exc).__name__)
        if ctx.fontes:
            secoes.append(("fontes", _formatar_fontes(_TITULOS["fontes"], ctx.fontes)))

    # Ordem canônica (estável) + teto total.
    ordem = {nome: i for i, nome in enumerate(ORDEM_SECOES)}
    secoes.sort(key=lambda s: ordem.get(s[0], len(ORDEM_SECOES)))
    ctx.secoes = [nome for nome, _ in secoes]
    texto = "\n\n---\n\n".join(t for _, t in secoes if t.strip())
    if len(texto) > max_total:
        ctx.avisos.append("Contexto truncado no teto total (AI_CONTEXTO_MAX_CHARS).")
        texto = _trunca(texto, max_total)
    ctx.texto = texto
    return ctx
