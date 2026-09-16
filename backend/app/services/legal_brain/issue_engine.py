from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .contracts import LegalIssue


@dataclass(frozen=True)
class _IssueRule:
    """Regra lexical auditável para uma questão jurídica candidata."""

    key: str
    title: str
    areas: tuple[str, ...]
    keywords: tuple[str, ...]
    question: str
    required_questions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    risks: tuple[str, ...]
    transversal: bool = False
    stems: tuple[str, ...] = ()


def _norm(value: str | None) -> str:
    """Normaliza texto sem acentos e separadores para matching reproduzível."""

    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()


def _matches_keyword(text: str, keyword: str) -> bool:
    """Casa termo/palavra completa, nunca substring incidental."""

    token = _norm(keyword)
    if not token:
        return False
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text) is not None


def _matches_stem(text: str, stem: str) -> bool:
    """Casa apenas prefixos intencionalmente declarados no início da palavra."""

    token = _norm(stem)
    if not token:
        return False
    return re.search(rf"(?<!\w){re.escape(token)}\w*", text) is not None


_RULES: tuple[_IssueRule, ...] = (
    _IssueRule(
        key="relacao_consumo_responsabilidade",
        title="Relação de consumo e regime de responsabilidade",
        areas=("consumidor", "civil"),
        keywords=("consumidor", "fornecedor", "produto", "servico", "cdc", "vicio", "defeito"),
        question="Há relação de consumo e qual é o regime jurídico de responsabilidade aplicável aos fatos comprovados?",
        required_questions=(
            "Quem forneceu o produto ou serviço?",
            "Qual foi a oferta, contratação ou aquisição?",
            "O problema é vício, fato do produto/serviço, cobrança ou prática comercial?",
        ),
        required_evidence=(
            "contrato/oferta",
            "comprovante de pagamento",
            "protocolos",
            "documentos do evento danoso",
        ),
        risks=(
            "qualificação jurídica prematura",
            "confusão entre vício e fato",
            "dano não demonstrado",
        ),
    ),
    _IssueRule(
        key="bancario_contrato_encargos",
        title="Contrato bancário, encargos e evolução do débito",
        areas=("bancario", "consumidor", "civil"),
        keywords=("banco", "emprestimo", "financiamento", "cartao", "cet", "juros", "tarifa", "parcela"),
        question="Os encargos, tarifas, seguros, amortização e evolução do débito correspondem ao contrato e às séries oficiais comparáveis?",
        required_questions=(
            "Qual é o produto financeiro e o período contratado?",
            "Há contrato integral, CET e demonstrativo de evolução?",
            "Quais pagamentos, renegociações, mora e garantias ocorreram?",
        ),
        required_evidence=(
            "contrato integral",
            "CET",
            "extratos",
            "demonstrativo de evolução",
            "comprovantes de pagamento",
        ),
        risks=(
            "comparar taxas não equivalentes",
            "cálculo por LLM",
            "omitir renegociação ou seguro",
        ),
    ),
    _IssueRule(
        key="tutela_urgencia",
        title="Tutela provisória de urgência",
        areas=(),
        keywords=("urgencia", "liminar", "tutela", "suspender", "bloqueio", "protesto"),
        stems=("imediat", "negativ"),
        transversal=True,
        question="Os documentos disponíveis demonstram probabilidade do direito, perigo de dano/risco ao resultado útil e adequação da medida requerida?",
        required_questions=(
            "Qual dano concreto ocorre se a medida não for concedida agora?",
            "Qual documento sustenta a probabilidade do direito?",
            "A medida é reversível e proporcional?",
        ),
        required_evidence=(
            "prova do fato principal",
            "prova da urgência",
            "cronologia",
            "documento do ato impugnado",
        ),
        risks=(
            "urgência apenas retórica",
            "pedido irreversível",
            "ausência de prova contemporânea",
        ),
    ),
    _IssueRule(
        key="competencia_rito",
        title="Competência, procedimento e rito",
        areas=(),
        keywords=("competencia", "foro", "juizado", "jec", "vara", "rito", "procedimento", "tribunal"),
        transversal=True,
        question="Qual órgão é competente e qual rito se aplica, considerados partes, matéria, valor, território e fase?",
        required_questions=(
            "Quem são as partes e qual sua natureza jurídica?",
            "Qual o valor e o objeto da pretensão?",
            "Há regra especial de competência territorial ou material?",
        ),
        required_evidence=(
            "qualificação das partes",
            "valor da pretensão",
            "domicílio/local do fato",
            "ato ou contrato relevante",
        ),
        risks=(
            "competência presumida",
            "JEC usado fora dos limites",
            "regra especial ignorada",
        ),
    ),
    _IssueRule(
        key="prescricao_decadencia",
        title="Prescrição e decadência",
        areas=(),
        keywords=("prescricao", "decadencia", "prazo", "ciencia", "vencimento", "constituicao", "ajuizamento"),
        transversal=True,
        question="Há dados suficientes para identificar o prazo aplicável e seus marcos inicial, interruptivos, suspensivos ou impeditivos?",
        required_questions=(
            "Qual é a natureza material ou processual do prazo?",
            "Qual evento jurídico inicia a contagem?",
            "Há suspensão, interrupção, impedimento, transição legislativa ou modulação?",
        ),
        required_evidence=(
            "datas documentadas",
            "ciência/notificação",
            "atos interruptivos/suspensivos",
            "fonte normativa vigente",
        ),
        risks=(
            "calcular sem marco jurídico",
            "transportar regra entre regimes",
            "confundir prescrição com decadência",
        ),
    ),
    _IssueRule(
        key="prova_onus_lacunas",
        title="Prova, ônus e lacunas probatórias",
        areas=(),
        keywords=("prova", "documento", "testemunha", "pericia", "onus", "comprovar", "evidencia", "laudo"),
        transversal=True,
        question="Quais fatos relevantes estão comprovados, controvertidos ou sem suporte e quem suporta o ônus correspondente?",
        required_questions=(
            "Qual fato precisa ser provado para cada pedido ou defesa?",
            "Qual prova existe e qual está ausente?",
            "É necessária prova pericial, testemunhal, técnica ou requisição a terceiro?",
        ),
        required_evidence=(
            "matriz fato-prova",
            "documentos existentes",
            "lista de lacunas",
            "cronologia",
        ),
        risks=(
            "tratar alegação como fato",
            "mencionar documento inexistente",
            "não antecipar prova adversa",
        ),
    ),
)


