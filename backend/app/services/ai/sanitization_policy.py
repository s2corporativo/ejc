# ── app/services/ai/sanitization_policy.py ───────────────────────────────────
# NÍVEIS DE SANITIZAÇÃO DE PII POR TIPO DE TAREFA (Núcleo Único de IA).
#
# Eleva o mascaramento irreversível legado para uma política graduada por
# tarefa, decidindo COMO o conteúdo é tratado antes de um provider EXTERNO
# (Anthropic/Groq — fora do VPS, art. 33/46 LGPD):
#
#   • LOCAL_COMPLETO         (Modo 1) — sigilo reforçado: só Ollama LOCAL; o
#                            conteúdo NUNCA vai a provider externo (nem
#                            pseudonimizado). Sem local elegível → bloqueia.
#   • EXTERNO_PSEUDONIMIZADO (Modo 2+3) — pseudonimiza (marcadores consistentes
#                            e reversíveis) → externo → REIDRATA a resposta
#                            localmente. Seguro para análise/minuta.
#   • EXTRACAO_LOCAL         (Modo 4) — a PII estruturada é extraída LOCALMENTE
#                            (regex/parser) no ponto de importação; ao gateway,
#                            trata-se como ≥ pseudonimizado (nunca vaza PII).
#   • MASCARAMENTO           (legado/fallback) — mascaramento IRREVERSÍVEL via
#                            sanitizer ([CPF], [EMAIL]…). Comportamento atual.
#
# O mapeamento default é REVISÁVEL POR DR. CLOVIS e OVERRIDÁVEL por configuração
# (Settings.AI_SANITIZATION_MODE_MAP — JSON opcional task_type→modo). Sem
# override, vale o default abaixo.
#
# DECISÃO DE PRODUTO (2026-07-06, dono do escritório): a IA deve funcionar
# PLENAMENTE em todas as áreas usando PSEUDONIMIZAÇÃO REVERSÍVEL (não
# mascaramento irreversível, não bloqueio). Nenhum PII real sai do VPS — o
# provider externo recebe apenas marcadores consistentes e a resposta é
# REIDRATADA localmente. Por isso o default de QUALQUER tarefa não mapeada passa
# a ser EXTERNO_PSEUDONIMIZADO (reversível, seguro), e não mais MASCARAMENTO.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import logging
from enum import Enum

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.sanitization_policy")


class ModoSanitizacao(str, Enum):
    LOCAL_COMPLETO = "local_completo"
    EXTERNO_PSEUDONIMIZADO = "externo_pseudonimizado"
    EXTRACAO_LOCAL = "extracao_local"
    MASCARAMENTO = "mascaramento"


# ── Mapeamento DEFAULT (revisável por Dr. Clovis) ─────────────────────────────
# Chaves em minúsculo; cobre o vocabulário de TarefaIA (system_prompts/router.py)
# E os task_types do ai_gateway (TASK_ROUTING + aliases), pois `chat()` pode
# receber qualquer um dos dois. Comparação é feita sobre o task_type ORIGINAL
# (antes da normalização por aliases do gateway).
_MODO_DEFAULT_POR_TASK: dict[str, ModoSanitizacao] = {
    # `criminal` — EXTERNO_PSEUDONIMIZADO (auditoria de IA 2026-07-17, achado A-1).
    # O risco que antes mantinha esta tarefa em LOCAL_COMPLETO — nomes de vítima/
    # testemunha/terceiro citados SÓ no documento/OCR/RAG (não cadastrados como
    # parte no Case) indo EM CLARO ao provedor externo — JÁ FOI MITIGADO: o
    # pseudonimizador tem uma 3ª passada de NER LOCAL (ai/ner_local.detectar_nomes
    # → [PESSOA_n], issue #102) que pseudonimiza esses nomes ANTES do provider
    # externo, e a 2ª barreira (validar_sem_pii_pseudonimizado →
    # contem_nome_alta_confianca) BLOQUEIA o externo se um nome de ALTA confiança
    # escapar (fail-closed). Só marcadores reversíveis deixam o VPS; a resposta é
    # reidratada localmente. Manter LOCAL_COMPLETO com o Ollama DESLIGADO em
    # produção deixava a IA criminal INDISPONÍVEL (cadeia local vazia → erro).
    # Para sigilo MÁXIMO, o escritório pode REFORÇAR criminal de volta a
    # LOCAL_COMPLETO via AI_SANITIZATION_MODE_MAP (reforço é sempre permitido) e
    # subir o Ollama on-prem (scripts/subir-ia-local.sh).
    "criminal": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    # Modo 2+3 — pseudonimização reversível + reidratação (análise/minuta).
    "analise_caso": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "dossie": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "minutas": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "estrategia": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "pesquisa_juridica": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "trabalhista": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "familia": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "administrativo": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "sucessoes": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "imobiliario": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "constitucional": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "juizados": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "civel": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "ambiental": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "honorarios": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "audiencia": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "prazos": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    # Vocabulário do gateway (TASK_ROUTING) para tarefas complexas equivalentes.
    "analise_juridica": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "elaboracao_peca": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "analise_contrato": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "auditoria_peca": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "jurimetria": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "critica_adversarial": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    # Modo 4 — extração estruturada local (importação/OCR de documento).
    "intake": ModoSanitizacao.EXTRACAO_LOCAL,
    "importacao_documento": ModoSanitizacao.EXTRACAO_LOCAL,
    "extracao_documento": ModoSanitizacao.EXTRACAO_LOCAL,
    "ocr": ModoSanitizacao.EXTRACAO_LOCAL,
    # Tarefas simples/econômicas — antes MASCARAMENTO irreversível. Migradas
    # para EXTERNO_PSEUDONIMIZADO (2026-07-06) para NÃO degradar a qualidade com
    # marcadores irreversíveis ([CPF]/[EMAIL]): agora usam marcadores reversíveis
    # e a resposta é reidratada localmente. A barreira externa continua idêntica.
    "triagem": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "resumo": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "rag_query": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "chat_rapido": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "chat": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
    "default": ModoSanitizacao.EXTERNO_PSEUDONIMIZADO,
}

