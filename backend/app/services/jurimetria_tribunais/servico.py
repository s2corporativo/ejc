"""Orquestra coleta → agregação e monta a resposta com fonte, escopo e limites."""
from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.integrations.feature_flags import enabled
from app.services.jurimetria_tribunais import tpu_desfechos as tpu
from app.services.jurimetria_tribunais.agregacao import MIN_AMOSTRA, agregar
from app.services.jurimetria_tribunais.coleta import (
    ALIAS_TJMG,
    MUNICIPIOS,
    coletar,
    municipios_validos,
)

FONTE = "DataJud/CNJ — API Pública (api_publica_tjmg)"

LIMITACOES = [
    "Desfecho inferido por código de movimento da TPU (proxy): depende da "
    "disciplina de codificação de cada vara. Exibir sempre o n e a data da coleta.",
    "O DataJud atualiza com defasagem e não traz o texto da decisão.",
    "Sentença de 1º grau em texto integral não está disponível por nenhuma API; "
    "a camada de teses (acórdãos do RAG) cobre só o 2º grau.",
    "A taxa de reforma é calculada dentro da amostra coletada, não sobre todos "
    "os recursos do tribunal.",
]


def status() -> dict[str, Any]:
    s = get_settings()
    return {
        "habilitado": enabled("jurimetria_tribunais"),
        "datajud_habilitado": bool(s.DATAJUD_ENABLED and s.DATAJUD_API_KEY),
        "fonte": FONTE,
        "alias": ALIAS_TJMG,
        "municipios": [
            {"chave": k, "nome": v["nome"], "ibge": v["ibge"]} for k, v in MUNICIPIOS.items()
        ],
        "tpu_versao": tpu.TPU_VERSAO,
        "tpu_fonte": tpu.TPU_FONTE,
        "min_amostra": MIN_AMOSTRA,
        "limitacoes": LIMITACOES,
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
    docs, meta = await coletar(chaves, classe=classe, assunto=assunto, desde=desde, ate=ate)
    agregado = agregar(docs, chaves)
    return {
        "fonte": FONTE,
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
        **agregado,
    }
