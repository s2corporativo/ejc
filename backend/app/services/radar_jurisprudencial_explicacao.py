# ── app/services/radar_jurisprudencial_explicacao.py ─────────────────────────
# Radar Jurisprudencial — Camada 3 (explicação por IA, PR 4, Commit 5).
#
# A IA NUNCA decide que uma tese está superada — ela só explica, em 1-2
# frases, por que uma decisão JÁ classificada pelas Camadas 1 (determinística)
# e 2 (semântica) PODE afetar a tese. Este módulo não participa da detecção
# de impacto; ele só enriquece um alerta que as camadas anteriores já
# produziram. A promoção real de `Tese.status_validacao` (ex.: "superada",
# "parcialmente_superada") continua sendo SOMENTE ato humano via
# `POST /teses/{tese_id}/validacao` (RBAC sócio+, gate de citações completo)
# — nada aqui escreve nessa coluna.
#
# Governança aplicada:
#   • task_type="resumo" — tier econômico já existente em ai_gateway (não
#     cria categoria nova de tarefa).
#   • hitl_policy.aplicar() — toda saída é rascunho, revisão sempre exigida.
#   • citation_gate.validar_citacoes() — se a explicação da IA trouxer
#     citação suspeita/não confirmada, o texto é SUPRIMIDO e substituído por
#     um aviso genérico; falha do próprio gate é tratada como suspeita
#     (fail-CLOSED aqui — texto de IA não sai sem passar pelo gate).
#   • AILog — toda chamada de IA é registrada, mesmo quando o texto acaba
#     suprimido (trilha auditável do que o modelo respondeu).
#   • Fail-open quanto ao ALERTA: qualquer falha (IA desligada, gateway
#     indisponível, erro do gate) devolve texto=None sem levantar — a
#     Camada 3 é enriquecimento, nunca pré-requisito para o alerta existir
#     (Camadas 1/2 já bastam).
from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ai_log import AILog, AIStatusHITL, AITipoUso
from app.services.ai.core.hitl_policy import aplicar as aplicar_hitl
from app.services.ai_gateway import chat as gw_chat
from app.services.citation_gate import validar_citacoes

logger = logging.getLogger("ejc.radar_jurisprudencial")

AVISO_PADRAO = "Possível impacto detectado — requer validação."
_AVISO_CITACAO_SUSPEITA = (
    f"{AVISO_PADRAO} (explicação suprimida: citação não confirmada pelo "
    "gate anti-alucinação; revisar manualmente)"
)

_SYS_PROMPT = (
    "Você é um assistente jurídico. NÃO decida se a tese está superada — essa "
    "decisão é sempre humana, tomada depois via revisão manual. Escreva 1 a 2 "
    "frases explicando POR QUE esta decisão PODE impactar a tese, no "
    f"vocabulário técnico-jurídico brasileiro. Comece sempre com \"{AVISO_PADRAO}\". "
    "NÃO invente número de processo, súmula, tema ou artigo de lei que não "
    "esteja no texto da decisão fornecido."
)


async def gerar_explicacao(
    db: AsyncSession,
    decisao: dict,
    tese_afetada: dict,
    *,
    user_id: str,
) -> dict:
    """Explicação curta de por que `decisao` pode afetar `tese_afetada`.

    `decisao`: mesmo dict usado pelas Camadas 1/2 (`titulo`, `ementa`, ...).
    `tese_afetada`: um item da saída de
    `radar_jurisprudencial.avaliar_decisao` (`tese_id`, `titulo`, ...).
    `user_id`: ator responsável pela chamada de IA (AILog.user_id é NOT
    NULL) — este módulo não tem ator próprio para varredura totalmente
    autônoma; quem dispara sem usuário autenticado (job agendado) decide se
    chama isto ou deixa o alerta sem explicação (Camadas 1/2 já bastam).

    Retorna `{"texto": str|None, "ai_log_id": str|None}` — nunca levanta.
    """
    if not get_settings().AI_ENABLED:
        return {"texto": None, "ai_log_id": None}

    user_msg = (
        f"TESE: {tese_afetada.get('titulo') or ''}\n\n"
        f"DECISÃO: {(decisao.get('ementa') or '')[:1500]}"
    )
    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": _SYS_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            task_type="resumo", temperature=0.2, max_tokens=200,
            nivel_inteligencia="padrao",
        )
    except Exception as e:
        logger.warning("Camada 3 do radar (IA) indisponível: %s", e)
        return {"texto": None, "ai_log_id": None}

    texto_bruto = (getattr(resp, "texto", "") or "").strip()
    if not texto_bruto:
        return {"texto": None, "ai_log_id": None}

    aplicar_hitl({"texto": texto_bruto})  # carimba rascunho/HITL (efeito é o registro, não o retorno)

    try:
        relatorio = await validar_citacoes(db, texto_bruto)
        citacao_suspeita = relatorio.bloqueia_aprovacao or bool(relatorio.bloqueantes)
    except Exception as e:
        logger.warning("Gate de citações indisponível na Camada 3 do radar: %s", e)
        citacao_suspeita = True  # gate falhou → trata como suspeita, nunca aprova em silêncio

    texto_final = _AVISO_CITACAO_SUSPEITA if citacao_suspeita else texto_bruto

    ai_log_id = str(uuid4())
    modelo = getattr(resp, "modelo", None) or "desconhecido"
    provedor = getattr(resp, "provedor", None)
    db.add(AILog(
        id=ai_log_id, user_id=user_id,
        tipo_uso=AITipoUso.resumo_documento,
        modelo=f"{provedor}/{modelo}" if provedor else modelo,
        prompt_sanitizado=user_msg[:8000],
        pii_removida=False,  # ementa/tese são conteúdo institucional público, não PII de cliente
        resposta=texto_bruto[:8000],
        status_hitl=AIStatusHITL.gerado,
    ))

    return {"texto": texto_final, "ai_log_id": ai_log_id}
