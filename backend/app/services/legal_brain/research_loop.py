from __future__ import annotations

from collections.abc import Iterable

from .contracts import LegalIssue, ResearchCoverage, ResearchPlan, ResearchStep


_SOURCE_CLASS_PRIORITY: tuple[str, ...] = (
    "legislacao_oficial",
    "precedente_vinculante",
    "jurisprudencia_oficial",
    "ato_administrativo_oficial",
    "doutrina_curada",
    "memoria_institucional_aprovada",
)


def build_research_plan(issue: LegalIssue, *, max_cycles: int = 3) -> ResearchPlan:
    """Gera um plano de pesquisa sem executar rede, RAG ou modelo.

    O plano obriga fonte primária, validade temporal e pesquisa adversa. Isso
    evita o padrão de recuperar apenas material que confirma a hipótese inicial.
    """

    cycles = min(5, max(1, int(max_cycles)))
    base = f"{issue.title}: {issue.question}"
    area = issue.area or "nao_definida"
    return ResearchPlan(
        issue_key=issue.key,
        area=area,
        max_cycles=cycles,
        steps=(
            ResearchStep(
                order=1,
                purpose="fonte_primaria",
                query=f"{base} norma vigente fonte oficial",
                source_classes=("legislacao_oficial", "ato_administrativo_oficial"),
            ),
            ResearchStep(
                order=2,
                purpose="precedente_favoravel",
                query=f"{base} precedente jurisprudencia oficial tese favoravel",
                source_classes=("precedente_vinculante", "jurisprudencia_oficial"),
            ),
            ResearchStep(
                order=3,
                purpose="precedente_adverso",
                query=f"{base} entendimento contrario distinção limitação superação",
                source_classes=("precedente_vinculante", "jurisprudencia_oficial"),
            ),
            ResearchStep(
                order=4,
                purpose="validade_temporal",
                query=f"{base} vigencia revogacao alteração legislativa tema sumula",
                source_classes=("legislacao_oficial", "precedente_vinculante"),
            ),
            ResearchStep(
                order=5,
                purpose="aderencia_fatica",
                query=f"{base} requisitos fatos prova distinção",
                source_classes=_SOURCE_CLASS_PRIORITY,
            ),
        ),
        stop_when=(
            "fonte primária identificada",
            "vigência/validade temporal verificada",
            "precedente favorável relevante identificado",
            "entendimento adverso relevante pesquisado",
            "aderência fática/probatória avaliada",
        ),
    )


def build_clarification_plan(issue: LegalIssue) -> ResearchPlan:
    """Cria plano de saneamento sem disparar pesquisa jurídica prematura.

    ``saneamento_inicial`` existe justamente quando ainda não há questão jurídica
    suficientemente delimitada. Nesse estado, pesquisar precedentes favoráveis ou
    adversos criaria ruído e falsa aparência de enquadramento.
    """

    return ResearchPlan(
        issue_key=issue.key,
        area=issue.area or "nao_definida",
        max_cycles=1,
        steps=(
            ResearchStep(
                order=1,
                purpose="saneamento_fatico",
                query=issue.question,
                source_classes=(),
                mandatory=True,
            ),
        ),
        stop_when=("partes, fatos, documentos, datas, valores, objetivo e fase confirmados",),
    )


def _provenance_id(raw: dict) -> str:
    """Retorna uma âncora rastreável sem inferir proveniência ausente."""

    for key in ("source_id", "canonical_id", "doc_id", "url", "citation"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def evaluate_research_coverage(records: Iterable[dict]) -> ResearchCoverage:
    """Mede cobertura somente a partir de evidência explícita e rastreável.

    Uma classe declarada sem ``source_id``/``canonical_id``/``doc_id``/URL/citação
    não satisfaz nenhum requisito. Flags de validação precisam ser booleanos
    nativos ``True``; strings como ``"false"`` nunca contam como verificação.
    """

    primary_source = False
    current_validity = False
    supporting_precedent = False
    adverse_precedent = False
    factual_fit = False

    for raw in records:
        if not isinstance(raw, dict):
            continue
        provenance = _provenance_id(raw)
        if not provenance:
            continue
        source_class = str(raw.get("source_class") or "").strip().lower()
        stance = str(raw.get("stance") or "").strip().lower()
        if source_class in {"legislacao_oficial", "ato_administrativo_oficial"}:
            primary_source = True
        if raw.get("validity_verified") is True:
            current_validity = True
        if source_class in {"precedente_vinculante", "jurisprudencia_oficial"}:
            if stance in {"favoravel", "supporting", "apoio"}:
                supporting_precedent = True
            if stance in {"contrario", "adverso", "adverse"}:
                adverse_precedent = True
        if raw.get("factual_fit_reviewed") is True:
            factual_fit = True

    return ResearchCoverage(
        primary_source=primary_source,
        current_validity=current_validity,
        supporting_precedent=supporting_precedent,
        adverse_precedent=adverse_precedent,
        factual_fit=factual_fit,
    )


def next_research_gap(coverage: ResearchCoverage) -> str | None:
    """Retorna a próxima lacuna, em ordem jurídica de segurança."""

    checks = (
        (coverage.primary_source, "fonte_primaria"),
        (coverage.current_validity, "validade_temporal"),
        (coverage.supporting_precedent, "precedente_favoravel"),
        (coverage.adverse_precedent, "precedente_adverso"),
        (coverage.factual_fit, "aderencia_fatica"),
    )
    for satisfied, gap in checks:
        if not satisfied:
            return gap
    return None
