"""
assistente.py — #37 Chat com o caso · #67 Detector de prazos em documentos.
IA via ai_gateway (Groq). #37 reusa o context engine (montar_dossie, sanitizado).
Ambos sanitizam PII antes do envio e marcam rascunho (HITL/OAB). Isolado.
"""
from __future__ import annotations
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.user import User
from app.models.case import Case
from app.services import ai_gateway
from app.services.sanitizer import sanitizar_pii
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/assistente", tags=["Assistente IA"])

_AVISO = "Rascunho gerado por IA — revisão do advogado responsável (OAB)."


def _vis(q, user: User):
    if ROLE_LEVEL.get(user.role.value, 0) >= ROLE_LEVEL["socio"]:
        return q
    return q.where(or_(Case.advogado_responsavel_id == user.id,
                       Case.advogado_auxiliar_id == user.id))


# ── #37 Chat com o caso ───────────────────────────────────────────────────────
class ChatMsg(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatReq(BaseModel):
    mensagens: list[ChatMsg] = Field(..., min_length=1, max_length=20)


@router.post("/cases/{case_id}/chat", dependencies=[Depends(rate_limit("assistente-chat", 20))])
async def chat_caso(case_id: str, req: ChatReq, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    """Conversa multi-turno sobre o caso, com contexto real injetado (sanitizado)."""
    q = _vis(select(Case).where(Case.id == case_id, Case.deleted_at.is_(None)), cu)
    if not (await db.execute(q)).scalar_one_or_none():
        raise HTTPException(404, "Caso não encontrado")

    from app.services.case_context import montar_dossie
    dossie = await montar_dossie(db, case_id, incluir_pecas=False, sanitizar=True)
    ctx = ((dossie or {}).get("texto") or "")[:8000]

    system = (
        "Você é o assistente jurídico DESTE caso. Responda às perguntas do advogado com base no "
        "CONTEXTO DO CASO abaixo e em conhecimento jurídico geral. Se um dado não constar do "
        "contexto, diga que não consta — NÃO invente fatos, lei, súmula ou número de processo. "
        "Toda resposta é rascunho para conferência do advogado (OAB).\n\n"
        f"=== CONTEXTO DO CASO ===\n{ctx}"
    )
    historico = []
    houve_pii = False
    for m in req.mensagens[-12:]:
        limpo, teve = sanitizar_pii(m.content)
        houve_pii = houve_pii or teve
        historico.append({"role": m.role, "content": limpo})

    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": system}] + historico,
        task_type="chat_rapido", temperature=0.3, max_tokens=1200,
    )

    # Auditoria: toda interação de IA deixa rastro em ai_logs (HITL/LGPD).
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso
    ultima_pergunta = next(
        (m["content"] for m in reversed(historico) if m["role"] == "user"), ""
    )
    log_id = await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.analise_caso, case_id=case_id,
        prompt_sanitizado=ultima_pergunta, pii_removida=houve_pii,
        resposta=resp.texto, modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
    )
    return {"resposta": resp.texto, "modelo": f"{resp.provedor}/{resp.modelo}",
            "is_draft": True, "is_rascunho": True, "aviso": _AVISO,
            "aviso_hitl": _AVISO, "log_id": log_id}


# ── #67 Detector de prazos em documentos ─────────────────────────────────────
class PrazosReq(BaseModel):
    texto: str = Field(..., min_length=20, max_length=40000)


_SYS_PRAZOS = (
    "Extraia do texto APENAS prazos e datas processuais que apareçam EXPLICITAMENTE. "
    "NÃO invente datas nem prazos. Responda SOMENTE em JSON: "
    '{"prazos":[{"data":"DD/MM/AAAA ou descrição","descricao":"o que é","tipo":"processual|audiencia|administrativo|interno"}]}'
)


@router.post("/detectar-prazos", dependencies=[Depends(rate_limit("assistente-prazos", 15))])
async def detectar_prazos(req: PrazosReq, db: AsyncSession = Depends(get_db),
                          cu: User = Depends(get_current_user)):
    """Sugere prazos encontrados num documento — o advogado confirma e cria."""
    limpo, houve_pii = sanitizar_pii(req.texto)
    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": _SYS_PRAZOS},
                  {"role": "user", "content": limpo[:30000]}],
        task_type="analise_juridica", temperature=0.1, max_tokens=900,
    )
    txt = resp.texto or ""
    try:
        data = json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        try:
            data = json.loads(m.group(0)) if m else {"prazos": []}
        except Exception:
            data = {"prazos": []}
    prazos = data.get("prazos", []) if isinstance(data, dict) else []

    # Auditoria: toda interação de IA deixa rastro em ai_logs (HITL/LGPD).
    from app.services.ai_guard import registrar_ai_log
    from app.models.ai_log import AITipoUso
    log_id = await registrar_ai_log(
        db, user_id=cu.id, tipo_uso=AITipoUso.outro, case_id=None,
        prompt_sanitizado=limpo[:8000], pii_removida=houve_pii,
        resposta=txt[:8000], modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
    )
    return {
        "prazos": prazos, "total": len(prazos), "is_draft": True,
        "is_rascunho": True, "log_id": log_id,
        "aviso": ("Prazos SUGERIDOS pela IA — o advogado confere e cria no módulo de prazos. "
                  "NÃO são criados automaticamente (IA não agenda prazo sozinha)."),
        "aviso_hitl": "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
    }
