"""Orquestra coleta → agregação e monta resposta com fonte, escopo e limites.

A resposta principal permanece TJMG/Betim-Contagem-BH por compatibilidade com
#1528. Recortes complementares são anexados em ``fontes_complementares``:
TRT3 (benchmark trabalhista MG) e JEC/Turmas Recursais (subconjunto do lote
TJMG, sem nova chamada). Nenhum deles é misturado com o histórico do escritório.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.feature_flags import enabled
from app.services.datajud_service import DataJudDesabilitadoError
from app.services.jurimetria_tribunais import tpu_desfechos as tpu
from app.services.jurimetria_tribunais.agregacao import MIN_AMOSTRA, agregar
from app.services.jurimetria_tribunais.coleta import (
    ALIAS_TJMG,
    ALIAS_TRT3,
    MUNICIPIOS,
    coletar,
    coletar_trt3,
    filtrar_jec,
    municipios_validos,
)

logger = logging.getLogger("ejc.jurimetria.tribunais")

FONTE_TJMG = "DataJud/CNJ — API Pública (api_publica_tjmg)"
FONTE_TRT3 = "DataJud/CNJ — API Pública (api_publica_trt3)"

LIMITACOES = [
    "Desfecho inferido por código de movimento da TPU (proxy): depende da "
    "disciplina de codificação de cada unidade. Exibir sempre o n e a data da coleta.",
    "O DataJud atualiza com defasagem e não traz o texto da decisão.",
    "Decisões/ementas normalizadas do RAG são uma camada documental separada: "
    "servem para pesquisa e fundamentação, não para inflar taxa de êxito.",
    "A taxa de reforma é calculada dentro da amostra coletada, não sobre todos "
    "os recursos do tribunal.",
    "Dados externos descrevem o histórico do tribunal e nunca são apresentados "
    "como desempenho do escritório ou garantia de resultado futuro.",
]


def status() -> dict[str, Any]:
    s = get_settings()
    return {
        "habilitado": enabled("jurimetria_tribunais"),
        "datajud_habilitado": bool(s.DATAJUD_ENABLED and s.DATAJUD_API_KEY),
        "fonte": FONTE_TJMG,
        "alias": ALIAS_TJMG,
        "fontes_externas": [
            {
                "chave": "tjmg",
                "tribunal": "TJMG",
                "alias": ALIAS_TJMG,
                "tipo": "estatistica_processual",
            },
            {
                "chave": "trt3",
                "tribunal": "TRT3",
                "alias": ALIAS_TRT3,
                "tipo": "estatistica_processual",
            },
            {
                "chave": "jec_tjmg",
                "tribunal": "TJMG",
                "alias": ALIAS_TJMG,
                "tipo": "recorte_juizados_e_turmas_recursais",
            },
        ],
        "municipios": [
            {"chave": k, "nome": v["nome"], "ibge": v["ibge"]}
            for k, v in MUNICIPIOS.items()
        ],
        "tpu_versao": tpu.TPU_VERSAO,
        "tpu_fonte": tpu.TPU_FONTE,
        "min_amostra": MIN_AMOSTRA,
        "limitacoes": LIMITACOES,
    }


def _recorte_jec(
    docs_tjmg: list[dict],
    chaves: list[str],
    meta_tjmg: dict[str, Any],
) -> dict[str, Any]:
    docs = filtrar_jec(docs_tjmg)
    agregado = agregar(docs, chaves)
    return {
        "disponivel": True,
        "fonte": FONTE_TJMG,
        "escopo": {
            "tribunal": "TJMG",
            "segmento": "Juizados Especiais / Turmas Recursais",
            "municipios": [MUNICIPIOS[c]["nome"] for c in chaves],
        },
        "coleta": {
            **meta_tjmg,
            "n_documentos": len(docs),
            "derivado_sem_nova_consulta": True,
        },
        **agregado,
    }


async def _recorte_trt3(
    *,
    classe: int | None,
    assunto: int | None,
    desde: str | None,
    ate: str | None,
) -> dict[str, Any]:
    """TRT3 é complementar: falha da fonte não derruba o painel TJMG."""
    try:
        docs, meta = await coletar_trt3(
            classe=classe,
            assunto=assunto,
            desde=desde,
            ate=ate,
        )
        agregado = agregar(docs, [])
        # Sem município no índice regional: não exponha o bucket artificial
        # "Outro" como se fosse um agrupamento geográfico útil.
        agregado["por_municipio"] = []
        return {
            "disponivel": True,
            "fonte": FONTE_TRT3,
            "escopo": {
                "tribunal": "TRT3",
                "regiao": "3ª Região — Minas Gerais",
                "classe": classe,
                "assunto": assunto,
                "desde": desde,
                "ate": ate,
            },
            "coleta": meta,
            **agregado,
        }
    except (DataJudDesabilitadoError, httpx.HTTPError) as exc:
        logger.warning(
            "recorte TRT3 indisponível (tipo=%s)",
            type(exc).__name__,
        )
        return {
            "disponivel": False,
            "fonte": FONTE_TRT3,
            "escopo": {"tribunal": "TRT3", "regiao": "3ª Região — Minas Gerais"},
            "erro": "Fonte TRT3 temporariamente indisponível.",
        }


async def desfechos(
    municipios: list[str] | None,
    *,
    classe: int | None = None,
    assunto: int | None = None,
    desde: str | None = None,
    ate: str | None = None,
) -> dict[str, Any]:
    chaves = municipios_validos(municipios)
    docs, meta = await coletar(
        chaves,
        classe=classe,
        assunto=assunto,
        desde=desde,
        ate=ate,
    )
    agregado = agregar(docs, chaves)
    jec = _recorte_jec(docs, chaves, meta)
    trt3 = await _recorte_trt3(
        classe=classe,
        assunto=assunto,
        desde=desde,
        ate=ate,
    )
    return {
        "fonte": FONTE_TJMG,
        "escopo": {
            "tribunal": "TJMG",
            "municipios": [MUNICIPIOS[c]["nome"] for c in chaves],
            "classe": classe,
            "assunto": assunto,
            "desde": desde,
            "ate": ate,
        },
        "coleta": meta,
        "tpu": {"versao": tpu.TPU_VERSAO, "fonte": tpu.TPU_FONTE},
        "min_amostra": MIN_AMOSTRA,
        "limitacoes": LIMITACOES,
        "fontes_complementares": {
            "jec_tjmg": jec,
            "trt3": trt3,
        },
        **agregado,
    }
