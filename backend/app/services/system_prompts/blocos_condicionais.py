"""Blocos condicionais de teses — Fase B (#2) do gerador de peças.

Catálogo de teses jurídicas OPCIONAIS que são injetadas no SYSTEM da etapa 7
(redação) conforme sinais confiáveis do caso (área do direito, Ficha de Triagem
CONFIRMADA) e/ou seleção manual do advogado. Cada bloco instrui a IA a incluir a
tese SOMENTE se a condição estiver ancorada nos fatos/ficha — nunca a inventar.

REGRA ANTI-FRANKENSTEIN: teses juridicamente incompatíveis não coexistem; toda
tese incluída deve estar ancorada nos fatos/ficha; condição não clara → OMITIR
(a omissão é sempre preferível à alucinação).

Nota de projeto: `incompativel_com` é o MECANISMO de sinalização de conflito
(one-way ou mútuo). O catálogo real desta fase declara listas vazias — as cinco
flags iniciais não têm impedimento jurídico rígido entre si; a regra textual
anti-frankenstein já cobre a mistura indevida. O campo/mecanismo fica pronto para
flags futuras com conflito real (ex.: teses processuais mutuamente excludentes).
"""
from __future__ import annotations

from typing import Iterable

# Catálogo de blocos. A ORDEM das chaves é o contrato de renderização (a instrução
# sai sempre na mesma sequência, independente da ordem em que as flags chegam).
BLOCOS: dict[str, dict] = {
    "dano_moral": {
        "rotulo": "Dano moral",
        "instrucao": (
            "Inclua a tese de DANO MORAL SOMENTE se os fatos descreverem lesão a "
            "direito da personalidade (honra, imagem, integridade, dignidade) que "
            "ultrapasse o mero aborrecimento; fundamente o dever de indenizar e "
            "sugira parâmetros de quantum. Caso contrário, OMITA integralmente."
        ),
        "incompativel_com": [],
    },
    "relacao_consumo": {
        "rotulo": "Relação de consumo (CDC)",
        "instrucao": (
            "Inclua a tese de RELAÇÃO DE CONSUMO (Lei 8.078/90) SOMENTE se as partes "
            "se enquadrarem como consumidor e fornecedor; quando cabível, invoque a "
            "inversão do ônus da prova (art. 6º, VIII) e a responsabilidade objetiva. "
            "Caso contrário, OMITA."
        ),
        "incompativel_com": [],
    },
    "hipossuficiencia": {
        "rotulo": "Hipossuficiência / justiça gratuita",
        "instrucao": (
            "Inclua o requerimento de JUSTIÇA GRATUITA por HIPOSSUFICIÊNCIA (art. 98 "
            "do CPC / Lei 1.060/50) SOMENTE se houver indício de insuficiência de "
            "recursos nos fatos/ficha. Caso contrário, OMITA."
        ),
        "incompativel_com": [],
    },
    "prova_documental_suficiente": {
        "rotulo": "Prova documental suficiente",
        "instrucao": (
            "Se a prova DOCUMENTAL já for suficiente para o direito alegado, "
            "afirme-o e ancore cada fato relevante ao documento correspondente "
            "'(doc. NN)', sem requerer dilação probatória desnecessária. Use SOMENTE "
            "se as provas disponíveis realmente sustentarem os fatos."
        ),
        "incompativel_com": [],
    },
    "pedido_tutela": {
        "rotulo": "Tutela de urgência",
        "instrucao": (
            "Inclua PEDIDO DE TUTELA DE URGÊNCIA (art. 300 do CPC) SOMENTE se os "
            "fatos demonstrarem probabilidade do direito E perigo de dano ou risco "
            "ao resultado útil do processo; fundamente ambos os requisitos. Caso "
            "contrário, OMITA."
        ),
        "incompativel_com": [],
    },
}

# Conjunto público das flags conhecidas — o router valida a união (determinísticas
# + manuais) contra este conjunto e IGNORA silenciosamente as desconhecidas.
FLAGS_VALIDAS: frozenset[str] = frozenset(BLOCOS)

REGRA_ANTI_FRANKENSTEIN = (
    "REGRA ANTI-FRANKENSTEIN (obrigatória): NÃO misture teses juridicamente "
    "incompatíveis entre si; toda tese incluída DEVE estar ancorada nos fatos e na "
    "Ficha de Triagem do caso; se uma condição não estiver clara nos fatos/ficha, "
    "NÃO inclua a tese nem invente fundamento — a omissão é preferível à alucinação. "
    "Uma peça coerente vale mais que uma peça com todas as teses possíveis."
)


def detectar_conflitos(
    flags: Iterable[str], catalogo: dict[str, dict] | None = None
) -> list[tuple[str, str]]:
    """Pares (a, b) de flags SELECIONADAS mutuamente/uni-lateralmente incompatíveis.

    Retorna pares ordenados e deduplicados. Conflito uni-lateral (só um lado
    declara `incompativel_com`) também é sinalizado.
    """
    cat = catalogo if catalogo is not None else BLOCOS
    presentes = {f for f in flags if f in cat}
    pares: set[tuple[str, str]] = set()
    for f in presentes:
        for outra in cat[f].get("incompativel_com", []):
            if outra in presentes:
                pares.add(tuple(sorted((f, outra))))  # type: ignore[arg-type]
    return sorted(pares)


def montar_instrucao_blocos(
    flags: Iterable[str], catalogo: dict[str, dict] | None = None
) -> str:
    """Texto das teses condicionais selecionadas + regra anti-frankenstein.

    Flags desconhecidas são ignoradas. Sem nenhuma flag conhecida → "" (não injeta
    cabeçalho vazio). A regra anti-frankenstein acompanha SEMPRE que houver ao
    menos uma tese. Conflitos declarados em `incompativel_com` viram uma linha de
    ATENÇÃO explícita para o modelo escolher apenas a tese sustentada pelos fatos.
    """
    cat = catalogo if catalogo is not None else BLOCOS
    fset = {f for f in flags if f in cat}
    if not fset:
        return ""

    # Ordem estável do catálogo (não a ordem de chegada das flags).
    selecionadas = [f for f in cat if f in fset]
    partes: list[str] = ["[BLOCOS CONDICIONAIS DE TESES]"]
    for f in selecionadas:
        partes.append(f"- {cat[f]['rotulo']}: {cat[f]['instrucao']}")

    for a, b in detectar_conflitos(selecionadas, cat):
        partes.append(
            f"ATENÇÃO — teses potencialmente incompatíveis: '{cat[a]['rotulo']}' e "
            f"'{cat[b]['rotulo']}'. Sustente APENAS a tese ancorada nos fatos; não "
            "inclua ambas."
        )

    partes.append(REGRA_ANTI_FRANKENSTEIN)
    return "\n".join(partes)


__all__ = [
    "BLOCOS",
    "FLAGS_VALIDAS",
    "REGRA_ANTI_FRANKENSTEIN",
    "detectar_conflitos",
    "montar_instrucao_blocos",
]
