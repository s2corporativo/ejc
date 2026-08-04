"""
Serviço de execução de AI Skills do EJC.
Usa ai_gateway.chat() para roteamento ao provedor e registra em ai_logs.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ai_skill import EjcSkill
from app.models.ai_log import AITipoUso, normalizar_modelo_ia
from app.services import ai_gateway
from app.services.ai_document_chunking import dividir_documento_em_blocos
from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log
from app.services.legal_base import garantir_identidade

logger = logging.getLogger("ejc.ai.skills")
settings = get_settings()

_ENGINE_PROVIDER = {"anthropic": "anthropic", "groq": "groq", "ollama": "ollama",
                    "maritaca": "maritaca"}

_AREA_TASK = {
    "juridico": "elaboracao_peca",
    "financeiro": "analise_juridica",
    "operacional": "resumo",
    "administrativo": "elaboracao_peca",
    "civel": "elaboracao_peca",
    "consumidor": "elaboracao_peca",
    "estrategia": "analise_juridica",
    "familia": "elaboracao_peca",
    "imobiliario": "elaboracao_peca",
    "penal": "elaboracao_peca",
    "previdenciario": "elaboracao_peca",
    "saude": "elaboracao_peca",
    "trabalhista": "elaboracao_peca",
    "provas": "resumo",
    "tributario": "elaboracao_peca",
}

# Roles com credencial para executar skills marcadas oab_restricted (produção de
# trabalho jurídico sob responsabilidade OAB). cliente_externo já é bloqueado
# antes (não acessa IA interna); estagiário/secretaria/financeiro ficam de fora.
_ROLES_OAB = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}


def _marcar_uso(skill: EjcSkill) -> None:
    """Incrementa o contador de uso da skill (Bloco 4 — enxugar catálogo,
    migration 130). Não commita — quem chama já commita junto do AILog na
    mesma transação (registrar_ai_log)."""
    skill.vezes_executado = (skill.vezes_executado or 0) + 1
    skill.ultima_execucao = datetime.now(timezone.utc)


async def skills_sem_uso(db: AsyncSession, dias_minimos: int = 90) -> list[EjcSkill]:
    """Skills ativas, criadas há mais de `dias_minimos` dias, nunca executadas
    (Bloco 4 — enxugar catálogo). Só relata — não arquiva nada; arquivar é
    decisão humana, feita com `PATCH /ai/skills/{id}` (active=False) depois
    de revisar esta lista. Skills recentes ficam de fora do relatório de
    propósito — nunca terem sido usadas ainda não significa que não serão."""
    from datetime import timedelta

    corte = datetime.now(timezone.utc) - timedelta(days=dias_minimos)
    result = await db.execute(
        select(EjcSkill)
        .where(
            EjcSkill.active == True,
            EjcSkill.vezes_executado == 0,
            EjcSkill.created_at < corte,
        )
        .order_by(EjcSkill.area, EjcSkill.display_name)
    )
    return result.scalars().all()


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
    user_role: str | None = None,
    entidades: dict[str, list[str]] | None = None,
) -> dict:
    result = await db.execute(
        select(EjcSkill).where(EjcSkill.name == skill_name, EjcSkill.active == True)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise ValueError(f"Skill '{skill_name}' não encontrada ou inativa.")

    # Enforcement de oab_restricted: skills que produzem trabalho jurídico sob
    # responsabilidade OAB só executam para roles com credencial. Antes esta
    # coluna era apenas descritiva (sem gate em runtime — achado de auditoria).
    if skill.oab_restricted and (user_role or "") not in _ROLES_OAB:
        raise PermissionError(
            f"Skill '{skill_name}' é restrita (OAB): seu perfil não tem permissão para executá-la."
        )

    # Guarda LGPD (auditoria 2026-07-02): query (texto digitado OU extraído via
    # OCR de documento de cliente em /execute-doc) ia direto ao provedor externo
    # sem sanitização — aborta se sobrar PII estrutural após a sanitização.
    query_limpa, pii = sanitizar_ou_abortar(query)
    nomes_entidades = [
        nome
        for nomes in (entidades or {}).values()
        for nome in nomes
    ]
    prompt_log, pii_nomes_prompt = sanitizar_ou_abortar(
        query_limpa, nomes_entidades
    )

    system_prompt = skill.system_prompt
    if contexto_rag:
        trechos = "\n\n---\n\n".join(
            f"Trecho {i+1}:\n{c}" for i, c in enumerate(contexto_rag)
        )
        system_prompt += f"\n\n## BASE DE CONHECIMENTO INTERNA:\n{trechos}"

    # Barreira anti-alucinação OBRIGATÓRIA: o system_prompt da skill é autoral
    # (gravado no banco) e o task_type derivado da área pode não passar por
    # aplicar_base no gateway — garantimos a identidade/regras OAB aqui.
    messages = garantir_identidade([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query_limpa},
    ])

    provider = _ENGINE_PROVIDER.get(skill.engine, "groq")
    task_type = _AREA_TASK.get(skill.area, "analise_juridica")

    resp = await ai_gateway.chat(
        messages=messages,
        task_type=task_type,
        provider_override=provider,
        nivel_inteligencia="alto",
        entidades=entidades,
    )

    inp = resp.input_tokens or 0
    out = resp.output_tokens or 0
    custo = float(resp.custo_estimado_brl or 0.0)
    resposta_log, pii_resposta = sanitizar_ou_abortar(
        resp.texto, nomes_entidades
    )

    modelo_log = f"{resp.provedor}/{resp.modelo}" if resp.provedor else resp.modelo
    _marcar_uso(skill)
    # registrar_ai_log PROPAGA erro (não engole em try/except com só warning) —
    # log de uso de IA é parte da própria correção, não pode falhar em silêncio.
    log_id = await registrar_ai_log(
        db,
        user_id=user_id,
        tipo_uso=AITipoUso.outro,
        case_id=case_id,
        prompt_sanitizado=prompt_log,
        pii_removida=pii or pii_nomes_prompt or pii_resposta,
        resposta=resposta_log,
        modelo=normalizar_modelo_ia(modelo_log),
        tokens_input=inp,
        tokens_output=out,
        custo_estimado=custo,
    )

    return {
        "conteudo": resp.texto,
        "skill": skill.display_name,
        "skill_name": skill.name,
        "engine": skill.engine,
        "is_rascunho": True,
        "requer_revisao": skill.requires_human_review,
        "tokens_usados": inp + out,
        "custo_estimado_brl": custo,
        "ai_log_id": log_id,
    }


async def executar_skill_documento_longo(
    *,
    db: AsyncSession,
    skill_name: str,
    texto_documento: str,
    instrucoes: str,
    user_id: str,
    case_id: str | None = None,
    contexto_rag: list[str] | None = None,
    user_role: str | None = None,
    entidades: dict[str, list[str]] | None = None,
) -> dict:
    """Executa uma skill sobre documento maior que a janela segura de 1 chamada.

    Usa map-reduce auditável: cada bloco gera uma ficha factual curta; apenas as
    fichas e as instruções seguem para a síntese final da skill. Um único AILog
    representa a operação lógica e soma tokens/custos de todas as chamadas.

    O limite é configurável para não prometer "centenas de páginas" em conta de
    provedor sem TPM suficiente. Acima dele a API falha de forma explícita, em
    vez de truncar e produzir uma conclusão aparentemente completa.
    """
    result = await db.execute(
        select(EjcSkill).where(EjcSkill.name == skill_name, EjcSkill.active == True)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise ValueError(f"Skill '{skill_name}' não encontrada ou inativa.")
    if skill.oab_restricted and (user_role or "") not in _ROLES_OAB:
        raise PermissionError(
            f"Skill '{skill_name}' é restrita (OAB): seu perfil não tem permissão para executá-la."
        )

    limite = settings.AI_LONG_DOCUMENT_MAX_CHARS
    tamanho_bloco = settings.AI_LONG_DOCUMENT_CHUNK_CHARS
    max_blocos = settings.AI_LONG_DOCUMENT_MAX_CHUNKS
    texto_documento = (texto_documento or "").strip()
    if len(texto_documento) > limite:
        raise ValueError(
            "Documento excede o limite seguro desta análise imediata "
            f"({limite:,} caracteres). Importe-o em Documentos/Data Room para "
            "indexação integral ou aumente AI_LONG_DOCUMENT_MAX_CHARS junto com "
            "o limite de tokens do provedor."
        )

    blocos = dividir_documento_em_blocos(
        texto_documento,
        tamanho=tamanho_bloco,
    )
    if not blocos:
        raise ValueError("Documento sem texto útil para análise.")
    if len(blocos) > max_blocos:
        raise ValueError(
            f"Documento gerou {len(blocos)} blocos; o limite operacional é "
            f"{max_blocos}. Use a indexação integral em Documentos/Data Room."
        )

    instrucoes_limpas, pii_instrucoes = sanitizar_ou_abortar(
        (instrucoes or "").strip()[:4000]
    )
    nomes_entidades = [
        nome
        for nomes in (entidades or {}).values()
        for nome in nomes
    ]
    provider = _ENGINE_PROVIDER.get(skill.engine, "groq")
    semaforo = asyncio.Semaphore(2)

    async def resumir_bloco(indice: int, bruto: str):
        limpo, pii = sanitizar_ou_abortar(bruto)
        mensagens = garantir_identidade([
            {
                "role": "system",
                "content": (
                    "Você faz EXTRAÇÃO FACTUAL PARCIAL de documento jurídico. "
                    "Analise somente o bloco recebido; não redija a peça final e "
                    "não complete lacunas. Entregue no máximo 12 itens curtos: "
                    "datas/atos, partes, alegações, pedidos, decisões, provas, "
                    "valores, prazos expressos, contradições e pontos inaudíveis/"
                    "ilegíveis. Preserve marcadores de página quando existirem."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"DOCUMENTO ENVIADO — BLOCO {indice + 1} "
                    f"DE {len(blocos)}\n\n{limpo}"
                ),
            },
        ])
        async with semaforo:
            resposta = await ai_gateway.chat(
                messages=mensagens,
                task_type="resumo",
                provider_override=provider,
                nivel_inteligencia="alto",
                max_tokens=500,
                entidades=entidades,
            )
        return indice, resposta, pii

    parciais = await asyncio.gather(
        *(resumir_bloco(i, bloco) for i, bloco in enumerate(blocos))
    )
    parciais.sort(key=lambda item: item[0])

    fichas = "\n\n".join(
        f"### BLOCO {indice + 1}/{len(blocos)}\n{resposta.texto}"
        for indice, resposta, _ in parciais
    )
    system_prompt = skill.system_prompt
    if contexto_rag:
        trechos = "\n\n---\n\n".join(
            f"Trecho RAG {i + 1}:\n{c}" for i, c in enumerate(contexto_rag)
        )
        system_prompt += f"\n\n## BASE INTERNA RECUPERADA:\n{trechos}"
    system_prompt += (
        "\n\nO documento foi lido em blocos. As fichas abaixo são intermediárias: "
        "não trate ausência na ficha como ausência nos autos; sinalize tudo o "
        "que exigir conferência no original. Não invente número de página."
    )
    mensagem_final = (
        (f"INSTRUÇÕES DO USUÁRIO:\n{instrucoes_limpas}\n\n" if instrucoes_limpas else "")
        + f"FICHAS FACTUAIS DO DOCUMENTO ENVIADO:\n\n{fichas}"
    )
    final = await ai_gateway.chat(
        messages=garantir_identidade([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": mensagem_final},
        ]),
        task_type=_AREA_TASK.get(skill.area, "analise_juridica"),
        provider_override=provider,
        nivel_inteligencia="alto",
        max_tokens=3000,
        entidades=entidades,
    )

    respostas = [item[1] for item in parciais] + [final]
    tokens_input = sum(r.input_tokens or 0 for r in respostas)
    tokens_output = sum(r.output_tokens or 0 for r in respostas)
    custo = sum(float(r.custo_estimado_brl or 0) for r in respostas)
    resposta_log, pii_resposta = sanitizar_ou_abortar(
        final.texto, nomes_entidades
    )
    prompt_log, pii_nomes_prompt = sanitizar_ou_abortar(
        instrucoes_limpas, nomes_entidades
    )
    pii_removida = (
        pii_instrucoes
        or pii_nomes_prompt
        or pii_resposta
        or any(item[2] for item in parciais)
    )
    modelo_log = f"{final.provedor}/{final.modelo}" if final.provedor else final.modelo
    _marcar_uso(skill)
    log_id = await registrar_ai_log(
        db,
        user_id=user_id,
        tipo_uso=AITipoUso.resumo_documento,
        case_id=case_id,
        prompt_sanitizado=(
            f"[DOCUMENTO LONGO; caracteres={len(texto_documento)}; "
            f"blocos={len(blocos)}]\n{prompt_log}"
        ),
        pii_removida=pii_removida,
        resposta=resposta_log,
        modelo=normalizar_modelo_ia(modelo_log),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        custo_estimado=custo,
    )
    return {
        "conteudo": final.texto,
        "skill": skill.display_name,
        "skill_name": skill.name,
        "engine": skill.engine,
        "is_rascunho": True,
        "requer_revisao": skill.requires_human_review,
        "tokens_usados": tokens_input + tokens_output,
        "custo_estimado_brl": custo,
        "ai_log_id": log_id,
        "processamento": {
            "modo": "map_reduce",
            "caracteres": len(texto_documento),
            "blocos": len(blocos),
            "truncado": False,
        },
    }
