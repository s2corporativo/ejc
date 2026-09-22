from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ownership import verificar_acesso_caso
from app.models.manus_task import ManusTask
from app.models.user import User
from app.services.ai_guard import sanitizar_ou_abortar
from app.services.ai.pseudonymizer import pseudonimizar, validar_sem_pii_pseudonimizado
from app.services.manus_client import ManusAPIError, ManusClient, ManusDisabledError

logger = logging.getLogger("ejc.manus.service")

MANUS_CASE_INTELLIGENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "resumo": {"type": "string"},
        "questoes_juridicas": {"type": "array", "items": {"type": "string"}},
        "fatos_relevantes": {"type": "array", "items": {"type": "string"}},
        "riscos": {"type": "array", "items": {"type": "string"}},
        "provas_faltantes": {"type": "array", "items": {"type": "string"}},
        "proximas_acoes": {"type": "array", "items": {"type": "string"}},
        "fontes": {"type": "array", "items": {"type": "string"}},
        "lacunas": {"type": "array", "items": {"type": "string"}},
        "revisao_obrigatoria": {"type": "boolean"},
    },
    "required": [
        "resumo", "questoes_juridicas", "fatos_relevantes", "riscos",
        "provas_faltantes", "proximas_acoes", "fontes", "lacunas",
        "revisao_obrigatoria",
    ],
    "additionalProperties": False,
}


def _status_from_webhook(payload: dict[str, Any]) -> tuple[str, str | None]:
    detail = payload.get("task_detail") or {}
    return ("waiting" if detail.get("stop_reason") == "ask" else "completed"), detail.get("stop_reason")


def _structured_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    detail = payload.get("task_detail") or {}
    structured = detail.get("structured_output")
    if not isinstance(structured, dict) or structured.get("success") is not True:
        return None
    value = structured.get("value")
    return value if isinstance(value, dict) else None


async def iniciar_analise(
    db: AsyncSession,
    *,
    user: User,
    case_id: str,
    texto: str,
    area: str | None = None,
    profile: str = "standard",
) -> ManusTask:
    settings = get_settings()
    if not settings.MANUS_API_ENABLED:
        raise HTTPException(status_code=503, detail="Integração Manus desativada")
    if not settings.AI_EXTERNAL_PROVIDERS_ALLOWED:
        raise HTTPException(status_code=422, detail="Provedores externos de IA estão bloqueados")
    caso = await verificar_acesso_caso(db, user, case_id)
    if getattr(caso, "sigilo_reforcado", False):
        raise HTTPException(status_code=422, detail="Caso com sigilo reforçado exige execução local")
    if len(texto.strip()) < 30:
        raise HTTPException(status_code=422, detail="Texto insuficiente para análise")

    # A Manus é um provedor externo independente do gateway síncrono: aplica a
    # mesma barreira de entrada e uma segunda validação explícita antes do POST.
    texto_limpo, _ = sanitizar_ou_abortar(texto)
    texto_pseudo = pseudonimizar([{"role": "user", "content": texto_limpo}])[0][0]["content"]
    residual = validar_sem_pii_pseudonimizado(texto_pseudo)
    if residual:
        raise HTTPException(status_code=422, detail="Conteúdo contém dados pessoais não aptos para provedor externo")
    prompt = (
        "Você é um analista jurídico auxiliar. Produza somente um rascunho, sem "
        "inventar fatos, fontes, jurisprudência ou endereços. Diferencie alegação, "
        "fato comprovado e lacuna. Toda recomendação exige revisão humana.\n\n"
        f"ÁREA: {area or 'não informada'}\n"
        f"CONTEÚDO SANITIZADO DO CASO:\n{texto_pseudo}\n"
        "Retorne o objeto conforme o schema fornecido."
    )
    client = ManusClient()
    try:
        resposta = await client.create_task(
            content=prompt,
            title="EJC — inteligência jurídica (rascunho)",
            structured_output_schema=MANUS_CASE_INTELLIGENCE_SCHEMA,
            agent_profile=profile,
        )
    except ManusDisabledError as exc:
        raise HTTPException(status_code=503, detail="Credencial Manus não configurada") from exc
    except ManusAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    manus_task_id = str(resposta.get("task_id") or "")
    if not manus_task_id:
        raise HTTPException(status_code=502, detail="Manus não retornou identificador de tarefa")
    registro = ManusTask(
        id=str(uuid4()),
        manus_task_id=manus_task_id,
        user_id=user.id,
        case_id=case_id,
        task_type="case_intelligence",
        status="created",
        prompt_sanitizado=prompt[:12000],
        mensagem_sanitizada=texto_pseudo[:12000],
        request_id=resposta.get("request_id"),
        task_url=resposta.get("task_url"),
    )
    db.add(registro)
    await db.commit()
    await db.refresh(registro)
    return registro


async def aplicar_webhook(db: AsyncSession, payload: dict[str, Any]) -> ManusTask | None:
    detail = payload.get("task_detail") or {}
    manus_task_id = detail.get("task_id")
    event_id = payload.get("event_id")
    if not manus_task_id or not event_id:
        return None
    registro = (await db.execute(select(ManusTask).where(ManusTask.manus_task_id == manus_task_id))).scalar_one_or_none()
    if registro is None:
        return None
    if registro.ultimo_evento_id == event_id:
        return registro
    registro.ultimo_evento_id = str(event_id)
    if payload.get("event_type") == "task_created":
        registro.status = "running"
        registro.started_at = registro.started_at or datetime.now(timezone.utc)
    elif payload.get("event_type") == "task_stopped":
        registro.status, registro.stop_reason = _status_from_webhook(payload)
        registro.completed_at = datetime.now(timezone.utc) if registro.status == "completed" else None
        resultado = _structured_result(payload)
        if resultado is not None:
            registro.resultado_json = resultado
        elif registro.status == "completed":
            registro.erro_codigo = "structured_output_unavailable"
            registro.erro_mensagem = "Manus concluiu sem saída estruturada válida"
            registro.status = "failed"
    await db.commit()
    await db.refresh(registro)
    return registro


async def obter_tarefa(db: AsyncSession, *, task_id: str, user: User) -> ManusTask:
    registro = (await db.execute(select(ManusTask).where(ManusTask.id == task_id))).scalar_one_or_none()
    if registro is None:
        raise HTTPException(status_code=404, detail="Análise Manus não encontrada")
    if registro.user_id != user.id and getattr(user.role, "value", user.role) not in {"admin", "superadmin", "socio"}:
        raise HTTPException(status_code=403, detail="Sem acesso a esta análise")
    return registro
