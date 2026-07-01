"""
Serviço de execução de AI Skills do EJC.
Usa ai_gateway.chat() para roteamento ao provedor e registra em ai_logs.
"""
from __future__ import annotations
import logging
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_skill import EjcSkill
from app.services import ai_gateway

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

    system_prompt = skill.system_prompt
    if contexto_rag:
        trechos = "\n\n---\n\n".join(
            f"Trecho {i+1}:\n{c}" for i, c in enumerate(contexto_rag)
        )
        system_prompt += f"\n\n## BASE DE CONHECIMENTO INTERNA:\n{trechos}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
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

    prompt_san = query[:500].replace("'", "''")
    from app.models.ai_log import normalizar_modelo_ia  # BUG-22: nome canônico
    modelo_log = f"{resp.provedor}/{resp.modelo}" if resp.provedor else resp.modelo
    try:
        await db.execute(text("""
            INSERT INTO ai_logs
                (id, user_id, case_id, tipo_uso, modelo,
                 prompt_sanitizado, tokens_input, tokens_output,
                 custo_estimado, status_hitl, created_at)
            VALUES
                (:id, :uid, :cid, 'outro', :modelo,
                 :prompt, :ti, :to, :custo, 'gerado', now())
        """), {
            "id": str(uuid4()), "uid": user_id, "cid": case_id,
            "modelo": normalizar_modelo_ia(modelo_log),
            "prompt": prompt_san, "ti": inp, "to": out, "custo": custo,
        })
        await db.commit()
    except Exception as e:
        logger.warning(f"[Skills] ai_logs insert falhou: {e}")

    return {
        "conteudo": resp.texto,
        "skill": skill.display_name,
        "engine": skill.engine,
        "is_rascunho": True,
        "requer_revisao": skill.requires_human_review,
        "tokens_usados": inp + out,
        "custo_estimado_brl": custo,
    }
