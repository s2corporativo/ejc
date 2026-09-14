"""Agregação dos desfechos coletados — só contagens e taxas, nunca PII.

Definições (espelham a honestidade estatística de ``services/jurimetria.py``):

  • ``taxa_procedencia`` = (procedência + procedência parcial) ÷ decididos no
    mérito. Acordo e extinção sem mérito NÃO entram no denominador;
  • ``taxa_acordo`` = acordos ÷ processos com desfecho;
  • ``tempo_sentenca`` = dias entre ajuizamento e movimento de mérito;
  • assuntos múltiplos são preservados. Um processo contribui uma vez para
    cada assunto realmente associado a ele, e o filtro por assunto (quando
    informado) restringe a dimensão ao código solicitado;
  • além das marginais por município e por assunto, a saída contém o cruzamento
    município × assunto — necessário para responder como cada comarca decide
    cada matéria sem inferir a partir de duas taxas independentes.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean, median
from typing import Any

from app.services.jurimetria_tribunais import tpu_desfechos as tpu
from app.services.jurimetria_tribunais.coleta import MUNICIPIOS

MIN_AMOSTRA = 10  # abaixo disso a taxa é exibida com aviso, não escondida

_MERITO = (tpu.PROCEDENCIA, tpu.PROCEDENCIA_PARCIAL, tpu.IMPROCEDENCIA)
_CONTAGENS = (*_MERITO, tpu.ACORDO, tpu.SEM_MERITO)


def _municipio_de(doc: dict, pedidos: list[str]) -> str:
    orgao = doc.get("orgaoJulgador") or {}
    nome = str(orgao.get("nome") or "").casefold()
    ibge = orgao.get("codigoMunicipioIBGE")
    for chave in pedidos:
        m = MUNICIPIOS[chave]
        if m["nome"].casefold() in nome:
            return chave
        try:
            if ibge is not None and int(ibge) == m["ibge"]:
                return chave
        except (TypeError, ValueError):
            pass
    return "outro"


def _assuntos_de(
    doc: dict,
    assunto_filtro: int | None = None,
) -> list[tuple[str, str]]:
    assuntos = doc.get("assuntos") or []
    if isinstance(assuntos, dict):
        assuntos = [assuntos]
    saida: list[tuple[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for a in assuntos:
        if not isinstance(a, dict) or not (a.get("codigo") or a.get("nome")):
            continue
        codigo = str(a.get("codigo") or "")
        nome = str(a.get("nome") or "")
        if assunto_filtro is not None and codigo != str(assunto_filtro):
            continue
        par = (codigo, nome)
        if par not in vistos:
            vistos.add(par)
            saida.append(par)
    if saida:
        return saida
    # Se houve filtro e o documento não carrega o assunto solicitado, não o
    # atribuímos artificialmente a "sem assunto". O DataJud deveria tê-lo
    # selecionado server-side; metadado inconsistente fica fora da dimensão.
    if assunto_filtro is not None:
        return []
    return [("", "(sem assunto)")]


def _dias(inicio: datetime | None, fim: datetime | None) -> int | None:
    if not inicio or not fim or fim < inicio:
        return None
    return (fim - inicio).days


def _grupo_vazio() -> dict[str, Any]:
    g: dict[str, Any] = {c: 0 for c in _CONTAGENS}
    g["n"] = 0
    g["n_com_desfecho"] = 0
    g["_dias"] = []
    return g


def _fechar_grupo(g: dict[str, Any]) -> dict[str, Any]:
    decididos = sum(g[c] for c in _MERITO)
    com_desfecho = g["n_com_desfecho"]
    dias = g.pop("_dias")
    saida = dict(g)
    saida["decididos_merito"] = decididos
    saida["taxa_procedencia"] = (
        round((g[tpu.PROCEDENCIA] + g[tpu.PROCEDENCIA_PARCIAL]) / decididos, 4)
        if decididos
        else None
    )
    saida["taxa_acordo"] = (
        round(g[tpu.ACORDO] / com_desfecho, 4) if com_desfecho else None
    )
    saida["amostra_pequena"] = decididos < MIN_AMOSTRA
    saida["tempo_sentenca"] = {
        "n": len(dias),
        "mediana_dias": int(median(dias)) if dias else None,
        "media_dias": int(mean(dias)) if dias else None,
    }
    return saida


def agregar(
    docs: list[dict],
    municipios: list[str],
    *,
    assunto_filtro: int | None = None,
) -> dict[str, Any]:
    por_processo: dict[str, dict[str, Any]] = {}
    recursal: dict[str, str] = {}

    for doc in docs:
        numero = str(doc.get("numeroProcesso") or "").strip()
        if not numero:
            continue
        grau = str(doc.get("grau") or "").upper()
        movs = doc.get("movimentos") or []
        if grau.startswith("G2") or grau in {"2", "SEGUNDO"}:
            r = tpu.resultado_recursal(movs)
            if r:
                recursal[numero] = r[0]
            continue

        assuntos_doc = _assuntos_de(doc, assunto_filtro)
        entrada = por_processo.setdefault(
            numero,
            {
                "municipio": _municipio_de(doc, municipios),
                "assuntos": [],
                "ajuizamento": tpu._parse_data(doc.get("dataAjuizamento")),
                "desfecho": None,
                "data_desfecho": None,
            },
        )
        existentes = set(entrada["assuntos"])
        for assunto in assuntos_doc:
            if assunto not in existentes:
                entrada["assuntos"].append(assunto)
                existentes.add(assunto)

        d = tpu.desfecho_1grau(movs)
        if d and (
            entrada["data_desfecho"] is None
            or (d[1] and d[1] > entrada["data_desfecho"])
        ):
            entrada["desfecho"], entrada["data_desfecho"] = d

    por_municipio: dict[str, dict[str, Any]] = defaultdict(_grupo_vazio)
    por_assunto: dict[tuple[str, str], dict[str, Any]] = defaultdict(_grupo_vazio)
    por_municipio_assunto: dict[
        tuple[str, str, str], dict[str, Any]
    ] = defaultdict(_grupo_vazio)
    total = _grupo_vazio()

    for p in por_processo.values():
        assuntos = p["assuntos"] or ([] if assunto_filtro is not None else [("", "(sem assunto)")])
        grupos_unicos = (por_municipio[p["municipio"]], total)
        for g in grupos_unicos:
            g["n"] += 1
        for assunto in assuntos:
            por_assunto[assunto]["n"] += 1
            por_municipio_assunto[(p["municipio"], assunto[0], assunto[1])]["n"] += 1

        desfecho = p["desfecho"]
        if not desfecho:
            continue
        dias = (
            _dias(p["ajuizamento"], p["data_desfecho"])
            if desfecho in _MERITO
            else None
        )
        for g in grupos_unicos:
            g["n_com_desfecho"] += 1
            g[desfecho] += 1
            if dias is not None:
                g["_dias"].append(dias)
        for assunto in assuntos:
            for g in (
                por_assunto[assunto],
                por_municipio_assunto[(p["municipio"], assunto[0], assunto[1])],
            ):
                g["n_com_desfecho"] += 1
                g[desfecho] += 1
                if dias is not None:
                    g["_dias"].append(dias)

    n_recurso = len(recursal)
    reformas = sum(1 for r in recursal.values() if r in tpu.REFORMA)
    reforma = {
        "n_com_recurso_julgado": n_recurso,
        tpu.PROVIMENTO: sum(1 for r in recursal.values() if r == tpu.PROVIMENTO),
        tpu.PROVIMENTO_PARCIAL: sum(
            1 for r in recursal.values() if r == tpu.PROVIMENTO_PARCIAL
        ),
        tpu.NAO_PROVIMENTO: sum(
            1 for r in recursal.values() if r == tpu.NAO_PROVIMENTO
        ),
        "taxa_reforma": round(reformas / n_recurso, 4) if n_recurso else None,
        "amostra_pequena": n_recurso < MIN_AMOSTRA,
    }

    return {
        "total": _fechar_grupo(total),
        "por_municipio": [
            {
                "municipio": k,
                "nome": MUNICIPIOS.get(k, {}).get("nome", "Outro"),
                **_fechar_grupo(v),
            }
            for k, v in sorted(
                por_municipio.items(), key=lambda kv: -kv[1]["n"]
            )
        ],
        "por_assunto": [
            {"assunto_codigo": k[0], "assunto": k[1], **_fechar_grupo(v)}
            for k, v in sorted(por_assunto.items(), key=lambda kv: -kv[1]["n"])
        ],
        "por_municipio_assunto": [
            {
                "municipio": k[0],
                "municipio_nome": MUNICIPIOS.get(k[0], {}).get("nome", "Outro"),
                "assunto_codigo": k[1],
                "assunto": k[2],
                **_fechar_grupo(v),
            }
            for k, v in sorted(
                por_municipio_assunto.items(), key=lambda kv: -kv[1]["n"]
            )
        ],
        "reforma_2grau": reforma,
        "n_processos_1grau": len(por_processo),
        "n_registros_2grau": n_recurso,
    }