# Fallback para tarefa desconhecida (2026-07-06): PSEUDONIMIZAÇÃO REVERSÍVEL —
# nunca "sem sanitização". Antes era MASCARAMENTO irreversível; a decisão de
# produto elegeu pseudonimização reversível como piso universal (qualidade sem
# vazar PII: o gateway só envia marcadores ao externo e reidrata a resposta).
_MODO_FALLBACK = ModoSanitizacao.EXTERNO_PSEUDONIMIZADO


def _overrides() -> dict[str, ModoSanitizacao]:
    """Lê Settings.AI_SANITIZATION_MODE_MAP (JSON opcional task_type→modo).
    JSON inválido/valor desconhecido é ignorado com log de aviso (fail-safe:
    cai no default), nunca derruba a chamada de IA."""
    raw = (getattr(get_settings(), "AI_SANITIZATION_MODE_MAP", "") or "").strip()
    if not raw:
        return {}
    try:
        bruto = json.loads(raw)
        if not isinstance(bruto, dict):
            raise ValueError("esperado objeto JSON task_type→modo")
    except Exception as e:  # noqa: BLE001 — override malformado nunca quebra IA
        logger.warning("AI_SANITIZATION_MODE_MAP ignorado (inválido): %s", str(e)[:200])
        return {}
    resultado: dict[str, ModoSanitizacao] = {}
    for task, modo in bruto.items():
        try:
            resultado[str(task).strip().lower()] = ModoSanitizacao(str(modo).strip().lower())
        except ValueError:
            logger.warning(
                "AI_SANITIZATION_MODE_MAP: modo '%s' desconhecido p/ '%s' — ignorado",
                modo, task,
            )
    return resultado


def modo_para_task(task_type: str) -> ModoSanitizacao:
    """Retorna o ModoSanitizacao para `task_type` (default + override de config).

    O override (AI_SANITIZATION_MODE_MAP) tem precedência sobre o default, EXCETO
    pelo PISO DE SEGURANÇA não-rebaixável: se o DEFAULT da tarefa for
    LOCAL_COMPLETO (sigilo reforçado), um override que NÃO seja LOCAL_COMPLETO é
    IGNORADO (com aviso) — o dado não pode ser rebaixado para externo por
    configuração. Reforçar (qualquer tarefa → LOCAL_COMPLETO) é sempre permitido.

    NOTA (2026-07-06): por decisão de produto NENHUMA tarefa tem mais default
    LOCAL_COMPLETO (inclusive `criminal`, agora EXTERNO_PSEUDONIMIZADO). O
    mecanismo do piso permanece intacto e passa a valer quando o escritório
    REFORÇAR uma tarefa para LOCAL_COMPLETO via override — daí ela não pode ser
    rebaixada por outro override. Tarefa não mapeada em nenhum dos dois →
    `_MODO_FALLBACK` (EXTERNO_PSEUDONIMIZADO, reversível e seguro)."""
    task = (task_type or "").strip().lower()
    padrao = _MODO_DEFAULT_POR_TASK.get(task, _MODO_FALLBACK)
    over = _overrides()
    if task in over:
        escolhido = over[task]
        # Piso: LOCAL_COMPLETO por default nunca é rebaixado por override.
        if padrao == ModoSanitizacao.LOCAL_COMPLETO and escolhido != ModoSanitizacao.LOCAL_COMPLETO:
            logger.warning(
                "AI_SANITIZATION_MODE_MAP: override '%s' para '%s' IGNORADO — "
                "tarefa de sigilo reforçado (LOCAL_COMPLETO) não pode ser rebaixada "
                "para provider externo (piso de segurança LGPD).",
                escolhido.value, task,
            )
            return ModoSanitizacao.LOCAL_COMPLETO
        return escolhido
    return padrao
