from __future__ import annotations

from typing import Any

from .contracts import FactualFitReview, ResearchPlan
from .research_loop import (
    evaluate_research_coverage,
    evaluate_research_coverage_by_issue,
    next_research_gap,
)


# "saneamento_fatico" é o purpose emitido por build_clarification_plan;
# "clarificar_fatos" é mantido por compatibilidade com planos já serializados.
_CLARIFICATION_PURPOSES = frozenset({"saneamento_fatico", "clarificar_fatos"})


def _record_from_rag(
    item: dict[str, Any], *, purpose: str, issue_key: str | None = None
) -> dict[str, Any] | None:
    """Converte um resultado do RAG em evidência rastreável, sem promover mérito.

    O adaptador conserva IDs e metadados canônicos, mas NÃO infere aderência
    fática nem posição favorável/adversa a partir do texto ou da query.
    """
    if not isinstance(item, dict):
        return None
    doc_id = str(item.get("doc_id") or "").strip()
    chunk_id = str(item.get("chunk_id") or "").strip()
    fonte = str(item.get("fonte") or "").strip()
    if not doc_id and not chunk_id and not fonte:
        return None

    # Import tardio: importar legal_brain não deve inicializar ai_service/RAG.
    from app.services.knowledge_governance import inferir_autoridade

    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    authority = inferir_autoridade(
        item.get("categoria"),
        fonte or None,
        extra,
    )
    authority_code = str(authority.get("code") or "referencial")
    source_class = {
        "oficial_normativa": "legislacao_oficial",
        "precedente_vinculante": "precedente_vinculante",
        "jurisprudencia_oficial": "jurisprudencia_oficial",
        "institucional_interna": "memoria_institucional_aprovada",
        "doutrinaria": "doutrina_curada",
    }.get(authority_code, authority_code)

    # Vigência só é promovida quando o próprio metadado canônico comprova:
    # norma vigente + origem + data de verificação + ausência de inferência.
    situacao = item.get("situacao_juridica") if isinstance(item.get("situacao_juridica"), dict) else {}
    validity_verified = bool(
        authority_code == "oficial_normativa"
        and situacao.get("code") == "vigente"
        and str(extra.get("legal_status_origem") or "").strip()
        and str(extra.get("legal_status_verificado_em") or "").strip()
        and not str(extra.get("legal_status_inferido_em") or "").strip()
    )

    return {
        "source_id": doc_id or chunk_id or fonte,
        "chunk_id": chunk_id or None,
        "citation": str(item.get("titulo") or "").strip() or None,
        "source_url": fonte or None,
        "source_class": source_class,
        "authority_level": authority_code,
        "research_purpose": purpose,
        "issue_key": issue_key,
        "validity_verified": validity_verified,
        # Não inferir estes dois campos. Só curadoria posterior pode promovê-los.
        "stance": None,
        "factual_fit_reviewed": False,
        "legal_status": situacao.get("code"),
        "confidence": item.get("confianca"),
        "version": item.get("versao"),
        "title": item.get("titulo"),
        "content": item.get("conteudo"),
    }


def apply_factual_fit_review(
    record: dict[str, Any], review: FactualFitReview
) -> dict[str, Any]:
    """Registra revisão humana de aderência fática em uma evidência (função pura).

    Retorna uma CÓPIA; nunca muta o registro nem é chamada pelo adaptador.
    Fail-closed: registro sem proveniência, ou cuja origem/questão não bate com
    a revisão, levanta ``ValueError``. A posição só muda se a revisão a informar.
    """

    if not isinstance(record, dict) or not isinstance(review, FactualFitReview):
        raise ValueError("registro e revisão válidos são obrigatórios")
    source_id = str(record.get("source_id") or "").strip()
    if not source_id or source_id != review.source_id.strip():
        raise ValueError("revisão não corresponde à fonte do registro")
    record_issue = str(record.get("issue_key") or "").strip()
    if not record_issue or record_issue != review.issue_key.strip():
        raise ValueError("revisão não corresponde à questão do registro")
    updated = dict(record)
    updated["factual_fit_reviewed"] = True
    updated["factual_fit"] = review.fits
    updated["factual_fit_reviewed_by"] = review.reviewed_by_user_id.strip()
    updated["factual_fit_reviewed_at"] = review.reviewed_at.strip()
    if review.stance is not None:
        updated["stance"] = review.stance
    return updated


