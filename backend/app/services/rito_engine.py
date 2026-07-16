"""Motor determinístico e auditável de ritos e etapas processuais.

O motor não substitui a revisão do advogado e não calcula prazos fatais. Ele
organiza o caso por sinais documentais, área, tipo de documento, tribunal e fase,
retornando uma jornada provável, fontes normativas-base e alertas de validação.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable


def _normalizar(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", text)).strip().lower()


def _lista(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _texto_contexto(contexto: dict[str, Any]) -> str:
    partes: list[str] = []
    for key in (
        "area", "subarea", "rito", "fase", "tribunal", "orgao", "tipo_documento",
        "resumo", "sintese", "texto", "classe", "assunto", "instancia",
    ):
        partes.extend(str(item) for item in _lista(contexto.get(key)) if item)
    for key in ("pedidos", "decisoes", "eventos", "prazos", "partes"):
        partes.extend(str(item) for item in _lista(contexto.get(key)) if item)
    return _normalizar(" ".join(partes))


@dataclass(frozen=True)
class RitoRule:
    codigo: str
    nome: str
    area: str | None
    sinais: tuple[str, ...]
    etapas: tuple[str, ...]
    fontes: tuple[str, ...]
    acoes: tuple[str, ...]
    instancia: str
    exclusoes: tuple[str, ...] = ()


_RULES: tuple[RitoRule, ...] = (
    RitoRule(
        "jec",
        "Juizado Especial Cível",
        "civil",
        ("juizado especial civel", "jec", "recurso inominado", "turma recursal", "lei 9 099"),
        ("triagem de competência", "petição ou reclamação", "conciliação", "contestação", "instrução", "sentença", "embargos de declaração", "recurso inominado", "turma recursal", "cumprimento de sentença"),
        ("CF, art. 98, I", "Lei 9.099/1995"),
        ("verificar competência e alçada", "preparar conciliação", "avaliar recurso inominado", "preparar cumprimento"),
        "primeiro_grau_ou_turma_recursal",
        ("pericia complexa", "incapaz como parte", "falencia", "acidente de trabalho"),
    ),
    RitoRule(
        "jef",
        "Juizado Especial Federal",
        "previdenciario",
        ("juizado especial federal", "jef", "turma nacional de uniformizacao", "tnu", "inss", "lei 10 259"),
        ("requerimento administrativo", "triagem de competência", "ajuizamento", "contestação", "perícia ou instrução", "sentença", "recurso inominado", "turma recursal", "uniformização", "cumprimento e RPV"),
        ("CF, art. 98, I", "Lei 10.259/2001"),
        ("verificar prévio requerimento", "analisar CNIS e prova", "preparar perícia", "avaliar uniformização", "calcular atrasados em motor determinístico"),
        "primeiro_grau_ou_turma_recursal",
    ),
    RitoRule(
        "jefaz",
        "Juizado Especial da Fazenda Pública",
        "administrativo",
        ("juizado especial da fazenda publica", "jefaz", "lei 12 153", "fazenda publica"),
        ("triagem de competência", "ajuizamento", "conciliação", "contestação", "instrução", "sentença", "recurso inominado", "turma recursal", "cumprimento e RPV ou precatório"),
        ("CF, art. 98, I", "Lei 12.153/2009"),
        ("verificar ente e competência", "validar alçada", "avaliar recurso inominado", "preparar RPV ou cumprimento"),
        "primeiro_grau_ou_turma_recursal",
    ),
    RitoRule(
        "jecrim",
        "Juizado Especial Criminal",
        "criminal",
        ("juizado especial criminal", "jecrim", "termo circunstanciado", "transacao penal", "composicao civil"),
        ("termo circunstanciado", "audiência preliminar", "composição civil", "transação penal", "denúncia ou queixa", "instrução", "sentença", "recurso", "execução"),
        ("CF, art. 98, I", "Lei 9.099/1995"),
        ("verificar menor potencial ofensivo", "avaliar composição", "avaliar transação penal", "preparar audiência"),
        "primeiro_grau_ou_turma_recursal",
    ),
    RitoRule(
        "transito_administrativo",
        "Processo Administrativo de Trânsito",
        "transito",
        ("auto de infracao de transito", "renavam", "jari", "cetran", "suspensao do direito de dirigir", "cassacao da cnh"),
        ("notificação de autuação", "indicação de condutor", "defesa prévia", "notificação de penalidade", "recurso à JARI", "recurso ao CETRAN", "eventual medida judicial", "encerramento"),
        ("Código de Trânsito Brasileiro", "Resoluções CONTRAN aplicáveis", "norma do órgão autuador"),
        ("auditar requisitos do auto", "identificar prazo", "preparar defesa", "preparar JARI ou CETRAN"),
        "administrativa",
    ),
    RitoRule(
        "ambiental_administrativo",
        "Processo Administrativo Ambiental",
        "ambiental",
        ("auto de infracao ambiental", "embargo ambiental", "apreensao", "orgao ambiental", "reparacao ambiental"),
        ("autuação", "defesa administrativa", "instrução técnica", "julgamento", "recurso administrativo", "cumprimento ou conversão", "eventual medida judicial"),
        ("Lei 9.605/1998", "Decreto 6.514/2008", "norma ambiental do ente autuador"),
        ("auditar auto", "verificar competência", "obter laudo", "preparar defesa ou recurso", "avaliar riscos civil e penal conexos"),
        "administrativa",
    ),
    RitoRule(
        "licitacao_administrativo",
        "Processo de Licitação ou Contrato Administrativo",
        "administrativo",
        ("pregao eletronico", "edital de licitacao", "ata de registro de precos", "contrato administrativo", "nota de empenho", "sancao administrativa"),
        ("análise do instrumento", "pedido de esclarecimento ou impugnação", "proposta e habilitação", "recurso", "contratação", "execução", "fiscalização", "defesa em sanção", "reequilíbrio ou cobrança", "encerramento"),
        ("Lei 14.133/2021", "edital, contrato e regulamento do órgão"),
        ("extrair obrigações e prazos", "auditar sanção", "avaliar reequilíbrio", "preparar defesa administrativa"),
        "administrativa",
    ),
    RitoRule(
        "trabalhista_conhecimento",
        "Procedimento Trabalhista de Conhecimento",
        "trabalhista",
        ("reclamacao trabalhista", "reclamante", "reclamado", "vara do trabalho", "rito sumarissimo", "recurso ordinario"),
        ("petição inicial", "notificação", "contestação", "audiência", "instrução", "razões finais", "sentença", "recurso ordinário", "acórdão", "execução"),
        ("CLT", "CPC subsidiário quando cabível", "normas e precedentes trabalhistas aplicáveis"),
        ("calcular verbas em motor determinístico", "preparar audiência", "auditar pedidos e provas", "avaliar recurso"),
        "primeiro_ou_segundo_grau",
    ),
    RitoRule(
        "processo_civil_comum",
        "Procedimento Comum Cível",
        "civil",
        ("procedimento comum", "peticao inicial", "contestacao", "replica", "audiencia de instrucao", "apelacao"),
        ("petição inicial", "análise inicial", "citação", "contestação", "réplica", "saneamento", "instrução", "sentença", "apelação", "tribunal", "cumprimento de sentença"),
        ("Código de Processo Civil",),
        ("auditar competência", "cruzar fatos e provas", "preparar próxima peça", "avaliar recurso ou cumprimento"),
        "primeiro_ou_segundo_grau",
    ),
    RitoRule(
        "recurso_especial_stj",
        "Recurso Especial e tramitação no STJ",
        None,
        ("recurso especial", "aresp", "agravo em recurso especial", "superior tribunal de justica", "stj"),
        ("juízo de admissibilidade na origem", "recurso especial", "contrarrazões", "decisão de admissibilidade", "agravo em recurso especial quando cabível", "julgamento no STJ", "agravo interno ou embargos", "retorno à origem"),
        ("CF, art. 105", "CPC", "Regimento Interno do STJ"),
        ("validar prequestionamento", "auditar demonstração da questão federal", "verificar óbices", "preparar contrarrazões"),
        "superior",
    ),
    RitoRule(
        "recurso_extraordinario_stf",
        "Recurso Extraordinário e tramitação no STF",
        None,
        ("recurso extraordinario", "agravo em recurso extraordinario", "repercussao geral", "supremo tribunal federal", "stf"),
        ("juízo de admissibilidade na origem", "recurso extraordinário", "contrarrazões", "demonstração da repercussão geral", "agravo quando cabível", "julgamento no STF", "agravo interno ou embargos", "retorno à origem"),
        ("CF, art. 102", "CPC", "Regimento Interno do STF"),
        ("validar questão constitucional", "auditar repercussão geral", "verificar prequestionamento", "preparar contrarrazões"),
        "superior",
    ),
)


_STAGE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cumprimento_ou_execucao", ("cumprimento de sentenca", "execucao", "penhora", "rpv", "precatorio", "liquidacao")),
    ("tribunal_superior", ("recurso especial", "recurso extraordinario", "aresp", "repercussao geral", "stj", "stf")),
    ("recursal", ("apelacao", "recurso inominado", "recurso ordinario", "agravo", "contrarrazoes", "acordao", "turma recursal")),
    ("pos_sentenca", ("sentenca", "julgo procedente", "julgo improcedente", "embargos de declaracao")),
    ("instrucao", ("audiencia de instrucao", "depoimento", "testemunha", "pericia", "laudo pericial", "saneamento")),
    ("defesa", ("contestacao", "resposta a acusacao", "defesa previa", "impugnacao")),
    ("inicial", ("peticao inicial", "reclamacao trabalhista", "ajuizamento", "distribuicao")),
    ("administrativa", ("processo administrativo", "auto de infracao", "recurso administrativo", "jari", "cetran")),
)


def _score(rule: RitoRule, text: str, area: str | None) -> tuple[int, list[str]]:
    sinais = [signal for signal in rule.sinais if _normalizar(signal) in text]
    score = len(sinais) * 3
    area_norm = _normalizar(area)
    if rule.area and area_norm == _normalizar(rule.area):
        score += 4
    if rule.codigo in {"jec", "processo_civil_comum"} and area_norm in {"consumidor", "bancario", "imobiliario", "familia", "sucessoes"}:
        score += 1
    return score, sinais


def identificar_rito(contexto: dict[str, Any]) -> dict[str, Any]:
    """Retorna rito e jornada prováveis, sempre sujeitos a confirmação humana."""
    text = _texto_contexto(contexto)
    area = contexto.get("area")
    ranked: list[tuple[int, RitoRule, list[str]]] = []
    for rule in _RULES:
        score, sinais = _score(rule, text, str(area or ""))
        if score:
            ranked.append((score, rule, sinais))

    if ranked:
        score, rule, sinais = max(ranked, key=lambda item: item[0])
        confidence = min(0.94, 0.42 + score * 0.055)
    else:
        rule = next(r for r in _RULES if r.codigo == "processo_civil_comum")
        sinais = []
        confidence = 0.35

    etapa = "triagem"
    for stage, markers in _STAGE_MARKERS:
        if any(_normalizar(marker) in text for marker in markers):
            etapa = stage
            break

    etapas = list(rule.etapas)
    proxima: list[str] = []
    etapa_norm = _normalizar(etapa)
    indices = [i for i, item in enumerate(etapas) if etapa_norm and etapa_norm in _normalizar(item)]
    start = indices[0] + 1 if indices else 0
    proxima = etapas[start:start + 3] or etapas[:3]

    exclusoes = [item for item in rule.exclusoes if _normalizar(item) in text]
    alertas = [
        "Rito, competência, cabimento e prazos dependem de validação jurídica humana.",
        "As fontes indicadas são bases normativas; conferir redação vigente, norma local e regimento do tribunal.",
    ]
    if exclusoes:
        alertas.append("Há sinal de possível incompatibilidade com o rito: " + ", ".join(exclusoes))
    if confidence < 0.64:
        alertas.append("Classificação com poucos sinais documentais; selecionar rito manualmente antes de gerar peça ou prazo.")

    return {
        "codigo": rule.codigo,
        "nome": rule.nome,
        "area_referencia": rule.area,
        "instancia": rule.instancia,
        "etapa_atual": etapa,
        "etapas": etapas,
        "proximas_etapas": proxima,
        "acoes_recomendadas": list(rule.acoes),
        "fontes_normativas_base": list(rule.fontes),
        "sinais": sinais,
        "confianca": round(confidence, 2),
        "alertas": alertas,
        "metodo": "motor_ritos_deterministico_v1",
        "requer_confirmacao_humana": True,
    }


def catalogo_ritos() -> list[dict[str, Any]]:
    return [
        {
            "codigo": rule.codigo,
            "nome": rule.nome,
            "area": rule.area,
            "instancia": rule.instancia,
            "fontes": list(rule.fontes),
            "etapas": list(rule.etapas),
        }
        for rule in _RULES
    ]
