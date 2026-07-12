# ── app/routers/provas.py ─────────────────────────────────────────────────────
# Gestão de Provas por CASO — acervo probatório estruturado (gap transversal:
# serve os 8 ramos) + gerador do "Documento Único de Anexos" em Visual Law.
#
#   GET    /casos/{case_id}/provas                       → lista (ordenada por ordem)
#   POST   /casos/{case_id}/provas                       → cria (audit)
#   PATCH  /casos/{case_id}/provas/{prova_id}            → atualiza/reordena (audit)
#   DELETE /casos/{case_id}/provas/{prova_id}            → soft delete (audit)
#   POST   /casos/{case_id}/provas/documento-unico       → {"download_url": ...}
#   GET    /casos/{case_id}/provas/documento-unico/{id}/download → FileResponse (PDF)
#   POST   /casos/{case_id}/provas/sugerir-faltantes     → IA sugere provas FALTANTES
#          (Etapa 6 — Mapa Probatório: advogado+, contexto determinístico do caso,
#           JSON estrito com parse defensivo, AILog/HITL — são SUGESTÕES)
#
# Segurança:
#   • autorização por caso via core/ownership.verificar_acesso_caso (404 se o caso
#     não existe/soft-deleted; 403 se sem permissão) em TODAS as rotas;
#   • vínculos validados no MESMO caso: document_id precisa pertencer ao caso
#     (Document.case_id); tese_id precisa existir e não estar soft-deleted (a Tese
#     é institucional/reutilizável — não é case-scoped no schema, N:N por
#     tese_caso_links);
#   • audit log (criar_audit_log) em toda escrita; soft delete;
#   • PDF endurecido (padrão routers/tributario_fiscal.py): esc() em toda string,
#     download_url + GET /download com UUID validado (sem traversal),
#     _limpar_pdfs_antigos (TTL/LGPD), rate_limit em TODAS as rotas.
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user
from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.document import Document
from app.models.prova import Prova
from app.models.tese import Tese
from app.models.user import User
from app.schemas.common import MsgResponse
from app.schemas.prova import ProvaCreate, ProvaUpdate, SugestaoProvaFaltante

settings = get_settings()
router = APIRouter(prefix="/casos/{case_id}/provas", tags=["Provas"])

# Retenção dos PDFs do documento único (contêm dados do caso e do cliente —
# LGPD): varredura best-effort remove os mais antigos que o TTL a cada geração.
PDF_TTL_SEGUNDOS = 3600  # 1h
from app.services import visual_law_files as _vlf  # #27: arnês único


# ── Helpers ───────────────────────────────────────────────────────────────────

