"""
Sala de Guerra EJC v3.0 — Tríade de Elite
IA Sentinela, Simulador War Room e Visual Law PDF.

P1 (2026-07-05) — Visual Law PDF com download real:
  POST /sala-de-guerra-v3/visual-law/{case_id}           → {"download_url": ...}
  GET  /sala-de-guerra-v3/visual-law/{case_id}/download  → FileResponse (PDF)
Contrato fixo consumido pelo frontend (tela Sala de Guerra). O endpoint antigo
/visual-law/gerar-pdf retornava o PATH do filesystem (inútil para o browser) e
não tinha vínculo com caso — substituído; não havia consumidores.
"""
import os
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.core.config import get_settings
from app.models.user import User
from app.services.ia_sentinela import IASentinela
from app.services.war_room import war_room
from app.services.visual_law_pdf import visual_law_pdf

router = APIRouter(prefix="/sala-de-guerra-v3", tags=["Sala de Guerra"])


@router.get("/sentinela/auditoria", dependencies=[Depends(rate_limit("sentinela-auditoria", 10))])
async def auditoria_sentinela(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    # IASentinela varre TODA a carteira do escritório → restrito a gestão (socio+).
    if not is_gestao(cu):
        raise HTTPException(403, "Auditoria estratégica restrita à gestão")
    sentinela = IASentinela(db)
    return await sentinela.gerar_alertas_estrategicos()


@router.post("/war-room/simular", dependencies=[Depends(rate_limit("war-room-simular", 10))])
async def simular_war_room(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Simula o advogado da parte contrária (War Room) via shim ai_brain.
    Auditoria: rastro obrigatório em ai_logs (HITL/LGPD) — mesmo padrão de
    diplomacia_v3.py::dossie_pressao. Contrato de resposta inalterado (str)."""
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso
    from app.services.sanitizer import sanitizar_pii

    peticao = payload.get("peticao")
    if not peticao:
        raise HTTPException(400, "Petição inicial é necessária para simulação.")

    case_id = payload.get("case_id")
    if case_id:
        await verificar_acesso_caso(db, cu, case_id)

    resultado = await war_room.simular_contestacao(peticao)

    # Prompt logado já sanitizado (o shim ai_brain aplica a mesma sanitização
    # antes do envio ao gateway central) — nunca grava PII bruta no AILog.
    prompt_limpo, houve_pii = sanitizar_pii(peticao)
    await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso,
        case_id=case_id,
        prompt_sanitizado=prompt_limpo, pii_removida=houve_pii,
        resposta=resultado,
    )
    return resultado


# ── Visual Law PDF (cronologia por caso) ──────────────────────────────────────

def _visual_law_path(case_id: str) -> str:
    """Path determinístico por caso no volume persistente (UPLOAD_DIR).
    Regeração sobrescreve — o download sempre serve a versão mais recente.
    case_id já foi validado contra o banco (gate de visibilidade) antes de
    chegar aqui — não é entrada livre para path traversal."""
    out_dir = os.path.join(get_settings().UPLOAD_DIR, "visual_law")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"cronologia_{case_id}.pdf")


@router.post("/visual-law/{case_id}",
             dependencies=[Depends(rate_limit("visual-law-pdf", 10))])
async def gerar_visual_law(
    case_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Gera o PDF da cronologia Visual Law do caso e retorna a URL de download
    (nunca o path do filesystem). Eventos: do payload {"eventos": [...]} ou,
    se ausentes, a cronologia REAL do caso (montar_eventos_caso — movimentos +
    prazos + documentos + honorários)."""
    from app.routers.visual_law import _obter_caso_visivel
    await _obter_caso_visivel(db, cu, case_id)  # 404 se inexistente/invisível

    eventos = (payload or {}).get("eventos") or None
    if eventos is None:
        from app.services.visual_law_core import montar_eventos_caso
        brutos = await montar_eventos_caso(db, case_id)
        eventos = [{
            "data": (e["data"].strftime("%d/%m/%Y")
                     if hasattr(e["data"], "strftime") else e["data"]),
            "evento": f"[{e['categoria']}] {e['descricao']}",
        } for e in brutos]

    visual_law_pdf.gerar_cronologia(eventos, _visual_law_path(case_id))
    return {"download_url": f"/sala-de-guerra-v3/visual-law/{case_id}/download"}


@router.get("/visual-law/{case_id}/download")
async def download_visual_law(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Download do PDF gerado pelo POST acima. Mesmo gate de visibilidade do
    caso; 404 se o PDF ainda não foi gerado."""
    from app.routers.visual_law import _obter_caso_visivel
    await _obter_caso_visivel(db, cu, case_id)

    path = _visual_law_path(case_id)
    if not os.path.isfile(path):
        raise HTTPException(
            404, "PDF ainda não gerado para este caso — use POST "
                 "/sala-de-guerra-v3/visual-law/{case_id} antes.")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"cronologia_{case_id}.pdf")
