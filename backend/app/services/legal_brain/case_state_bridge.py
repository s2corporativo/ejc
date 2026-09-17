from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from .contracts import EvidenceState
from .evidence import CaseAssertion


@dataclass(frozen=True)
class CaseStateBridgeResult:
    """Visão somente leitura do estado da Sala para o Legal Brain."""

    assertions: tuple[CaseAssertion, ...]
    evidence_gaps: tuple[str, ...]
    ignored_items: int = 0


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.strip().lower().replace("-", "_").replace(" ", "_")


def _text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("texto", "fato", "descricao", "item", "questao"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _explicit_source_ids(item: dict[str, Any]) -> tuple[str, ...]:
    """Coleta somente identificadores explícitos; nunca converte texto em ID."""

    values: list[str] = []
    raw_list = item.get("source_ids")
    if isinstance(raw_list, (list, tuple)):
        values.extend(str(value).strip() for value in raw_list if str(value).strip())
    for key in ("source_id", "doc_id", "documento_id", "chunk_id"):
        value = str(item.get(key) or "").strip()
        if value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _state_for_fact(
    classification: str,
    *,
    origin: str,
    reviewer_user_id: str | None,
    reviewed_at: str | None,
) -> EvidenceState | None:
    """Mapeia classificação da Sala sem permitir promoção automática da IA."""

    label = _norm(classification)
    if label in {"ausente", "faltante", "nao_informado", "nao_comprovado"}:
        return None
    if label in {"alegado", "alegado_cliente"}:
        return EvidenceState.ALEGADO_CLIENTE
    if label in {"alegado_parte_contraria", "parte_contraria"}:
        return EvidenceState.ALEGADO_PARTE_CONTRARIA
    if label in {"controvertido", "controverso"}:
        return EvidenceState.CONTROVERTIDO
    if label in {"inferido", "inferencia", "inferencia_ia"}:
        return EvidenceState.INFERENCIA_IA
    if label in {"superado", "descartado"}:
        return EvidenceState.DESCARTADO

    if label in {"comprovado", "confirmado", "validado_advogado"}:
        # A extração automática da Sala é produzida por IA. Mesmo que o JSON
        # use a palavra "comprovado", isso é apenas uma classificação do modelo
        # até existir um ato humano auditável.
        if _norm(origin) != "manual" or not reviewer_user_id or not reviewed_at:
            return EvidenceState.INFERENCIA_IA
        if label == "validado_advogado":
            return EvidenceState.VALIDADO_ADVOGADO
        return EvidenceState.CONFIRMADO

    # Vocabulário não reconhecido não ganha semântica probatória por aproximação.
    return None


def bridge_legal_chat_state(
    state: dict[str, Any] | None,
    *,
    origin: str = "ai",
    reviewer_user_id: str | None = None,
    reviewed_at: str | None = None,
) -> CaseStateBridgeResult:
    """Transforma o dossiê existente em visão probatória efêmera e fail-closed.

    Não grava nada, não altera ``LegalChatStateVersion`` e não cria uma segunda
    memória de caso. O caller pode informar ``origin='manual'`` + identidade e
    data apenas quando a versão decorre de uma edição humana auditável.
    """

    payload = state if isinstance(state, dict) else {}
    assertions: list[CaseAssertion] = []
    gaps: list[str] = []
    ignored = 0

    facts = payload.get("fatos")
    if not isinstance(facts, list):
        facts = []

    for index, raw in enumerate(facts, start=1):
        if not isinstance(raw, dict):
            ignored += 1
            continue
        text = _text(raw)
        if not text:
            ignored += 1
            continue
        classification = str(raw.get("classificacao") or "").strip()
        normalized = _norm(classification)
        if normalized in {"ausente", "faltante", "nao_informado", "nao_comprovado"}:
            gaps.append(text)
            continue

        evidence_state = _state_for_fact(
            classification,
            origin=origin,
            reviewer_user_id=reviewer_user_id,
            reviewed_at=reviewed_at,
        )
        if evidence_state is None:
            ignored += 1
            continue

        fact_id = str(raw.get("id") or raw.get("fato_id") or f"state-fact-{index}").strip()
        kwargs: dict[str, Any] = {}
        if evidence_state in {EvidenceState.CONFIRMADO, EvidenceState.VALIDADO_ADVOGADO}:
            kwargs = {
                "validated_by_user_id": reviewer_user_id,
                "validated_at": reviewed_at,
            }
        assertions.append(
            CaseAssertion(
                id=fact_id,
                text=text,
                state=evidence_state,
                source_ids=_explicit_source_ids(raw),
                **kwargs,
            )
        )

    pending = payload.get("pendencias")
    if isinstance(pending, list):
        for item in pending:
            text = _text(item)
            if text:
                gaps.append(text)
            else:
                ignored += 1

    return CaseStateBridgeResult(
        assertions=tuple(assertions),
        evidence_gaps=tuple(dict.fromkeys(gaps)),
        ignored_items=ignored,
    )
