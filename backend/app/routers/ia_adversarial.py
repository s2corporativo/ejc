# ── app/routers/ia_adversarial.py ────────────────────────────────────────────
# Modo Duas IAs (Fase 5): crítica adversarial SOB DEMANDA de qualquer texto de
# peça. A IA Crítica (advogado da parte contrária + magistrado) aponta
# contradições, lacunas fáticas, fragilidades probatórias, teses defensivas
# prováveis e jurisprudência contrária a verificar — preferindo provider
# DIFERENTE do que gerou a peça (se informado). Resultado é APOIO ao revisor
# humano (HITL); a própria crítica passa pelo gate de citações.
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.ai.adversarial import CriticaAdversarial, criticar_peca

router = APIRouter(prefix="/ia", tags=["IA — Crítica Adversarial (Duas IAs)"])


class CriticaAdversarialRequest(BaseModel):
    texto_peca: str = Field(..., min_length=50, max_length=200_000,
                            description="Texto integral da peça a criticar.")
    contexto_caso: str | None = Field(default=None, max_length=20_000,
                                      description="Contexto fático opcional (dossiê/resumo).")
    task_type_origem: str | None = Field(default=None, max_length=60,
                                         description="task_type que gerou a peça (ex: elaboracao_peca).")
    provedor_origem: str | None = Field(default=None, max_length=30,
                                        description="Provider que gerou a peça (ollama|anthropic|groq) — "
                                                    "a crítica prefere um DIFERENTE.")


@router.post("/critica-adversarial", response_model=CriticaAdversarial,
             dependencies=[Depends(rate_limit("critica-adversarial", 10))])
async def critica_adversarial_endpoint(
    req: CriticaAdversarialRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Executa a IA Crítica/Adversarial sobre um texto de peça (sob demanda).

    Nunca falha por indisponibilidade de provider: retorna `disponivel=false`
    com aviso. Uso registrado no AILog (LGPD/OAB); PII é barrada pelo
    ai_gateway antes de qualquer provider externo.
    """
    critica = await criticar_peca(
        db,
        texto_peca=req.texto_peca,
        contexto_caso=req.contexto_caso,
        task_type_origem=req.task_type_origem,
        provedor_origem=req.provedor_origem,
    )

    # Trilha de auditoria (padrão do projeto: todo uso de IA gera AILog).
    if critica.disponivel:
        from app.models.ai_log import AILog, AIStatusHITL, AITipoUso
        from app.services.sanitizer import sanitizar_pii
        prompt_log, pii = sanitizar_pii(req.texto_peca)
        db.add(AILog(
            id=str(uuid4()),
            user_id=cu.id,
            tipo_uso=AITipoUso.outro,
            modelo=f"{critica.provedor}/{critica.modelo}"[:50],
            prompt_sanitizado=("[CRITICA_ADVERSARIAL sob demanda]\n" + prompt_log)[:8000],
            pii_removida=pii,
            resposta=critica.relatorio,
            tokens_input=critica.tokens_input,
            tokens_output=critica.tokens_output,
            status_hitl=AIStatusHITL.gerado,
        ))
        await db.commit()

    return critica
