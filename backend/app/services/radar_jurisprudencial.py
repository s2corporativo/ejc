# ── app/services/radar_jurisprudencial.py ────────────────────────────────────
# Radar Jurisprudencial — Camada 1 (determinística) do PR 4 da série de
# consolidação do Banco de Teses Jurídicas.
#
# Cruza UMA decisão nova × N teses e devolve as teses possivelmente afetadas.
# É o mesmo problema que `impacto_regulatorio.py` já resolve para publicação
# do Diário Oficial × tese — este módulo NÃO reimplementa o motor de score,
# reusa `tese_caso_matcher.pontuar_texto` (mesma composição de peso, pra não
# ter dois pesos divergindo com o tempo) e acrescenta um segundo sinal que o
# Diário Oficial não tem: casamento de CITAÇÃO ESTRUTURADA (número de súmula/
# tema/processo/artigo), via o parser já existente em
# `verificador_jurisprudencia.analisar_texto`.
#
# INVARIANTES (mesmos de impacto_regulatorio.py):
#   • 100% DETERMINÍSTICO — sem IA. A camada 3 (explicação por IA) consome a
#     SAÍDA deste módulo, nunca decide o que entra aqui.
#   • FUNÇÕES PURAS — sem banco e sem rede. Quem consulta/persiste é o
#     chamador (radar_jurisprudencial_registro.py).
#   • SUGESTÃO, NUNCA VEREDITO — a saída diz "esta decisão PODE afetar esta
#     tese, e foi por isto (termos casados / citação idêntica)". Mudar
#     `Tese.status_validacao` continua sendo SOMENTE ato humano via
#     `POST /teses/{tese_id}/validacao` — este módulo nunca escreve nela.
from __future__ import annotations

import re

from app.services.tese_caso_matcher import (
    PISO_RELEVANCIA_PADRAO,
    pontuar_texto,
)
from app.services.verificador_jurisprudencia import SUMULA_TETO, analisar_texto

# Mesmos tetos de varredura de impacto_regulatorio.py — o cruzamento é
# O(decisões × teses × termos) em memória.
MAX_TESES_VARRIDAS = 500

# Teto de súmula para tribunal não identificado no texto (mesmo fallback de
# `verificador_jurisprudencia._SUMULA_TETO_DEFAULT`, recalculado aqui porque
# aquele nome é privado ao módulo de origem).
_SUMULA_TETO_MAX = max(SUMULA_TETO.values())

SEVERIDADES = ("critica", "alta", "media", "baixa")


def _texto_decisao(decisao: dict) -> str:
    return " ".join(str(decisao.get(c) or "") for c in ("titulo", "ementa"))


def _sumula_plausivel(numero: object, tribunal: object) -> bool:
    try:
        n = int(str(numero))
    except (TypeError, ValueError):
        return False
    teto = SUMULA_TETO.get(str(tribunal or "").upper(), _SUMULA_TETO_MAX)
    return 0 < n <= teto


def _chave_citacao(achado: dict) -> tuple | None:
    """Chave comparável de uma citação estruturada, ou None se não for
    comparável (tipo `generica`, ou súmula implausível — SUMULA_TETO já filtra
    aqui para não basear um alerta numa citação com cara de alucinação, ainda
    que a decisão em si venha de fonte oficial).
    """
    tipo = achado.get("tipo")
    if tipo == "sumula":
        numero, tribunal = achado.get("numero"), achado.get("tribunal")
        if not _sumula_plausivel(numero, tribunal):
            return None
        return ("sumula", str(numero), str(tribunal or "").upper(), bool(achado.get("vinculante")))
    if tipo == "recurso":
        numero = re.sub(r"\D", "", str(achado.get("numero") or ""))
        if not numero:
            return None
        return ("recurso", str(achado.get("classe") or "").upper(), numero)
    if tipo == "processo_cnj":
        numero = re.sub(r"\D", "", str(achado.get("numero") or ""))
        if not numero:
            return None
        return ("processo_cnj", numero)
    if tipo == "artigo":
        numero = achado.get("numero")
        if not numero:
            return None
        return ("artigo", str(numero), str(achado.get("diploma") or "").upper())
    return None


