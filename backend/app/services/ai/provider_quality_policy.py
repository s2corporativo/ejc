from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.provider_quality_policy")
SCHEMA = "ejc-provider-quality/1"


@lru_cache(maxsize=4)
def _load_artifact(path: str, mtime_ns: int) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[adaptive-routing] artefato inválido/indisponível: %s", type(exc).__name__)
        return {}
    return raw if isinstance(raw, dict) else {}


def _artifact() -> dict:
    settings = get_settings()
    path = str(getattr(settings, "AI_ADAPTIVE_ROUTING_ARTIFACT", "") or "").strip()
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        return _load_artifact(str(p), p.stat().st_mtime_ns)
    except OSError:
        return {}


def recommend_provider(
    *,
    area: str | None,
    task_type: str,
    eligible: Iterable[str],
) -> tuple[str | None, str]:
    """Recomenda provider SOMENTE com benchmark humano certificado + holdout.

    Fail-closed: ausência de artefato, corpus insuficiente, falha crítica ou
    provider fora da cadeia elegível devolve None. A recomendação nunca torna
    um provider elegível; a AIProviderPolicy é reaplicada depois.
    """
    settings = get_settings()
    if not bool(getattr(settings, "AI_ADAPTIVE_ROUTING_ENABLED", False)):
        return None, "roteamento adaptativo desligado"

    art = _artifact()
    if art.get("schema") != SCHEMA:
        return None, "artefato de qualidade ausente ou schema incompatível"
    if art.get("certified") is not True or art.get("holdout_evaluated") is not True:
        return None, "benchmark sem certificação humana e holdout"

    area_key = (area or "geral").strip().lower() or "geral"
    task_key = (task_type or "default").strip().lower() or "default"
    areas = art.get("areas") or {}
    bloco = (
        ((areas.get(area_key) or {}).get(task_key))
        or ((areas.get(area_key) or {}).get("default"))
        or ((areas.get("geral") or {}).get(task_key))
        or ((areas.get("geral") or {}).get("default"))
        or {}
    )
    providers = bloco.get("providers") or {}
    min_n = int(getattr(settings, "AI_ADAPTIVE_ROUTING_MIN_CASES", 15) or 15)
    eligible_set = {str(p).lower() for p in eligible}

    candidatos: list[tuple[float, float, str, int]] = []
    for provider, row in providers.items():
        p = str(provider).lower()
        if p not in eligible_set or not isinstance(row, dict):
            continue
        n = int(row.get("n") or 0)
        score = float(row.get("score") or 0.0)
        critical = int(row.get("critical_failures") or 0)
        cost = float(row.get("avg_cost_brl") or 0.0)
        if n < min_n or critical > 0:
            continue
        candidatos.append((score, -cost, p, n))

    if not candidatos:
        return None, "nenhum provider com amostra certificada suficiente e zero falha crítica"

    candidatos.sort(reverse=True)
    score, neg_cost, provider, n = candidatos[0]
    return provider, (
        f"benchmark certificado: provider={provider}, score={score:.3f}, "
        f"n={n}, custo_medio_brl={-neg_cost:.4f}"
    )
