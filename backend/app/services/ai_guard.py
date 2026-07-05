# ── app/services/ai_guard.py ─────────────────────────────────────────────────
# Guarda única de PII/auditoria para endpoints de IA (auditoria 2026-07-02).
# Centraliza o padrão-ouro já usado em analise_estrategica.py: sanitizar_pii +
# segunda barreira (validar_sem_pii com abort) + AILog honesto (erro propaga,
# não é engolido). Endpoints que ainda montam AILog manualmente devem migrar
# para registrar_ai_log() em vez de reimplementar o INSERT.
from __future__ import annotations
from uuid import uuid4
from fastapi import HTTPException

from app.services.sanitizer import sanitizar_pii_interno, validar_sem_pii_interno
from app.models.ai_log import AILog, AIStatusHITL
from app.core.config import get_settings

settings = get_settings()


def sanitizar_ou_abortar(texto: str, nomes_proteger: list[str] | None = None) -> tuple[str, bool]:
    """
    Barreira de ENTRADA (uso interno do escritório, decisão de 2026-07-04):
    CPF/CNPJ deixam de ser removidos aqui (não abortam mais a chamada) —
    continuam sendo removidos processo/RG/e-mail/telefone/CEP/cartão/PIX/nomes
    protegidos, com abort real (422) se sobrar algum desses após a limpeza.

    Isso NÃO afeta a proteção de provider externo: `ai_gateway` aplica sua
    própria barreira final (`_sanitizar_messages_externo`, que usa
    `sanitizar_pii`/`validar_sem_pii` — as versões completas, com CPF/CNPJ)
    antes de qualquer chamada a Anthropic/Groq. Só o Ollama local recebe
    CPF/CNPJ em texto plano.

    Retorna (texto_sanitizado, houve_remocao).
    """
    limpo, houve_remocao = sanitizar_pii_interno(texto, nomes_proteger)
    residual = validar_sem_pii_interno(limpo)
    if residual:
        raise HTTPException(
            422,
            f"Dados pessoais detectados ({', '.join(residual)}) mesmo após "
            "sanitização. Remova RG/e-mail/telefone/CEP/número de processo "
            "do texto e tente novamente.",
        )
    return limpo, houve_remocao


async def registrar_ai_log(
    db,
    *,
    user_id: str,
    tipo_uso,
    case_id: str | None,
    prompt_sanitizado: str,
    pii_removida: bool,
    resposta: str | None,
    modelo: str | None = None,
    fontes_rag: str | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    custo_estimado=None,
) -> str:
    """
    Grava AILog. Erro de gravação PROPAGA (não é engolido em try/except com só
    um warning) — se o log falhar, a chamada de IA deve falhar também, porque
    IA sem rastro de auditoria é o próprio problema que este módulo corrige.
    """
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=case_id,
        tipo_uso=tipo_uso,
        modelo=modelo or settings.GROQ_MODEL,
        prompt_sanitizado=prompt_sanitizado[:8000],
        pii_removida=pii_removida,
        resposta=resposta,
        fontes_rag=fontes_rag,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        custo_estimado=custo_estimado,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()
    return log.id