async def execute_research_plan_with_rag(
    db,
    plan: ResearchPlan,
    *,
    limit_per_step: int = 6,
    scope_client_id: str | None = None,
    scope_case_id: str | None = None,
) -> dict[str, Any]:
    """Executa um ``ResearchPlan`` somente contra o retrieval canônico do EJC.

    Ownership e governança permanecem em ``buscar_contexto_rag``. O passo de
    validade pode consultar versões históricas, mas isso nunca as promove a
    autoridade atual. Planos apenas de saneamento não consultam RAG nem abrem
    automaticamente uma lacuna de pesquisa jurídica.
    """
    # Import tardio: mantém o pacote Legal Brain leve e evita ciclos de startup.
    from app.services.ai_service import buscar_contexto_rag

    records: list[dict[str, Any]] = []
    executed_steps: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    clarification_only = bool(plan.steps) and all(
        step.purpose in _CLARIFICATION_PURPOSES for step in plan.steps
    )

    # ``plan.max_cycles`` limita as rodadas. A 1ª executa todos os passos; as
    # seguintes repetem só os passos que não recuperaram nada, enquanto houver
    # lacuna aberta e progresso (registro novo). Passos que já recuperaram
    # material não são repetidos: repetir a mesma consulta não fecha lacuna de
    # posição/aderência, que só a revisão humana promove.
    max_cycles = max(1, int(plan.max_cycles))
    pending = list(plan.steps)
    for cycle in range(1, max_cycles + 1):
        if not pending:
            break
        retry: list = []
        progressed = False
        for step in pending:
            if step.purpose in _CLARIFICATION_PURPOSES:
                executed_steps.append(
                    {"purpose": step.purpose, "query": step.query, "retrieved": 0, "skipped": True}
                )
                continue

            raw_items = await buscar_contexto_rag(
                db,
                step.query,
                limite=max(1, int(limit_per_step)),
                scope_client_id=scope_client_id,
                scope_case_id=scope_case_id,
                incluir_historico=step.purpose == "validade_temporal",
                incluir_ficticio=False,
            )
            count = 0
            for raw in raw_items or []:
                record = _record_from_rag(raw, purpose=step.purpose, issue_key=plan.issue_key)
                if record is None:
                    continue
                key = (
                    step.purpose,
                    str(record.get("source_id") or ""),
                    str(record.get("chunk_id") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
                count += 1
            executed_steps.append(
                {
                    "purpose": step.purpose,
                    "query": step.query,
                    "retrieved": count,
                    "skipped": False,
                    "cycle": cycle,
                }
            )
            if count:
                progressed = True
            else:
                retry.append(step)
        if not progressed or evaluate_research_coverage(records).complete:
            break
        pending = retry

    coverage = evaluate_research_coverage(records)
    return {
        "issue_key": plan.issue_key,
        "area": plan.area,
        "records": records,
        "coverage": {
            "primary_source": coverage.primary_source,
            "current_validity": coverage.current_validity,
            "supporting_precedent": coverage.supporting_precedent,
            "adverse_precedent": coverage.adverse_precedent,
            "factual_fit": coverage.factual_fit,
            "complete": coverage.complete,
        },
        "coverage_by_issue": {
            key: {
                "primary_source": cov.primary_source,
                "current_validity": cov.current_validity,
                "supporting_precedent": cov.supporting_precedent,
                "adverse_precedent": cov.adverse_precedent,
                "factual_fit": cov.factual_fit,
                "complete": cov.complete,
            }
            for key, cov in evaluate_research_coverage_by_issue(
                records, issue_keys=(plan.issue_key,)
            ).items()
        },
        "next_gap": "clarificar_fatos" if clarification_only else next_research_gap(coverage),
        "executed_steps": executed_steps,
        "requires_human_review": True,
    }
