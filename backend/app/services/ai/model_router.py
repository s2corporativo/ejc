# ── app/services/ai/model_router.py ──────────────────────────────────────────
# Roteamento inteligente por COMPLEXIDADE e CUSTO (Fase 6).
#
# O roteador é DETERMINÍSTICO (nenhuma chamada de IA): estima a complexidade do
# input por sinais baratos (tamanho, perfil do task_type, contexto de caso, nº
# de citações) e mapeia score → tier (leve|medio|pesado) → provedor de PARTIDA.
#
# O roteador apenas PROPÕE. O ai_gateway ainda aplica elegibilidade por provedor
# (kill-switch de soberania, chave, ENABLED), a barreira PII e o fallback. Se o
# provedor proposto for inelegível, o gateway o ignora e usa a cadeia normal.
#
# Desligado por padrão (ROTEAMENTO_INTELIGENTE_ENABLED=false) → o gateway usa a
# lógica atual por task_type intacta.
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings

# Perfil de peso por task_type (vocabulário do TASK_ROUTING + aliases já
# normalizados no gateway). Tarefas de raciocínio jurídico profundo pesam mais.
_PESO_TASK: dict[str, int] = {
    # leves
    "resumo": 0,
    "chat_rapido": 0,
    "triagem": 0,
    # médias
    "analise_contrato": 3,
    "auditoria_peca": 3,
    "jurimetria": 3,
    # pesadas
    "analise_juridica": 5,
    "elaboracao_peca": 5,
    "estrategia": 6,
    "critica_adversarial": 6,
}

# Detecção barata de citações jurídicas (nº CNJ, artigos, súmulas, REsp/RE/HC).
_RX_CITACAO = re.compile(
    r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"      # nº CNJ
    r"|art\.?\s*\d+"                                  # artigo
    r"|s[úu]mula\s*\d+"                               # súmula
    r"|(?:REsp|RE|HC|AgRg|AREsp|ADI|ADPF)\s*\d+)",   # recursos/ações
    re.IGNORECASE,
)


@dataclass
class DecisaoRoteamento:
    tier: str                 # "leve" | "medio" | "pesado"
    provider: str             # provedor de PARTIDA proposto
    model: str | None         # modelo sugerido (None = default do provedor)
    score: int                # score de complexidade (determinístico)
    motivo: str               # explicação legível do roteamento


def _tamanho(texto_entrada: str | None, tamanho_override: int | None) -> int:
    if tamanho_override is not None:
        return max(0, int(tamanho_override))
    return len(texto_entrada or "")


def calcular_score(
    task_type: str,
    texto_entrada: str | None = None,
    contexto: dict | None = None,
    tamanho_override: int | None = None,
) -> tuple[int, list[str]]:
    """Score de complexidade determinístico + motivos. SEM IA."""
    motivos: list[str] = []
    score = 0

    peso_task = _PESO_TASK.get((task_type or "").strip().lower(), 4)
    score += peso_task
    motivos.append(f"task_type '{task_type}' (+{peso_task})")

    n = _tamanho(texto_entrada, tamanho_override)
    if n >= 8000:
        score += 3
        motivos.append("input muito grande >=8000 chars (+3)")
    elif n >= 3000:
        score += 2
        motivos.append("input grande >=3000 chars (+2)")
    elif n >= 800:
        score += 1
        motivos.append("input médio >=800 chars (+1)")

    ctx = contexto or {}
    if ctx.get("case_id") or ctx.get("contexto_rag") or ctx.get("tem_contexto_caso"):
        score += 1
        motivos.append("contexto de caso presente (+1)")

    n_cit = 0
    if texto_entrada:
        n_cit = len(_RX_CITACAO.findall(texto_entrada))
    if n_cit >= 5:
        score += 2
        motivos.append(f"muitas citações ({n_cit}) (+2)")
    elif n_cit >= 1:
        score += 1
        motivos.append(f"citações jurídicas ({n_cit}) (+1)")

    return score, motivos


def _tier_do_score(score: int) -> str:
    s = get_settings()
    if score >= s.ROTEAMENTO_LIMIAR_PESADO:
        return "pesado"
    if score >= s.ROTEAMENTO_LIMIAR_MEDIO:
        return "medio"
    return "leve"


def _provider_do_tier(tier: str) -> str:
    s = get_settings()
    return {
        "leve": s.ROTEAMENTO_PROVIDER_LEVE,
        "medio": s.ROTEAMENTO_PROVIDER_MEDIO,
        "pesado": s.ROTEAMENTO_PROVIDER_PESADO,
    }.get(tier, s.ROTEAMENTO_PROVIDER_MEDIO)


def _model_do_provider(provider: str, tier: str) -> str | None:
    """Modelo sugerido. Só Anthropic diferencia por tier (RAPIDO vs COMPLEXO);
    ollama/groq resolvem o modelo default por tarefa no próprio gateway."""
    s = get_settings()
    if provider == "anthropic":
        return s.ANTHROPIC_MODEL_COMPLEXO if tier == "pesado" else s.ANTHROPIC_MODEL_RAPIDO
    return None


def escolher_modelo(
    task_type: str,
    texto_entrada: str | None = None,
    contexto: dict | None = None,
    tamanho_override: int | None = None,
) -> DecisaoRoteamento:
    """Decide provider+modelo de PARTIDA por complexidade/custo. Determinístico.
    O gateway ainda valida elegibilidade/PII e faz fallback."""
    score, motivos = calcular_score(task_type, texto_entrada, contexto, tamanho_override)
    tier = _tier_do_score(score)
    provider = _provider_do_tier(tier)
    model = _model_do_provider(provider, tier)
    return DecisaoRoteamento(
        tier=tier,
        provider=provider,
        model=model,
        score=score,
        motivo=f"tier={tier} (score={score}): " + "; ".join(motivos),
    )
