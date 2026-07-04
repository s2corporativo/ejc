# ── app/services/estilo_service.py ───────────────────────────────────────────
# Aprendizado de Estilo — destila e mantém o perfil de redação de cada advogado.
#
# Fluxo de destilação (LGPD + auditoria como os demais fluxos de IA):
#   texto aprovado → sanitizar_ou_abortar (barreira de entrada) → AI Gateway
#   (task_type "analise_juridica") → perfil destilado → registrar_ai_log.
#
# Ownership ESTRITO: todas as funções operam sempre sobre o user_id do advogado
# logado (nunca aceitam um user_id vindo do corpo da requisição). O router
# passa cu.id; um advogado jamais toca o estilo de outro.
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AITipoUso
from app.models.estilo_advogado import EstiloAdvogado
from app.services.ai_gateway import chat as gw_chat
from app.services.ai_guard import registrar_ai_log, sanitizar_ou_abortar

# Limite de caracteres da amostra enviada à IA (evita prompts gigantes).
_MAX_AMOSTRA = 12000
# Limite do perfil destilado persistido/reinjetado.
_MAX_PERFIL = 4000


async def obter_estilo(db: AsyncSession, user_id: str) -> EstiloAdvogado | None:
    """Perfil de estilo do advogado (ou None)."""
    return (
        await db.execute(
            select(EstiloAdvogado).where(EstiloAdvogado.user_id == user_id)
        )
    ).scalar_one_or_none()


def _prompt_destilacao(texto: str, perfil_atual: str | None) -> list[dict]:
    """Monta as mensagens para o Gateway destilar/refinar o perfil de estilo."""
    system = (
        "Você é um analista de escrita jurídica. A partir de uma peça APROVADA por "
        "um advogado, destile o ESTILO DE REDAÇÃO dele — não o conteúdo do caso. "
        "Descreva de forma objetiva e reutilizável: (1) tom e nível de formalidade; "
        "(2) conectivos e expressões de transição recorrentes; (3) estrutura típica "
        "de argumentação e de parágrafos; (4) vocabulário e expressões idiossincráticas; "
        "(5) uso de citações legais e jurisprudenciais; (6) tamanho médio de frases. "
        "NÃO reproduza fatos, nomes, números de processo ou dados do caso — apenas o "
        "PADRÃO DE ESCRITA. Responda em um bloco descritivo conciso (máx. ~400 palavras)."
    )
    if perfil_atual:
        user = (
            "PERFIL DE ESTILO ATUAL (destilado de peças anteriores):\n"
            f"{perfil_atual}\n\n"
            "NOVA PEÇA APROVADA (amostra adicional do mesmo advogado):\n"
            f"{texto}\n\n"
            "Refine e CONSOLIDE o perfil combinando o padrão atual com o observado na "
            "nova peça. Mantenha o que é estável, ajuste o que evoluiu e devolva o "
            "perfil consolidado (não um diff)."
        )
    else:
        user = (
            "PEÇA APROVADA (primeira amostra do advogado):\n"
            f"{texto}\n\n"
            "Destile o perfil de estilo inicial a partir desta peça."
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def destilar_amostra(
    db: AsyncSession,
    user_id: str,
    texto: str,
    substituir: bool = False,
) -> EstiloAdvogado:
    """
    Destila (ou refina) o perfil de estilo do advogado a partir de uma peça
    aprovada. Sanitiza a entrada (LGPD), chama o Gateway, grava AILog e persiste.

    substituir=True descarta o perfil anterior e trata a amostra como a primeira
    (n_amostras volta a 1). Caso contrário, refina o perfil e incrementa n_amostras.
    """
    # Barreira de entrada LGPD (aborta 422 se sobrar PII estrutural).
    texto_limpo, houve_pii = sanitizar_ou_abortar(texto[:_MAX_AMOSTRA])

    estilo = await obter_estilo(db, user_id)
    perfil_base = None if substituir else (estilo.perfil_estilo if estilo else None)

    messages = _prompt_destilacao(texto_limpo, perfil_base)
    resp = await gw_chat(
        messages=messages,
        task_type="analise_juridica",
        temperature=0.2,
        max_tokens=900,
    )
    novo_perfil = (resp.texto or "").strip()[:_MAX_PERFIL]

    if estilo is None:
        estilo = EstiloAdvogado(
            id=str(uuid4()),
            user_id=user_id,
            perfil_estilo=novo_perfil,
            n_amostras=1,
            ativo=True,
        )
        db.add(estilo)
    else:
        estilo.perfil_estilo = novo_perfil
        estilo.n_amostras = 1 if substituir else (estilo.n_amostras or 0) + 1

    # Auditoria canônica (erro de gravação PROPAGA).
    await registrar_ai_log(
        db,
        user_id=user_id,
        tipo_uso=AITipoUso.outro,
        case_id=None,
        prompt_sanitizado=texto_limpo,
        pii_removida=houve_pii,
        resposta=novo_perfil,
        modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
    )
    await db.commit()
    await db.refresh(estilo)
    return estilo


async def definir_ativo(
    db: AsyncSession, user_id: str, ativo: bool
) -> EstiloAdvogado | None:
    """Liga/desliga o uso do estilo na geração de peças. None se não há perfil."""
    estilo = await obter_estilo(db, user_id)
    if estilo is None:
        return None
    estilo.ativo = ativo
    await db.commit()
    await db.refresh(estilo)
    return estilo


async def limpar_estilo(db: AsyncSession, user_id: str) -> bool:
    """Remove o perfil de estilo do advogado. True se havia algo para remover."""
    estilo = await obter_estilo(db, user_id)
    if estilo is None:
        return False
    await db.delete(estilo)
    await db.commit()
    return True


async def instrucao_estilo(db: AsyncSession, user_id: str) -> str | None:
    """
    Bloco de instrução de estilo para o pipeline de peças, ou None quando o
    advogado não tem perfil, o perfil está vazio ou o estilo está desativado.
    """
    estilo = await obter_estilo(db, user_id)
    if estilo is None or not estilo.ativo:
        return None
    perfil = (estilo.perfil_estilo or "").strip()
    if not perfil:
        return None
    return (
        "ESTILO DO ADVOGADO (reproduza fielmente o padrão de escrita a seguir na "
        "redação, sem copiar conteúdo de outros casos):\n" + perfil
    )
