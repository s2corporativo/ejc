"""
Sala de Guerra EJC v3.0 — Tríade de Elite
IA Sentinela, Simulador War Room e Visual Law PDF.
"""
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.services.ia_sentinela import IASentinela
from app.services.war_room import war_room
from app.services.visual_law_pdf import visual_law_pdf

router = APIRouter(prefix="/sala-de-guerra-v3", tags=["Sala de Guerra"])

@router.get("/sentinela/auditoria")
async def auditoria_sentinela(db: AsyncSession = Depends(get_db), cu: User = Depends(get_current_user)):
    sentinela = IASentinela(db)
    return await sentinela.gerar_alertas_estrategicos()

@router.post("/war-room/simular")
async def simular_war_room(payload: dict, cu: User = Depends(get_current_user)):
    peticao = payload.get("peticao")
    if not peticao:
        raise HTTPException(400, "Petição inicial é necessária para simulação.")
    return await war_room.simular_contestacao(peticao)

@router.post("/visual-law/gerar-pdf")
async def gerar_pdf_visual(payload: dict, cu: User = Depends(get_current_user)):
    eventos = payload.get("eventos", [])
    # P1-3: grava no UPLOAD_DIR (volume persistente) e corrige strftime malformado
    # (%Y%6m%d era inválido). Antes gravava em /home/ubuntu (inexistente no container).
    out_dir = os.path.join(get_settings().UPLOAD_DIR, "visual_law")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"visual_law_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
    visual_law_pdf.gerar_cronologia(eventos, path)
    return {"status": "PDF gerado com sucesso", "path": path}