def _out_prova(p: Prova, documento_nome: Optional[str] = None,
               tese_titulo: Optional[str] = None) -> dict:
    return {
        "id": p.id,
        "case_id": p.case_id,
        "tipo": p.tipo,
        "titulo": p.titulo,
        "descricao": p.descricao,
        "document_id": p.document_id,
        "documento_nome": documento_nome,
        "tese_id": p.tese_id,
        "tese_titulo": tese_titulo,
        "fato_probando": p.fato_probando,
        "ordem": p.ordem,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def _validar_document(db: AsyncSession, case_id: str, document_id: str) -> None:
    """document_id precisa existir, não estar soft-deleted E pertencer ao MESMO
    caso — não deixa vincular documento de outro caso (nem vaza sua existência)."""
    doc = (await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if doc is None or doc.case_id != case_id:
        raise HTTPException(status_code=400,
                            detail="Documento inválido ou de outro caso")


async def _validar_tese(db: AsyncSession, tese_id: str) -> None:
    """tese_id precisa existir e não estar soft-deleted. A Tese é institucional
    (Banco de Teses reutilizável entre casos, N:N via tese_caso_links) — não é
    case-scoped no schema, então validamos apenas existência/vigência."""
    tese = (await db.execute(
        select(Tese).where(Tese.id == tese_id, Tese.deleted_at.is_(None))
    )).scalar_one_or_none()
    if tese is None:
        raise HTTPException(status_code=400, detail="Tese inválida")


async def _carregar_prova(db: AsyncSession, case_id: str, prova_id: str) -> Prova:
    """Carrega a prova garantindo que pertence AO caso do path (e não deletada).
    404 fora do escopo — não vaza existência de prova de outro caso."""
    p = (await db.execute(
        select(Prova).where(
            Prova.id == prova_id,
            Prova.case_id == case_id,
            Prova.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Prova não encontrada")
    return p


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(rate_limit("provas-listar", 60))])
async def listar_provas(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Lista as provas do caso (ordenadas por `ordem`), cada uma já com o nome do
    documento vinculado e o título da tese vinculada (quando houver)."""
    await verificar_acesso_caso(db, cu, case_id)

    rows = (await db.execute(
        select(Prova, Document.titulo, Tese.titulo)
        .outerjoin(Document, Document.id == Prova.document_id)
        .outerjoin(Tese, Tese.id == Prova.tese_id)
        .where(Prova.case_id == case_id, Prova.deleted_at.is_(None))
        .order_by(Prova.ordem, Prova.created_at)
    )).all()

    data = [_out_prova(p, doc_nome, tese_titulo)
            for p, doc_nome, tese_titulo in rows]
    return {"data": data, "total": len(data)}


@router.post("", status_code=201,
             dependencies=[Depends(rate_limit("provas-criar", 30))])
async def criar_prova(
    case_id: str,
    payload: ProvaCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)

    if payload.document_id:
        await _validar_document(db, case_id, payload.document_id)
    if payload.tese_id:
        await _validar_tese(db, payload.tese_id)

    p = Prova(
        id=str(uuid4()),
        case_id=case_id,
        tipo=payload.tipo.value,
        titulo=payload.titulo.strip(),
        descricao=payload.descricao,
        document_id=payload.document_id,
        tese_id=payload.tese_id,
        fato_probando=payload.fato_probando,
        ordem=payload.ordem,
        created_by=cu.id,
    )
    db.add(p)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "provas",
                          p.id, detalhes=f"caso {case_id}: {p.tipo} — {p.titulo}")
    await db.commit()
    return _out_prova(p)


@router.patch("/{prova_id}",
              dependencies=[Depends(rate_limit("provas-atualizar", 30))])
async def atualizar_prova(
    case_id: str,
    prova_id: str,
    payload: ProvaUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)
    p = await _carregar_prova(db, case_id, prova_id)

    mudancas = payload.model_dump(exclude_unset=True)
    if mudancas.get("tipo") is not None:
        mudancas["tipo"] = mudancas["tipo"].value
    # Revalida vínculos quando (re)informados — mesmo racional da criação.
    if mudancas.get("document_id"):
        await _validar_document(db, case_id, mudancas["document_id"])
    if mudancas.get("tese_id"):
        await _validar_tese(db, mudancas["tese_id"])
    if mudancas.get("titulo") is not None:
        mudancas["titulo"] = mudancas["titulo"].strip()

    for k, v in mudancas.items():
        setattr(p, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "provas",
                          prova_id, detalhes=f"campos: {sorted(mudancas)}")
    await db.commit()
    return _out_prova(p)


@router.delete("/{prova_id}", response_model=MsgResponse,
               dependencies=[Depends(rate_limit("provas-remover", 30))])
async def remover_prova(
    case_id: str,
    prova_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Soft delete — a prova some da lista mas o registro é preservado."""
    await verificar_acesso_caso(db, cu, case_id)
    p = await _carregar_prova(db, case_id, prova_id)
    p.deleted_at = datetime.now(timezone.utc)
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "provas", prova_id)
    await db.commit()
    return MsgResponse(detail="Prova removida")


# ── Provas FALTANTES (sugestão da IA — Etapa 6 do Mapa Probatório) ────────────
# A IA recebe um contexto DETERMINÍSTICO do caso (área, título, tese principal,
# tipo de ação e as provas EXISTENTES com fato probando) e devolve JSON estrito
# com as provas TÍPICAS que estão faltando (ex.: laudo, ata notarial, orçamento,
# extrato) + justificativa probatória. HITL: são SUGESTÕES — o advogado que
# acatar cria a Prova pelo fluxo normal (nenhuma escrita automática no acervo).

_CRITICIDADES_VALIDAS = {"alta", "media", "baixa"}
_MAX_SUGESTOES = 12


def _norm_titulo(texto: str) -> str:
    """Normaliza título p/ deduplicação (minúsculas, sem acentos, espaços únicos)."""
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def _extrair_lista_json(texto: str) -> Optional[list]:
    """Extrai a PRIMEIRA lista JSON plausível do texto da IA (parse defensivo):
    texto puro → cerca ```json``` → maior slice entre '[' e ']'. Aceita também
    um objeto com a lista dentro (ex.: {"sugestoes": [...]}). None se nada
    parseável — o chamador degrada p/ lista vazia + aviso (nunca 500)."""
    candidatos: list[str] = [texto.strip()]
    cerca = re.search(r"```(?:json)?\s*(.+?)```", texto, re.S)
    if cerca:
        candidatos.append(cerca.group(1).strip())
    ini, fim = texto.find("["), texto.rfind("]")
    if 0 <= ini < fim:
        candidatos.append(texto[ini:fim + 1])

    for cand in candidatos:
        try:
            parsed = json.loads(cand)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):  # {"sugestoes": [...]} / {"provas_faltantes": [...]}
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    return None


def _parse_sugestoes(texto: str, titulos_existentes: list[str]) -> list[dict]:
    """Valida item a item a resposta da IA (schema SugestaoProvaFaltante como
    última linha de defesa) e DESCARTA: itens malformados, criticidade fora do
    domínio (após normalização de acento/caixa) vira "media", e qualquer
    sugestão cujo título já exista no acervo (a IA é instruída a não repetir,
    mas o filtro determinístico é a garantia)."""
    bruto = _extrair_lista_json(texto or "")
    if not bruto:
        return []

    existentes = {_norm_titulo(t) for t in titulos_existentes if t}
    saida: list[dict] = []
    vistos: set[str] = set()
    for item in bruto:
        if not isinstance(item, dict):
            continue
        crit = _norm_titulo(str(item.get("criticidade") or ""))
        try:
            sug = SugestaoProvaFaltante(
                titulo=str(item.get("titulo") or "").strip()[:255],
                por_que_importa=str(item.get("por_que_importa") or "").strip()[:2000],
                como_obter=str(item.get("como_obter") or "").strip()[:2000],
                criticidade=crit if crit in _CRITICIDADES_VALIDAS else "media",
            )
        except Exception:
            continue  # item malformado nunca derruba o lote
        chave = _norm_titulo(sug.titulo)
        if not chave or chave in existentes or chave in vistos:
            continue
        vistos.add(chave)
        saida.append(sug.model_dump())
        if len(saida) >= _MAX_SUGESTOES:
            break
    return saida


def _contexto_sugestao(case: Case, provas: list[Prova]) -> str:
    """Contexto DETERMINÍSTICO do caso (sem texto livre além dos campos do
    próprio caso): área, título, tipo de ação, tese principal e o acervo
    existente com fato probando. É o ÚNICO insumo fático dado à IA."""
    area = case.area.value if hasattr(case.area, "value") else str(case.area or "—")
    tipo_acao = (case.tipo_acao_prescricao
                 or case.extrajudicial_type
                 or case.case_type
                 or "não informado")
    linhas = [
        f"Área do direito: {area}",
        f"Título do caso: {case.titulo or '—'}",
        f"Tipo de ação: {tipo_acao}",
        f"Tese principal: {(case.tese_principal or 'não informada').strip()[:2000]}",
        "",
        "Provas JÁ EXISTENTES no caso:",
    ]
    if provas:
        for p in provas:
            fato = (p.fato_probando or "não informado").strip()[:500]
            linhas.append(f"- [{p.tipo}] {p.titulo} — fato probando: {fato}")
    else:
        linhas.append("- (nenhuma prova cadastrada ainda)")

    # ── Âncora determinística: matriz tese×prova (Fase C) ──────────────────────
    # Piso mínimo por área/tese, sem IA. Se nada casar, não injeta nada (o
    # comportamento atual é preservado). Só rótulos jurídicos — sem PII.
    from app.services.matriz_provas import provas_recomendadas_texto
    texto_alvo = " ".join(filter(None, [
        case.titulo, case.tese_principal, str(tipo_acao),
        getattr(case, "descricao_fatos", None),
    ]))
    matriz_txt = provas_recomendadas_texto(area, texto_alvo)
    if matriz_txt:
        linhas += [
            "",
            "REFERÊNCIA (matriz tese×prova) — provas mínimas típicas para as "
            "teses/pedidos deste caso (piso determinístico, use como âncora):",
            matriz_txt,
        ]
    return "\n".join(linhas)


_SYSTEM_SUGESTAO = (
    "Você é um assistente jurídico do escritório, especializado em instrução "
    "probatória no direito brasileiro. Dado o contexto de um caso e a lista de "
    "provas já existentes, aponte APENAS as provas TÍPICAS para aquele tipo de "
    "ação que estão FALTANDO (ex.: laudo pericial, ata notarial, orçamento, "
    "extrato bancário, testemunhas, notificação extrajudicial).\n"
    "Regras OBRIGATÓRIAS:\n"
    "1. NÃO repita nem parafraseie provas que já constam da lista existente.\n"
    "2. NÃO invente fatos do caso: justifique cada sugestão apenas pela "
    "tipicidade probatória da ação/área informada.\n"
    "3. Responda SOMENTE com um array JSON válido, sem markdown nem texto "
    "fora do JSON, no formato: [{\"titulo\": str, \"por_que_importa\": str, "
    "\"como_obter\": str, \"criticidade\": \"alta\"|\"media\"|\"baixa\"}].\n"
    "4. No máximo 8 sugestões, das mais críticas para as menos críticas. Se "
    "nada relevante faltar, responda [].\n"
    "5. Se o contexto trouxer uma REFERÊNCIA (matriz tese×prova), trate-a como "
    "PISO mínimo: as provas ali listadas que ainda NÃO constarem do acervo "
    "devem figurar entre as sugestões (com criticidade coerente). Você pode e "
    "deve acrescentar outras provas típicas além do piso.\n"
    "Suas sugestões são RASCUNHO de apoio — a decisão é do advogado (HITL)."
)


@router.post("/sugerir-faltantes",
             dependencies=[Depends(rate_limit("provas-sugerir-faltantes", 5))])
async def sugerir_provas_faltantes(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """IA sugere provas FALTANTES do caso (Mapa Probatório — Etapa 6).

    Piso advogado+ (endpoint de geração), ownership via verificar_acesso_caso,
    contexto determinístico, JSON estrito com parse defensivo (fallback lista
    vazia + aviso — nunca 500 por resposta ruim da IA), pseudonimização LGPD
    das entidades do caso antes de provider externo e AILog registrado (HITL:
    nada é escrito no acervo — o advogado cria a Prova pelo fluxo normal).
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Apenas advogados podem gerar sugestões de provas com IA")
    case = await verificar_acesso_caso(db, cu, case_id)

    provas = list((await db.execute(
        select(Prova)
        .where(Prova.case_id == case_id, Prova.deleted_at.is_(None))
        .order_by(Prova.ordem, Prova.created_at)
    )).scalars())

    contexto = _contexto_sugestao(case, provas)

    # LGPD: nomes do caso (cliente/partes/advogado) pseudonimizados de forma
    # REVERSÍVEL pela barreira do gateway antes de qualquer provider externo
    # (padrão ia_adversarial). Falha do helper degrada com segurança ({}).
    from app.services.ai.entidades_caso import entidades_do_caso
    from app.services.ai_gateway import chat as gw_chat
    entidades = await entidades_do_caso(db, case_id)

    aviso: Optional[str] = None
    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": _SYSTEM_SUGESTAO},
                {"role": "user", "content": contexto},
            ],
            task_type="analise_juridica",
            temperature=0.2,
            max_tokens=1800,
            entidades=entidades,
        )
    except Exception as e:  # provider indisponível NUNCA vira 500 aqui
        # Detalhe do provider só no log — não vaza infraestrutura na UI.
        logging.getLogger("ejc.provas").warning(
            f"sugerir-faltantes: gateway indisponível: {e}")
        return {"data": [], "total": 0, "modelo": None, "provedor": None,
                "aviso": "IA indisponível no momento — tente novamente em instantes."}

    sugestoes = _parse_sugestoes(resp.texto, [p.titulo for p in provas])
    if not sugestoes:
        aviso = ("A IA não retornou sugestões válidas para este caso — nada "
                 "foi descartado do acervo; tente novamente ou detalhe a tese "
                 "principal do caso.")

    # Trilha de auditoria (padrão do projeto: todo uso de IA gera AILog).
    # prompt SANITIZADO (sem PII) no log; status HITL "gerado" — são sugestões.
    from app.models.ai_log import AILog, AIStatusHITL, AITipoUso
    from app.services.sanitizer import sanitizar_pii
    prompt_log, pii = sanitizar_pii(contexto)
    db.add(AILog(
        id=str(uuid4()),
        user_id=cu.id,
        case_id=case_id,
        tipo_uso=AITipoUso.analise_caso,
        modelo=f"{resp.provedor}/{resp.modelo}"[:50],
        prompt_sanitizado=("[PROVAS_FALTANTES sugestão IA]\n" + prompt_log)[:8000],
        pii_removida=pii,
        resposta=(resp.texto or "")[:8000],
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
        status_hitl=AIStatusHITL.gerado,
    ))
    await db.commit()

    return {"data": sugestoes, "total": len(sugestoes),
            "modelo": resp.modelo, "provedor": resp.provedor, "aviso": aviso}


@router.get("/matriz",
            dependencies=[Depends(rate_limit("provas-matriz", 30))])
async def matriz_provas_referencia(
    case_id: str,
    area: Optional[str] = None,
    pedidos: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Referência determinística (matriz tese×prova) — provas mínimas típicas.

    Piso estagiário+ (leitura de referência estática, sem IA e sem PII).
    Ownership via verificar_acesso_caso. Se ``area``/``pedidos`` não vierem,
    são derivados do próprio caso (área + título + tese principal). Nunca 500:
    a matriz degrada para lista vazia quando nada casa.
    """
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["estagiario"]:
        raise HTTPException(403, "Sem permissão para consultar a matriz de provas")
    case = await verificar_acesso_caso(db, cu, case_id)

    from app.services.matriz_provas import provas_recomendadas
    area_ef = area or (case.area.value if hasattr(case.area, "value") else str(case.area or ""))
    texto = pedidos or " ".join(filter(None, [
        case.titulo, case.tese_principal,
        getattr(case, "descricao_fatos", None),
    ]))
    data = provas_recomendadas(area_ef, texto)
    return {"data": data, "total": len(data), "area": area_ef}


# ── Documento Único de Anexos (Visual Law) ────────────────────────────────────

def _romano(n: int) -> str:
    """Numeração romana para os anexos (Anexo I, II, III...)."""
    if n <= 0:
        return str(n)
    tabela = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
              (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
              (5, "V"), (4, "IV"), (1, "I"))
    saida = []
    for valor, simbolo in tabela:
        while n >= valor:
            saida.append(simbolo)
            n -= valor
    return "".join(saida)


def _html_documento_unico(caso: dict, provas: list[dict]) -> str:
    """Monta o HTML do Documento Único de Anexos: capa + sumário numerado
    (Anexo I, II, III...) + uma seção por prova. TODA string vinda do banco/
    usuário passa por vlt.esc() (anti-injeção)."""
    from app.services import visual_law_theme as vlt

    esc = vlt.esc
    rotulo_tipo = {
        "documental": "Documental", "pericial": "Pericial",
        "testemunhal": "Testemunhal", "material": "Material",
        "digital": "Digital", "outro": "Outro",
    }

    partes: list[str] = [vlt.render_banner(
        "DOCUMENTO ÚNICO DE ANEXOS",
        f"{esc(caso.get('cliente') or '—')} · {esc(caso.get('ramo') or '—')}",
    )]

    # Capa: dados do caso.
    partes.append(
        "<div style='background:" + vlt.OURO_PALHA + ";border-left:4px solid "
        + vlt.OURO + ";padding:14px 16px;margin:16px 0;'>"
        f"<div style='font-size:13pt;font-weight:bold;color:{vlt.OURO_PROFUNDO};'>"
        f"{esc(caso.get('titulo') or 'Caso')}</div>"
        f"<div style='font-size:10pt;color:{vlt.TEXTO_SUAVE};'>"
        f"Processo/nº: {esc(caso.get('numero') or '—')} · "
        f"Cliente: {esc(caso.get('cliente') or '—')} · "
        f"Ramo: {esc(caso.get('ramo') or '—')}</div></div>"
    )

    # Sumário de anexos numerado.
    partes.append(f"<h2 style='color:{vlt.OURO};'>Sumário de Anexos</h2>"
                  "<table class='tema'><thead><tr>"
                  "<th style='width:16mm;'>Anexo</th><th>Prova</th>"
                  "<th style='width:26mm;'>Tipo</th><th>Fato probando</th>"
                  "</tr></thead><tbody>")
    for i, pr in enumerate(provas, start=1):
        anexo = f"Anexo {_romano(i)}"
        tipo = rotulo_tipo.get(pr.get("tipo") or "", esc(pr.get("tipo") or "—"))
        partes.append(
            f"<tr><td style='font-weight:bold;color:{vlt.OURO};white-space:nowrap;'>"
            f"{esc(anexo)}</td><td>{esc(pr.get('titulo') or '—')}</td>"
            f"<td>{esc(tipo)}</td>"
            f"<td>{esc(pr.get('fato_probando') or '—')}</td></tr>"
        )
    partes.append("</tbody></table>")

    # Uma seção por prova.
    for i, pr in enumerate(provas, start=1):
        anexo = f"Anexo {_romano(i)}"
        tipo = rotulo_tipo.get(pr.get("tipo") or "", esc(pr.get("tipo") or "—"))
        partes.append(
            f"<h2 style='color:{vlt.OURO};margin-top:22px;'>"
            f"{esc(anexo)} — {esc(pr.get('titulo') or '—')}</h2>"
            f"<p style='font-size:9.5pt;color:{vlt.TEXTO_SUAVE};'>"
            f"Tipo: {esc(tipo)}</p>"
        )
        if pr.get("fato_probando"):
            partes.append("<p style='font-size:10pt;'><strong>Fato probando:</strong> "
                          f"{esc(pr['fato_probando'])}</p>")
        if pr.get("descricao"):
            partes.append(f"<p style='font-size:10pt;'>{esc(pr['descricao'])}</p>")
        if pr.get("documento_nome"):
            partes.append("<p style='font-size:9.5pt;'><strong>Documento anexado:</strong> "
                          f"{esc(pr['documento_nome'])}</p>")
        if pr.get("tese_titulo"):
            partes.append("<p style='font-size:9.5pt;'><strong>Tese/pedido sustentado:</strong> "
                          f"{esc(pr['tese_titulo'])}</p>")

    partes.append(
        f"<div style='margin-top:24px;font-size:8.5pt;color:{vlt.RODAPE_COR};"
        "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
        f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · "
        f"{len(provas)} anexo(s)</div>"
    )

    rodape = "De Paula Teixeira Advogados · Documento Único de Anexos"
    return vlt.html_doc("".join(partes), css=vlt.css_fluxo(rodape))


def _provas_dir() -> str:
    out_dir = os.path.join(settings.UPLOAD_DIR, "provas")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _limpar_pdfs_antigos(out_dir: str) -> None:
    """Retenção LGPD: os PDFs carregam dados do caso e do cliente. Varredura
    best-effort remove os mais antigos que o TTL a cada geração — sem estado
    externo, tolerante a falhas (nunca quebra a resposta)."""
    # #27: purga TTL centralizada em services/visual_law_files (retenção LGPD).
    _vlf.purgar_antigos(out_dir, PDF_TTL_SEGUNDOS)


@router.post("/documento-unico",
             dependencies=[Depends(rate_limit("provas-documento-unico", 10))])
async def gerar_documento_unico(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera o PDF Visual Law "Documento Único de Anexos" do caso e retorna a URL
    de download (padrão tributario_fiscal). Requer ao menos uma prova."""
    case = await verificar_acesso_caso(db, cu, case_id)

    cli = (await db.execute(
        select(Client).where(Client.id == case.client_id)
    )).scalar_one_or_none()

    rows = (await db.execute(
        select(Prova, Document.titulo, Tese.titulo)
        .outerjoin(Document, Document.id == Prova.document_id)
        .outerjoin(Tese, Tese.id == Prova.tese_id)
        .where(Prova.case_id == case_id, Prova.deleted_at.is_(None))
        .order_by(Prova.ordem, Prova.created_at)
    )).all()
    if not rows:
        raise HTTPException(status_code=422,
                            detail="Nenhuma prova cadastrada neste caso.")

    provas = [{
        "tipo": p.tipo, "titulo": p.titulo, "descricao": p.descricao,
        "fato_probando": p.fato_probando,
        "documento_nome": doc_nome, "tese_titulo": tese_titulo,
    } for p, doc_nome, tese_titulo in rows]

    ramo = case.area.value if hasattr(case.area, "value") else str(case.area or "")
    caso_info = {
        "titulo": case.titulo,
        "numero": case.numero_processo or case.numero_interno or "—",
        "cliente": cli.nome_exibicao if cli else "—",
        "ramo": ramo,
    }

    try:
        from weasyprint import HTML as WP_HTML
    except ImportError as exc:
        raise HTTPException(503, f"Dependência de PDF não disponível: {exc}. "
                                 "Instale weasyprint.")

    html_full = _html_documento_unico(caso_info, provas)
    pdf_bytes = WP_HTML(string=html_full).write_pdf()

    out_dir = _provas_dir()
    _limpar_pdfs_antigos(out_dir)  # retenção LGPD (TTL) a cada geração
    arquivo_id = str(uuid4())
    path = os.path.join(out_dir, f"anexos_{arquivo_id}.pdf")
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "provas",
                          case_id, detalhes=f"documento único: {len(provas)} anexo(s)")
    await db.commit()
    return {"download_url": f"/casos/{case_id}/provas/documento-unico/{arquivo_id}/download"}


@router.get("/documento-unico/{arquivo_id}/download",
            dependencies=[Depends(rate_limit("provas-documento-download", 30))])
async def download_documento_unico(
    case_id: str,
    arquivo_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Download do PDF gerado. `arquivo_id` é validado como UUID (nunca
    interpolado livre no path — sem traversal). Exige acesso ao caso."""
    await verificar_acesso_caso(db, cu, case_id)
    # #27: validação anti-traversal (UUID) centralizada.
    _vlf.validar_uuid(arquivo_id)
    path = os.path.join(_provas_dir(), f"anexos_{arquivo_id}.pdf")
    if not os.path.isfile(path):
        raise HTTPException(404, "Documento não encontrado — gere via POST "
                                 "/casos/{case_id}/provas/documento-unico.")
    return FileResponse(path, media_type="application/pdf",
                        filename="documento_unico_anexos.pdf")