def _citacoes_estruturadas(texto: str) -> dict[tuple, dict]:
    """Mapa chave→achado das citações comparáveis de um texto (1ª ocorrência)."""
    mapa: dict[tuple, dict] = {}
    for achado in analisar_texto(texto):
        chave = _chave_citacao(achado)
        if chave is not None and chave not in mapa:
            mapa[chave] = achado
    return mapa


def _severidade(score: int, tem_citacao_casada: bool) -> str | None:
    if tem_citacao_casada:
        return "critica"
    if score >= 85:
        return "alta"
    if score >= 55:
        return "media"
    if score >= PISO_RELEVANCIA_PADRAO:
        return "baixa"
    return None


def avaliar_decisao(
    decisao: dict,
    teses: list[dict],
    *,
    piso: int = PISO_RELEVANCIA_PADRAO,
    limite: int = 20,
) -> list[dict]:
    """Cruza UMA decisão nova × N teses e devolve as teses possivelmente afetadas.

    `decisao`: dict com `id`, `titulo`, `ementa`, `tribunal`, `numero_processo`,
    `data_julgamento`, `link`, `area_juridica` (já vem classificada no `extra`
    do `KnowledgeDoc` — não precisa de classificador de área aqui).

    `teses`: dicts com `id`, `titulo`, `area_juridica`, `termos` (pré-extraído
    pelo chamador via `extrair_termos(titulo, tags, descricao, fundamentacao)`
    — inclui `fundamentacao` porque é onde mora o dispositivo legal citado, o
    texto que mais importa para "esta decisão pode superar esta tese"),
    `fundamentacao`, `jurisprudencia` (usados aqui só para extrair citações
    estruturadas via `analisar_texto`, não para o score textual).

    Saída ordenada por severidade/score, molde compatível com o JSON
    `teses_afetadas` de `TeseAlertaJurisprudencial`:
    `[{tese_id, titulo, score, termos_casados, citacoes_casadas, severidade,
       area_alinhada}]`.
    """
    if not teses:
        return []

    texto_decisao = _texto_decisao(decisao)
    citacoes_decisao = _citacoes_estruturadas(texto_decisao)
    area_decisao = decisao.get("area_juridica")

    afetadas: list[dict] = []
    for tese in teses[:MAX_TESES_VARRIDAS]:
        termos = tese.get("termos") or []
        if not termos:
            continue

        area_alinhada = bool(
            area_decisao and tese.get("area_juridica")
            and str(area_decisao).strip().lower() == str(tese.get("area_juridica")).strip().lower()
        )
        score, termos_casados = pontuar_texto(termos, texto_decisao, area_alinhada=area_alinhada)

        texto_tese = " ".join(
            str(tese.get(c) or "") for c in ("fundamentacao", "jurisprudencia")
        )
        citacoes_tese = _citacoes_estruturadas(texto_tese)
        chaves_casadas = set(citacoes_decisao) & set(citacoes_tese)
        citacoes_casadas = [
            {"tipo": chave[0], "trecho": citacoes_decisao[chave].get("trecho")}
            for chave in sorted(chaves_casadas, key=str)
        ]

        severidade = _severidade(score, bool(citacoes_casadas))
        if severidade is None:
            continue

        afetadas.append({
            "tese_id": tese.get("id"),
            "titulo": tese.get("titulo"),
            "score": score,
            "termos_casados": termos_casados,
            "citacoes_casadas": citacoes_casadas,
            "severidade": severidade,
            "area_alinhada": area_alinhada,
        })

    ordem_severidade = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
    afetadas.sort(
        key=lambda t: (ordem_severidade[t["severidade"]], -t["score"], str(t.get("tese_id") or ""))
    )
    return afetadas[:limite]
