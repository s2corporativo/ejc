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
    "Quando o teto de coleta é atingido, as taxas são suprimidas: o primeiro "
    "lote cronológico não é tratado como amostra representativa do tribunal.",
    "No recorte TJMG por comarca, taxa de reforma em 2º grau fica indisponível "
    "até que os recursos sejam vinculados aos números dos processos de origem; "
    "câmaras recursais não carregam necessariamente o nome da comarca.",
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


def _suprimir_taxas_se_truncado(
    agregado: dict[str, Any], meta: dict[str, Any]
) -> dict[str, Any]:
    """Não transforma lote cronológico capado em estatística representativa."""
    if not meta.get("truncado"):
        agregado["amostra_truncada"] = False
        return agregado

    for chave in ("total",):
        grupo = agregado.get(chave)
        if isinstance(grupo, dict):
            grupo["taxa_procedencia"] = None
            grupo["taxa_acordo"] = None
            if isinstance(grupo.get("tempo_sentenca"), dict):
                grupo["tempo_sentenca"]["mediana_dias"] = None
                grupo["tempo_sentenca"]["media_dias"] = None
    for chave in ("por_municipio", "por_assunto", "por_municipio_assunto"):
        for grupo in agregado.get(chave) or []:
            grupo["taxa_procedencia"] = None
            grupo["taxa_acordo"] = None
            if isinstance(grupo.get("tempo_sentenca"), dict):
                grupo["tempo_sentenca"]["mediana_dias"] = None
                grupo["tempo_sentenca"]["media_dias"] = None
    if isinstance(agregado.get("reforma_2grau"), dict):
        agregado["reforma_2grau"]["taxa_reforma"] = None

    agregado["amostra_truncada"] = True
    agregado["aviso_amostragem"] = (
        "O limite máximo de registros foi atingido. Contagens são exibidas, "
        "mas taxas e tempos foram suprimidos porque o lote não é uma amostra "
        "estatisticamente representativa do universo consultado. Restrinja "
        "período, classe ou assunto para obter um recorte não truncado."
    )
    return agregado


def _desabilitar_reforma_geografica(agregado: dict[str, Any]) -> None:
    reforma = agregado.get("reforma_2grau")
    if not isinstance(reforma, dict):
        return
    reforma["taxa_reforma"] = None
    reforma["disponivel"] = False
    reforma["motivo"] = (
        "O filtro por comarca seleciona o primeiro grau, mas o órgão de segundo "
        "grau é uma Câmara/Turma e pode não carregar o nome da comarca. A taxa "
        "só será publicada após vínculo explícito pelo número do processo de origem."
    )


def _recorte_jec(
    docs_tjmg: list[dict],
    chaves: list[str],
    meta_tjmg: dict[str, Any],
    *,
    assunto: int | None,
) -> dict[str, Any]:
    docs = filtrar_jec(docs_tjmg)
    agregado = agregar(docs, chaves, assunto_filtro=assunto)
    _desabilitar_reforma_geografica(agregado)
    agregado = _suprimir_taxas_se_truncado(agregado, meta_tjmg)
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
        agregado = agregar(docs, [], assunto_filtro=assunto)
        agregado["por_municipio"] = []
        agregado["por_municipio_assunto"] = []
        agregado = _suprimir_taxas_se_truncado(agregado, meta)
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
            "escopo": {
                "tribunal": "TRT3",
                "regiao": "3ª Região — Minas Gerais",
            },
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
    agregado = agregar(docs, chaves, assunto_filtro=assunto)
    _desabilitar_reforma_geografica(agregado)
    agregado = _suprimir_taxas_se_truncado(agregado, meta)
    jec = _recorte_jec(docs, chaves, meta, assunto=assunto)
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