def identify_legal_issues(
    text: str,
    *,
    area: str | None = None,
    limit: int = 8,
) -> tuple[LegalIssue, ...]:
    """Identifica questões candidatas sem decidir mérito ou inferir fatos.

    Regras transversais continuam elegíveis em qualquer área canônica. Regras de
    ramo só são consideradas quando compatíveis com a área informada.
    """

    normalized = _norm(text)
    normalized_area = _norm(area).replace(" ", "_") if area else ""
    found: list[LegalIssue] = []

    for rule in _RULES:
        if normalized_area and not rule.transversal and normalized_area not in rule.areas:
            continue
        matched_keywords = tuple(
            keyword for keyword in rule.keywords if _matches_keyword(normalized, keyword)
        )
        matched_stems = tuple(
            stem for stem in rule.stems if _matches_stem(normalized, stem)
        )
        matched = matched_keywords + matched_stems
        if not matched:
            continue
        found.append(
            LegalIssue(
                key=rule.key,
                title=rule.title,
                area=normalized_area or (rule.areas[0] if rule.areas else "transversal"),
                question=rule.question,
                matched_terms=matched,
                required_questions=rule.required_questions,
                required_evidence=rule.required_evidence,
                risks=rule.risks,
            )
        )
        if len(found) >= max(1, limit):
            break

    if found:
        return tuple(found)

    return (
        LegalIssue(
            key="saneamento_inicial",
            title="Saneamento jurídico inicial",
            area=normalized_area or "nao_definida",
            question="Quais fatos, documentos, partes, datas, valores, objetivo e fase precisam ser confirmados antes de formular a questão jurídica?",
            required_questions=(
                "Quem são as partes e qual é o objetivo jurídico?",
                "Quais fatos são documentados e quais são apenas alegados?",
                "Quais datas, valores e atos oficiais são relevantes?",
            ),
            required_evidence=(
                "documentos essenciais",
                "cronologia",
                "identificação das partes",
            ),
            risks=("conclusão sem enquadramento suficiente",),
        ),
    )
