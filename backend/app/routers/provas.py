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

import os
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
from app.core.security import get_current_user
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.document import Document
from app.models.prova import Prova
from app.models.tese import Tese
from app.models.user import User
from app.schemas.common import MsgResponse
from app.schemas.prova import ProvaCreate, ProvaUpdate

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
