# ── app/services/ai_guard.py ─────────────────────────────────────────────────
# Guarda única de PII/auditoria para endpoints de IA (auditoria 2026-07-02).
# Centraliza o padrão-ouro já usado em analise_estrategica.py: sanitizar_pii +
# AILog honesto (erro propaga, não é engolido). Endpoints que ainda montam AILog
# manualmente devem migrar para registrar_ai_log() em vez de reimplementar o
# INSERT.
from __future__ import annotations
import logging
from uuid import uuid4

from app.services.sanitizer import sanitizar_pii_interno, validar_sem_pii_interno
from app.models.ai_log import AILog, AIStatusHITL
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("ejc.ai.guard")


def sanitizar_ou_abortar(texto: str, nomes_proteger: list[str] | None = None) -> tuple[str, bool]:
    """
    Barreira de ENTRADA — "sanitiza e SEGUE" (decisão de produto 2026-07-06).

    Antes esta barreira ABORTAVA (HTTP 422) quando sobrava PII residual após a
    limpeza de entrada. Isso bloqueava análises legítimas do escritório. Agora
    ela NÃO aborta mais: sanitiza o texto internamente (remove processo/RG/e-mail/
    telefone/CEP/cartão/PIX/nomes protegidos; CPF/CNPJ seguem íntegros para o
    Ollama local, decisão de 2026-07-04) e apenas REGISTRA (log) que houve PII
    residual, seguindo o fluxo. O nome/contrato é mantido por compatibilidade.

    Segurança preservada: a proteção real de provider externo é a barreira FINAL
    do `ai_gateway` (`_preparar_mensagens_externo` → pseudonimização/mascaramento
    + `validar_sem_pii*`), que PULA o provider externo se ainda houver PII —
    NENHUM PII real chega a Anthropic/Groq mesmo sem este abort de entrada. Só o
    Ollama local recebe CPF/CNPJ em texto plano.

    Retorna (texto_sanitizado, houve_remocao).
    """
    limpo, houve_remocao = sanitizar_pii_interno(texto, nomes_proteger)
    residual = validar_sem_pii_interno(limpo)
    if residual:
        # Não aborta: registra os TIPOS de PII residual (nunca o valor/texto —
        # LGPD) para auditoria; a barreira final do gateway garante o não-vazamento.
        logger.info(
            "[ai_guard] PII residual após sanitização de entrada (%s) — "
            "seguindo; barreira final do gateway protege o provider externo.",
            ", ".join(sorted(residual)),
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
