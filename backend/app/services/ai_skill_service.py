"""
Serviço de execução de AI Skills do EJC.
Usa ai_gateway.chat() para roteamento ao provedor e registra em ai_logs.
"""
from __future__ import annotations
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_skill import EjcSkill
from app.models.ai_log import AITipoUso, normalizar_modelo_ia
from app.services import ai_gateway
from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log

logger = logging.getLogger("ejc.ai.skills")

_ENGINE_PROVIDER = {"anthropic": "anthropic", "groq": "groq", "ollama": "ollama"}

_AREA_TASK = {
    "juridico": "elaboracao_peca",
    "financeiro": "analise_juridica",
    "operacional": "resumo",
}


async def listar_skills(db: AsyncSession, area: str | None = None) -> list[EjcSkill]:
    q = select(EjcSkill).where(EjcSkill.active == True)
    if area:
        q = q.where(EjcSkill.area == area)
    result = await db.execute(q.order_by(EjcSkill.area, EjcSkill.display_name))
    return result.scalars().all()


async def executar_skill(
    db: AsyncSession,
    skill_name: str,
    query: str,
    user_id: str,
    case_id: str | None = None,
    contexto_rag: list[str] | None = None,
) -> dict:
    result = await db.execute(
        select(EjcSkill).where(EjcSkill.name == skill_name, EjcSkill.active == True)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise ValueError(f"Skill '{skill_name}' não encontrada ou inativa.")

    # Guarda LGPD (auditoria 2026-07-02): query (texto digitado OU extraído via
    # OCR de documento de cliente em /execute-doc) ia direto ao provedor externo
    # sem sanitização — aborta se sobrar PII estrutural após a sanitização.
    query_limpa, pii = sanitizar_ou_abortar(query)

    system_prompt = skill.system_prompt
    if contexto_rag:
        trechos = "\n\n---\n\n".join(
            f"Trecho {i+1}:\n{c}" for i, c in enumerate(contexto_rag)
        )
        system_prompt += f"\n\n## BASE DE CONHECIMENTO INTERNA:\n{trechos}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query_limpa},
    ]

    provider = _ENGINE_PROVIDER.get(skill.engine, "groq")
    task_type = _AREA_TASK.get(skill.area, "analise_juridica")

    resp = await ai_gateway.chat(
        messages=messages,
        task_type=task_type,
        provider_override=provider,
        nivel_inteligencia="alto",
    )

    inp = resp.input_tokens or 0
    out = resp.output_tokens or 0
    custo = ai_gateway._custo_brl(resp.modelo, inp, out) if provider == "anthropic" else 0.0

    modelo_log = f"{resp.provedor}/{resp.modelo}" if resp.provedor else resp.modelo
    # registrar_ai_log PROPAGA erro (não engole em try/except com só warning) —
    # log de uso de IA é parte da própria correção, não pode falhar em silêncio.
    await registrar_ai_log(
        db,
        user_id=user_id,
        tipo_uso=AITipoUso.outro,
        case_id=case_id,
        prompt_sanitizado=query_limpa,
        pii_removida=pii,
        resposta=resp.texto,
        modelo=normalizar_modelo_ia(modelo_log),
        tokens_input=inp,
        tokens_output=out,
        custo_estimado=custo,
    )

    return {
        "conteudo": resp.texto,
        "skill": skill.display_name,
        "engine": skill.engine,
        "is_rascunho": True,
        "requer_revisao": skill.requires_human_review,
        "tokens_usados": inp + out,
        "custo_estimado_brl": custo,
    }
