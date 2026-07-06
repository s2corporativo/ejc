# ── app/routers/dossie_estrategico.py ─────────────────────────────────────────
# Dossiê Estratégico — geração versionada por caso com aprovação HITL.
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.dossie_estrategico import DossieEstrategico, DossieStatus
from app.services.dossie_service import gerar_dossie
from app.modules.auditoria.middleware import registrar_acao

router = APIRouter(prefix="/dossie", tags=["Dossiê Estratégico"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class GerarDossieReq(BaseModel):
    titulo: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pode_ver(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["estagiario"]

def _pode_gerar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["advogado"]

def _pode_aprovar(u: User) -> bool:
    return ROLE_LEVEL.get(u.role.value, 0) >= ROLE_LEVEL["socio"]

def _out(d: DossieEstrategico, incluir_conteudo: bool = True) -> dict:
    base = {
        "id":          d.id,
        "case_id":     d.case_id,
        "versao":      d.versao,
        "titulo":      d.titulo,
        "status":      d.status.value if hasattr(d.status, "value") else d.status,
        "modelo_ia":   d.modelo_ia,
        "provedor_ia": d.provedor_ia,
        "tokens_usados": d.tokens_usados,
        "gerado_por":  d.gerado_por,
        "aprovado_por": d.aprovado_por,
        "aprovado_em":  d.aprovado_em.isoformat() if d.aprovado_em else None,
        "created_at":   d.created_at.isoformat() if d.created_at else None,
    }
    if incluir_conteudo:
        base["conteudo_texto"] = d.conteudo_texto
        base["conteudo_html"]  = d.conteudo_html
    return base


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{case_id}/gerar", status_code=201)
async def gerar(
    case_id: str,
    req:     GerarDossieReq = GerarDossieReq(),
    db:      AsyncSession = Depends(get_db),
    cu:      User = Depends(get_current_user),
):
    """
    Gera nova versão do dossiê estratégico para o caso.
    O resultado é um RASCUNHO — revisão humana obrigatória antes de aprovar.
    """
    if not _pode_gerar(cu):
        raise HTTPException(403, "Apenas advogados ou sócios podem gerar dossiês.")
    # Bloco 5 (continuação): só existência era checada — advogado+ de qualquer
    # caso podia gerar o dossiê ESTRATÉGICO (conteúdo sensível: teses, pontos
    # fracos) de caso alheio. verificar_acesso_caso cobre existência + ownership.
    await verificar_acesso_caso(db, cu, case_id)
    dossie = await gerar_dossie(db, case_id, cu.id, req.titulo)
    return _out(dossie)


@router.get("/{case_id}")
async def obter_atual(
    case_id: str,
    db:      AsyncSession = Depends(get_db),
    cu:      User = Depends(get_current_user),
):
    """Retorna o dossiê aprovado mais recente; se não houver, retorna o último rascunho."""
    if not _pode_ver(cu):
        raise HTTPException(403)
    # IDOR: conteúdo estratégico sensível — restringe a quem atua no caso (ou gestão).
    await verificar_acesso_caso(db, cu, case_id)
    # Preferência: aprovado mais recente
    dossie = (await db.execute(
        select(DossieEstrategico)
        .where(DossieEstrategico.case_id == case_id,
               DossieEstrategico.status == DossieStatus.aprovado)
        .order_by(DossieEstrategico.versao.desc())
        .limit(1)
    )).scalar_one_or_none()

    if not dossie:
        # fallback: rascunho mais recente
        dossie = (await db.execute(
            select(DossieEstrategico)
            .where(DossieEstrategico.case_id == case_id)
            .order_by(DossieEstrategico.versao.desc())
            .limit(1)
        )).scalar_one_or_none()

    if not dossie:
        raise HTTPException(404, "Nenhum dossiê encontrado para este caso.")
    return _out(dossie)


@router.get("/{case_id}/historico")
async def historico(
    case_id: str,
    status:  Optional[str] = Query(None),
    db:      AsyncSession = Depends(get_db),
    cu:      User = Depends(get_current_user),
):
    """Lista todas as versões do dossiê, da mais recente para a mais antiga."""
    if not _pode_ver(cu):
        raise HTTPException(403)
    # IDOR: conteúdo estratégico sensível — restringe a quem atua no caso (ou gestão).
    await verificar_acesso_caso(db, cu, case_id)
    q = (select(DossieEstrategico)
         .where(DossieEstrategico.case_id == case_id)
         .order_by(DossieEstrategico.versao.desc()))
    if status:
        q = q.where(DossieEstrategico.status == status)
    dossies = (await db.execute(q)).scalars().all()
    # Histórico não inclui conteúdo completo para economia
    return [_out(d, incluir_conteudo=False) for d in dossies]


@router.patch("/{case_id}/{dossie_id}/aprovar")
async def aprovar(
    case_id:  str,
    dossie_id: str,
    db:       AsyncSession = Depends(get_db),
    cu:       User = Depends(get_current_user),
):
    """
    Aprovação HITL — marca o dossiê como aprovado pelo sócio.
    Arquiva a versão aprovada anterior (se houver).
    """
    if not _pode_aprovar(cu):
        raise HTTPException(403, "Somente sócios podem aprovar dossiês.")
    dossie = (await db.execute(
        select(DossieEstrategico)
        .where(DossieEstrategico.id == dossie_id,
               DossieEstrategico.case_id == case_id)
    )).scalar_one_or_none()
    if not dossie:
        raise HTTPException(404)
    if dossie.status == DossieStatus.arquivado:
        raise HTTPException(400, "Dossiê arquivado não pode ser aprovado.")

    # Arquiva outros aprovados do mesmo caso
    anteriores = (await db.execute(
        select(DossieEstrategico)
        .where(DossieEstrategico.case_id == case_id,
               DossieEstrategico.status == DossieStatus.aprovado,
               DossieEstrategico.id != dossie_id)
    )).scalars().all()
    for ant in anteriores:
        ant.status = DossieStatus.arquivado
        ant.updated_at = datetime.now(timezone.utc)

    dossie.status       = DossieStatus.aprovado
    dossie.aprovado_por = cu.id
    dossie.aprovado_em  = datetime.now(timezone.utc)
    dossie.updated_at   = datetime.now(timezone.utc)
    await db.commit()

    await registrar_acao(db, cu.id, "aprovar", "dossie_estrategico", dossie.id,
                         f"Dossiê v{dossie.versao} aprovado para caso {case_id}")
    return _out(dossie)


@router.get("/{case_id}/{dossie_id}/pdf")
async def exportar_pdf(
    case_id:  str,
    dossie_id: str,
    db:       AsyncSession = Depends(get_db),
    cu:       User = Depends(get_current_user),
):
    """Exporta o dossiê em PDF via WeasyPrint. Requer dossiê aprovado ou rascunho."""
    if not _pode_ver(cu):
        raise HTTPException(403)
    # IDOR: conteúdo estratégico sensível — restringe a quem atua no caso (ou gestão).
    await verificar_acesso_caso(db, cu, case_id)

    dossie = (await db.execute(
        select(DossieEstrategico)
        .where(DossieEstrategico.id == dossie_id,
               DossieEstrategico.case_id == case_id)
    )).scalar_one_or_none()
    if not dossie:
        raise HTTPException(404)

    try:
        import markdown
        from weasyprint import HTML as WP_HTML
        from app.services import visual_law_theme as vlt

        aviso_hitl = ""
        if dossie.status != DossieStatus.aprovado:
            aviso_hitl = (
                "<div style='background:#fffbe6;border:1px solid #f0ad4e;"
                "border-left:4px solid " + vlt.OURO_CLARO + ";padding:12px;"
                "margin:16px 0;'><strong>RASCUNHO — Revisão Humana Obrigatória"
                "</strong><br>Este dossiê ainda não foi aprovado por um sócio.</div>"
            )

        corpo_html = markdown.markdown(
            dossie.conteudo_texto or "",
            extensions=["tables", "nl2br"],
        )
        # Padrão Visual Law central: banner dourado + logo + rodapé repetido.
        banner = vlt.render_banner(
            "DOSSIÊ ESTRATÉGICO",
            f"{dossie.titulo or 'Dossiê'} — v{dossie.versao}",
        )
        rodape_pdf = (
            f"De Paula Teixeira Advogados · Dossiê Estratégico v{dossie.versao} · "
            f"IA: {dossie.provedor_ia}/{dossie.modelo_ia}"
        )
        footer_html = (
            "<div style='margin-top:24px;font-size:8.5pt;color:#6b7280;"
            "border-top:1px solid #e5e7eb;padding-top:8px;'>Gerado em: "
            f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC | "
            f"IA: {dossie.provedor_ia}/{dossie.modelo_ia} | Versão {dossie.versao}</div>"
        )
        html_full = vlt.html_doc(
            banner + aviso_hitl + corpo_html + footer_html,
            css=vlt.css_fluxo(rodape_pdf),
        )
        pdf_bytes = WP_HTML(string=html_full).write_pdf()
        filename = f"dossie_v{dossie.versao}_{case_id[:8]}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ImportError as exc:
        raise HTTPException(
            503,
            f"Dependência de PDF não disponível: {exc}. Instale weasyprint e markdown.",
        )
