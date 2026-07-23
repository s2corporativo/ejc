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
from app.core.ownership import verificar_acesso_caso
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
    case_id: str | None = Field(default=None, max_length=64,
                                description="Caso ao qual a peça pertence. Quando informado, os nomes "
                                            "do caso (cliente/parte contrária) são pseudonimizados de "
                                            "forma REVERSÍVEL antes de qualquer provider externo (LGPD).")


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
    # Se o chamador vincula a crítica a um caso, exige acesso a ESSE caso — o
    # case_id só serve para montar as entidades a pseudonimizar, mas validar o
    # ownership mantém consistência com os demais endpoints de caso e evita que
    # evoluções futuras (surfacing de algo derivado das entidades) virem IDOR.
    if req.case_id:
        await verificar_acesso_caso(db, cu, req.case_id)

    critica = await criticar_peca(
        db,
        texto_peca=req.texto_peca,
        contexto_caso=req.contexto_caso,
        task_type_origem=req.task_type_origem,
        provedor_origem=req.provedor_origem,
        # Com case_id, monta as entidades nomeadas do caso p/ pseudonimização
        # reversível no gateway; sem ele, degrada com segurança (a barreira
        # estrutural do gateway segue ativa). LGPD: nomes não vazam ao externo.
        case_id=req.case_id,
    )

    # Trilha de auditoria (padrão do projeto: todo uso de IA gera AILog).
    if critica.disponivel:
        from app.models.ai_log import AILog, AIStatusHITL, AITipoUso, classificar_risco_ia
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
            risco_ia=classificar_risco_ia("elaboracao_peca"),
            status_hitl=AIStatusHITL.gerado,
        ))
        await db.commit()

    return critica
