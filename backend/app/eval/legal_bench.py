from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.services.legal_brain.research_loop import evaluate_research_coverage

# Versão da régua. Alterações na semântica de pontuação exigem bump, para que
# baselines gravados com réguas diferentes não sejam comparados como iguais.
REGUA_VERSION = "legal_bench/2"

_ABSTENTION_STATUSES = frozenset(
    {
        "insuficiente",
        "evidencia_insuficiente",
        "requer_saneamento",
        "sem_conclusao_segura",
    }
)

# Situações possíveis de cada dimensão, por caso/resposta.
#   nao_aplicavel -> a dimensão não é exigida por este caso (fora do denominador)
#   ausente       -> a dimensão é exigida mas a resposta não forneceu insumo
#   avaliado      -> a dimensão foi medida sobre insumo presente
_DIM_NAO_APLICAVEL = "nao_aplicavel"
_DIM_AUSENTE = "ausente"
_DIM_AVALIADO = "avaliado"


def _bool_field(raw: dict[str, Any], key: str, default: bool) -> bool:
    """Aceita somente booleano nativo em contratos de benchmark."""

    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"campo {key} precisa ser booleano")
    return value


@dataclass(frozen=True)
class LegalBenchCase:
    """Caso curado ou sintético usado pelo benchmark determinístico."""

    id: str
    area: str
    prompt: str
    expected_issue_keys: tuple[str, ...] = ()
    expected_source_ids: tuple[str, ...] = ()
    allowed_fact_ids: tuple[str, ...] = ()
    requires_adverse_research: bool = True
    has_missing_evidence: bool = False
    source_scoring_enabled: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LegalBenchCase":
        """Valida os campos mínimos antes de construir um caso de benchmark."""

        case_id = str(raw.get("id") or "").strip()
        prompt = str(raw.get("prompt") or "").strip()
        if not case_id:
            raise ValueError("caso de benchmark precisa de id")
        if not prompt:
            raise ValueError(f"caso {case_id} precisa de prompt")
        return cls(
            id=case_id,
            area=str(raw.get("area") or "nao_definida"),
            prompt=prompt,
            expected_issue_keys=tuple(str(v) for v in raw.get("expected_issue_keys", [])),
            expected_source_ids=tuple(str(v) for v in raw.get("expected_source_ids", [])),
            allowed_fact_ids=tuple(str(v) for v in raw.get("allowed_fact_ids", [])),
            requires_adverse_research=_bool_field(raw, "requires_adverse_research", True),
            has_missing_evidence=_bool_field(raw, "has_missing_evidence", False),
            source_scoring_enabled=_bool_field(raw, "source_scoring_enabled", True),
        )


@dataclass(frozen=True)
class _Dim:
    """Resultado de uma dimensão: valor + situação, sem crédito implícito."""

    value: float | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {"valor": self.value, "situacao": self.status}


_DIM_NA = _Dim(value=None, status=_DIM_NAO_APLICAVEL)


def _measured(value: float, *, has_input: bool) -> _Dim:
    return _Dim(value=value, status=_DIM_AVALIADO if has_input else _DIM_AUSENTE)


@dataclass(frozen=True)
class LegalBenchScore:
    """Métricas determinísticas de um único caso avaliado.

    Cada dimensão carrega valor (``None`` = não aplicável ao caso) e situação.
    O total é a média **somente das dimensões aplicáveis**, de modo que uma
    dimensão desativada ou exigida sem insumo nunca infle a nota.
    """

    case_id: str
    issue_recall: float | None
    source_precision: float | None
    fact_grounding: float | None
    adverse_coverage: float | None
    uncertainty_compliance: float | None
    answer_status: str
    dims: tuple[tuple[str, _Dim], ...]

    def _applicable(self) -> list[float]:
        return [d.value for d in (dim for _, dim in self.dims) if d.value is not None]

    @property
    def total(self) -> float | None:
        """Média das dimensões aplicáveis. ``None`` quando nada é avaliável."""

        values = self._applicable()
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    def to_dict(self) -> dict[str, Any]:
        """Serializa o score para relatório/JSONL de comparação."""

        return {
            "regua": REGUA_VERSION,
            "case_id": self.case_id,
            "issue_recall": self.issue_recall,
            "source_precision": self.source_precision,
            "fact_grounding": self.fact_grounding,
            "adverse_coverage": self.adverse_coverage,
            "uncertainty_compliance": self.uncertainty_compliance,
            "total": self.total,
            "answer_status": self.answer_status,
            "dimensoes": {name: dim.to_dict() for name, dim in self.dims},
        }


def _ratio(expected: set[str], actual: set[str]) -> float:
    """Recall determinístico de um conjunto esperado. Vazio esperado = 0 na
    aplicação, mas o chamador trata 'esperado vazio' como não aplicável."""

    if not expected:
        return 0.0
    return round(len(expected & actual) / len(expected), 4)


def _precision(expected: set[str], actual: set[str]) -> float:
    """Precisão determinística; ausência de insumo = 0 quando há expectativa."""

    if not actual:
        return 0.0
    return round(len(expected & actual) / len(actual), 4)


