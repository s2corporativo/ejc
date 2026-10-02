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
    # Expressões multi-termo (posse/ausência/qualidade de prova) casadas sobre o
    # texto normalizado como sequência, para reconhecer linguagem probatória
    # que não aparece como substantivo isolado (ex.: "não possui contrato").
    phrases: tuple[str, ...] = ()


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


_CLAUSE_BREAK = re.compile(r"[.;:,!?()\[\]\n]")
_NEGATORS = frozenset({"nao", "sem", "nunca", "jamais", "nem", "nenhum", "nenhuma"})
_CONTRAST = frozenset({"mas", "porem", "contudo", "todavia", "entretanto"})
_NEGATION_WINDOW = 3

# Questão de outra área só entra com indício mais forte que um termo isolado.
_MIN_SCORE = 1
_MIN_SCORE_OUT_OF_AREA = 2


def _is_negated(text: str, start: int) -> bool:
    """Negação simples: negador até 3 palavras antes do termo, na mesma oração.

    Vírgula/ponto/dois-pontos e conjunções adversativas encerram o alcance.
    """

    segment = _CLAUSE_BREAK.split(text[:start])[-1]
    window = segment.split()[-_NEGATION_WINDOW:]
    for idx in range(len(window) - 1, -1, -1):
        if window[idx] in _CONTRAST:
            window = window[idx + 1 :]
            break
    return any(word in _NEGATORS for word in window)


def _split_negated(
    text: str, pattern: str, terms: tuple[str, ...]
) -> tuple[list[str], list[str]]:
    """Separa termos com ocorrência afirmada dos que só aparecem sob negação."""

    affirmed: list[str] = []
    negated: list[str] = []
    for term in terms:
        token = _norm(term)
        if not token:
            continue
        hits = list(re.finditer(pattern.format(re.escape(token)), text))
        if not hits:
            continue
        if any(not _is_negated(text, hit.start()) for hit in hits):
            affirmed.append(term)
        else:
            negated.append(term)
    return affirmed, negated


def _confidence(score: int, *, out_of_area: bool) -> float:
    """Confiança lexical determinística: 1 - 0.6**score (0.40, 0.64, 0.78...)."""

    if score <= 0:
        return 0.0
    value = 1.0 - 0.6**score
    if out_of_area:
        value *= 0.5
    return round(value, 2)


def _matches_phrase(text: str, phrase: str) -> bool:
    """Casa uma expressão multi-termo como sequência de palavras inteiras."""

    token = _norm(phrase)
    if not token:
        return False
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text) is not None


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
        # Expressões probatórias: posse, ausência e limitação de documento.
        # Reconhecem a linguagem em que o caso descreve o que tem e o que não
        # tem, que é exatamente a questão de ônus e lacunas. Substantivos
        # isolados (prova, documento, laudo) já são cobertos por keywords.
        phrases=(
            "possui contrato",
            "possui documento",
            "possui documentos",
            "possui extrato",
            "possui extratos",
            "possui protocolo",
            "possui comprovante",
            "possui comprovantes",
            "possui apolice",
            "possui memorial",
            "nao possui contrato",
            "nao possui documento",
            "nao possui documentos",
            "nao possui extrato",
            "nao possui extratos",
            "nao possui protocolo",
            "nao possui comprovante",
            "nao possui apolice",
            "nao ha contrato",
            "nao ha documento",
            "nao ha documentos",
            "nao ha extrato",
            "nao ha protocolo",
            "nao ha comprovante",
            "sem contrato",
            "sem documento",
            "sem documentos",
            "sem extrato",
            "sem protocolo",
            "sem comprovante",
            "nao apresentou contrato",
            "nao apresentou documento",
            "nao apresentou documentos",
            "nao apresentou prova",
            "nao anexou",
            "nao juntou",
            "faltam documentos",
            "faltam provas",
            "memoria de amortizacao",
            "documento que",
            "documentos que",
            "comprovante de",
            "comprovantes de",
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
    ramo compatíveis com a área informada entram com indício mínimo; regras de
    outra área (área mista) só entram com indício mais forte e confiança
    reduzida, sem descartar a questão de maior pontuação. Termos sob negação
    simples ("não houve", "sem", "nunca") não contam como indício e ficam em
    ``negated_terms``. Sem indício suficiente, cai em ``saneamento_inicial``
    (fail-safe: pedir esclarecimento, nunca afirmar enquadramento).
    """

    normalized = _norm(text)
    normalized_area = _norm(area).replace(" ", "_") if area else ""
    candidates: list[tuple[int, int, LegalIssue]] = []
    all_negated: list[str] = []

    for order, rule in enumerate(_RULES):
        out_of_area = bool(
            normalized_area and not rule.transversal and normalized_area not in rule.areas
        )
        kw, kw_neg = _split_negated(normalized, r"(?<!\w){}(?!\w)", rule.keywords)
        st, st_neg = _split_negated(normalized, r"(?<!\w){}\w*", rule.stems)
        # Frases já carregam a própria polaridade ("não possui contrato" é
        # indício de lacuna) e, na regra de prova, a negação do substantivo
        # ("sem prova") é justamente a lacuna: negação não se aplica a elas.
        ph = tuple(p for p in rule.phrases if _matches_phrase(normalized, p))
        if rule.key == "prova_onus_lacunas":
            kw, kw_neg = kw + kw_neg, []
            st, st_neg = st + st_neg, []
        matched = tuple(kw) + tuple(st) + ph
        negated = tuple(kw_neg) + tuple(st_neg)
        all_negated.extend(negated)
        score = len(matched)
        if score < (_MIN_SCORE_OUT_OF_AREA if out_of_area else _MIN_SCORE):
            continue
        candidates.append(
            (
                score,
                order,
                LegalIssue(
                    key=rule.key,
                    title=rule.title,
                    area=(
                        rule.areas[0]
                        if out_of_area
                        else normalized_area or (rule.areas[0] if rule.areas else "transversal")
                    ),
                    question=rule.question,
                    matched_terms=matched,
                    required_questions=rule.required_questions,
                    required_evidence=rule.required_evidence,
                    risks=rule.risks,
                    score=score,
                    confidence=_confidence(score, out_of_area=out_of_area),
                    negated_terms=negated,
                ),
            )
        )

    if candidates:
        # O limite preserva as de maior pontuação; a saída mantém a ordem das regras.
        kept = sorted(candidates, key=lambda c: (-c[0], c[1]))[: max(1, limit)]
        return tuple(issue for _, _, issue in sorted(kept, key=lambda c: c[1]))

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
            negated_terms=tuple(dict.fromkeys(all_negated)),
        ),
    )
