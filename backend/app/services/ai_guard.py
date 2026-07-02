# ── app/services/ai_guard.py ─────────────────────────────────────────────────
# Guarda única de PII/auditoria para endpoints de IA (auditoria 2026-07-02).
# Centraliza o padrão-ouro já usado em analise_estrategica.py: sanitizar_pii +
# segunda barreira (validar_sem_pii com abort) + AILog honesto (erro propaga,
# não é engolido). Endpoints que ainda montam AILog manualmente devem migrar
# para registrar_ai_log() em vez de reimplementar o INSERT.
from __future__ import annotations
from uuid import uuid4
from fastapi import HTTPException

from app.services.sanitizer import sanitizar_pii, validar_sem_pii
from app.models.ai_log import AILog, AIStatusHITL
from app.core.config import get_settings

settings = get_settings()


def sanitizar_ou_abortar(texto: str, nomes_proteger: list[str] | None = None) -> tuple[str, bool]:
    """
    Sanitiza PII e aplica a segunda barreira (checagem residual) com abort real.
    Levanta HTTPException 422 se sobrar PII estrutural (CPF/CNPJ/processo/RG/
    e-mail/telefone/CEP) após a sanitização — não deixa passar "quase limpo".

    Retorna (texto_sanitizado, houve_remocao).
    """
    limpo, houve_remocao = sanitizar_pii(texto, nomes_proteger)
    residual = validar_sem_pii(limpo)
    if residual:
        raise HTTPException(
            422,
            f"Dados pessoais detectados ({', '.join(residual)}) mesmo após "
            "sanitização. Remova CPF/CNPJ/RG/e-mail/telefone/CEP/número de "
            "processo do texto e tente novamente.",
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