def score_structured_answer(
    case: LegalBenchCase,
    answer: dict[str, Any],
) -> LegalBenchScore:
    """Pontua saída estruturada sem LLM-as-judge nem autodeclaração de pesquisa.

    Regras de honestidade da régua (v2):
    - Dimensão **não aplicável** (esperativa vazia / desativada) fica fora do
      denominador e nunca recebe crédito.
    - Dimensão aplicável com insumo ausente pontua 0 e é marcada ``ausente``.
    - Resposta vazia recebe 0 nas dimensões aplicáveis; ``abstencao`` só é
      reconhecida quando há ``conclusion_status`` de insuficiencia de fundo.
    - ``adverse_coverage`` é derivado de ``research_records`` rastreáveis; um
      booleano declarado pela resposta não produz pontuação.
    """

    issue_keys = {str(v) for v in answer.get("issue_keys", []) if str(v).strip()}
    source_ids = {str(v) for v in answer.get("source_ids", []) if str(v).strip()}
    fact_ids = {str(v) for v in answer.get("fact_ids", []) if str(v).strip()}
    expected_issues = set(case.expected_issue_keys)
    expected_sources = set(case.expected_source_ids)
    allowed_facts = set(case.allowed_fact_ids)

    research_records = answer.get("research_records") or []
    if not isinstance(research_records, list):
        research_records = []

    conclusion_status = str(answer.get("conclusion_status") or "").strip().lower()
    founded_abstention = conclusion_status in _ABSTENTION_STATUSES
    has_any_input = bool(issue_keys or source_ids or fact_ids or research_records or conclusion_status)

    if not has_any_input:
        answer_status = "vazia"
    elif founded_abstention and not (issue_keys or source_ids or fact_ids):
        answer_status = "abstencao_fundamentada"
    else:
        answer_status = "substantiva"

    # issue_recall: aplicável só se há questões esperadas.
    if expected_issues:
        issue_recall = _measured(_ratio(expected_issues, issue_keys), has_input=bool(issue_keys))
    else:
        issue_recall = _DIM_NA

    # source_precision: aplicável só se scoring habilitado E há fontes esperadas.
    if case.source_scoring_enabled and expected_sources:
        source_precision = _measured(
            _precision(expected_sources, source_ids), has_input=bool(source_ids)
        )
    else:
        source_precision = _DIM_NA

    # fact_grounding: aplicável quando há fatos permitidos a que ancorar OU a
    # resposta cita fatos. Sem insumo e sem gabarito = não aplicável.
    if allowed_facts:
        # Precisão sobre os fatos citados: fração dos fatos da resposta que
        # existem no conjunto permitido. Fato inventado reduz a métrica.
        value = round(len(allowed_facts & fact_ids) / len(fact_ids), 4) if fact_ids else 0.0
        fact_grounding = _measured(value, has_input=bool(fact_ids))
    elif fact_ids:
        fact_grounding = _measured(0.0, has_input=True)
    else:
        fact_grounding = _DIM_NA

    # adverse_coverage: aplicável só quando o caso exige pesquisa adversa.
    if case.requires_adverse_research:
        coverage = evaluate_research_coverage(research_records)
        adverse_coverage = _measured(
            1.0 if coverage.adverse_precedent else 0.0,
            has_input=bool(research_records),
        )
    else:
        adverse_coverage = _DIM_NA

    # uncertainty_compliance: aplicável só quando o caso declara lacuna de
    # evidência. Abstenção fundamentada é o único caminho para o crédito.
    if case.has_missing_evidence:
        uncertainty_compliance = _measured(
            1.0 if founded_abstention else 0.0, has_input=bool(conclusion_status)
        )
    else:
        uncertainty_compliance = _DIM_NA

    dims = (
        ("issue_recall", issue_recall),
        ("source_precision", source_precision),
        ("fact_grounding", fact_grounding),
        ("adverse_coverage", adverse_coverage),
        ("uncertainty_compliance", uncertainty_compliance),
    )

    return LegalBenchScore(
        case_id=case.id,
        issue_recall=issue_recall.value,
        source_precision=source_precision.value,
        fact_grounding=fact_grounding.value,
        adverse_coverage=adverse_coverage.value,
        uncertainty_compliance=uncertainty_compliance.value,
        answer_status=answer_status,
        dims=dims,
    )


def load_cases(path: str | Path) -> list[LegalBenchCase]:
    """Carrega JSONL e rejeita IDs duplicados ou registros inválidos."""

    cases: list[LegalBenchCase] = []
    seen_ids: set[str] = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL inválido na linha {lineno}: {exc}") from exc
            if not isinstance(raw, dict):
                raise ValueError(f"Caso da linha {lineno} precisa ser objeto JSON")
            case = LegalBenchCase.from_dict(raw)
            if case.id in seen_ids:
                raise ValueError(f"id de caso duplicado: {case.id}")
            seen_ids.add(case.id)
            cases.append(case)
    return cases


def summarize(scores: Iterable[LegalBenchScore]) -> dict[str, Any]:
    """Agrega scores por dimensão, publicando denominadores e cobertura.

    Cada média é calculada apenas sobre os casos em que a dimensão é aplicável;
    ``n_aplicavel`` explicita o denominador. ``total_medio`` cobre somente casos
    com ao menos uma dimensão avaliável.
    """

    rows = list(scores)
    if not rows:
        return {"regua": REGUA_VERSION, "n": 0, "total": 0.0, "dimensoes": {}}

    def dim_summary(name: str) -> dict[str, Any]:
        applicable = [dim.value for row in rows for n, dim in row.dims if n == name and dim.value is not None]
        avg = round(sum(applicable) / len(applicable), 4) if applicable else None
        return {"media": avg, "n_aplicavel": len(applicable), "n_total": len(rows)}

    totals = [row.total for row in rows if row.total is not None]
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.answer_status] = by_status.get(row.answer_status, 0) + 1

    return {
        "regua": REGUA_VERSION,
        "n": len(rows),
        "total": round(sum(totals) / len(totals), 4) if totals else None,
        "n_total_avaliado": len(totals),
        "dimensoes": {
            name: dim_summary(name) for name, _ in rows[0].dims
        },
        "answer_status": by_status,
    }
