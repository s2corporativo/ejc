"""Agregação dos desfechos coletados — só contagens e taxas, nunca PII.

Definições (espelham a honestidade estatística de ``services/jurimetria.py``):

  • ``taxa_procedencia`` = (procedência + procedência parcial) ÷ decididos no
    mérito (procedência + parcial + improcedência). Acordo e extinção sem
    mérito NÃO entram no denominador: acordo não é vitória judicial e
    extinção não é decisão de mérito. Ambos ficam visíveis nas contagens;
  • ``taxa_acordo`` = acordos ÷ processos com desfecho (qualquer);
  • ``tempo_sentenca`` = dias entre ``dataAjuizamento`` e a data do movimento
    de desfecho de mérito; mediana e média, com o ``n`` que as sustenta;
  • ``reforma_2grau`` = entre os processos com registro de 2º grau julgado,
    quantos tiveram provimento (total ou parcial) — só faz sentido dentro da
    amostra coletada, por isso ``n_com_recurso_julgado`` acompanha a taxa.
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


def _assunto_de(doc: dict) -> tuple[str, str]:
    assuntos = doc.get("assuntos") or []
    if isinstance(assuntos, dict):
        assuntos = [assuntos]
    for a in assuntos:
        if isinstance(a, dict) and (a.get("codigo") or a.get("nome")):
            return str(a.get("codigo") or ""), str(a.get("nome") or "")
    return "", "(sem assunto)"


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
        if decididos else None
    )
    saida["taxa_acordo"] = round(g[tpu.ACORDO] / com_desfecho, 4) if com_desfecho else None
    saida["amostra_pequena"] = decididos < MIN_AMOSTRA
    saida["tempo_sentenca"] = {
        "n": len(dias),
        "mediana_dias": int(median(dias)) if dias else None,
        "media_dias": int(mean(dias)) if dias else None,
    }
    return saida


def agregar(docs: list[dict], municipios: list[str]) -> dict[str, Any]:
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
        # 1º grau (ou grau ausente: tratado como originário)
        entrada = por_processo.setdefault(numero, {
            "municipio": _municipio_de(doc, municipios),
            "assunto": _assunto_de(doc),
            "ajuizamento": tpu._parse_data(doc.get("dataAjuizamento")),
            "desfecho": None,
            "data_desfecho": None,
        })
        d = tpu.desfecho_1grau(movs)
        if d and (entrada["data_desfecho"] is None or (d[1] and d[1] > entrada["data_desfecho"])):
            entrada["desfecho"], entrada["data_desfecho"] = d

    por_municipio: dict[str, dict[str, Any]] = defaultdict(_grupo_vazio)
    por_assunto: dict[tuple[str, str], dict[str, Any]] = defaultdict(_grupo_vazio)
    total = _grupo_vazio()

    for numero, p in por_processo.items():
        grupos = (por_municipio[p["municipio"]], por_assunto[p["assunto"]], total)
        for g in grupos:
            g["n"] += 1
        desfecho = p["desfecho"]
        if not desfecho:
            continue
        for g in grupos:
            g["n_com_desfecho"] += 1
            g[desfecho] += 1
            if desfecho in _MERITO:
                dias = _dias(p["ajuizamento"], p["data_desfecho"])
                if dias is not None:
                    g["_dias"].append(dias)

    n_recurso = len(recursal)
    reformas = sum(1 for r in recursal.values() if r in tpu.REFORMA)
    reforma = {
        "n_com_recurso_julgado": n_recurso,
        tpu.PROVIMENTO: sum(1 for r in recursal.values() if r == tpu.PROVIMENTO),
        tpu.PROVIMENTO_PARCIAL: sum(1 for r in recursal.values() if r == tpu.PROVIMENTO_PARCIAL),
        tpu.NAO_PROVIMENTO: sum(1 for r in recursal.values() if r == tpu.NAO_PROVIMENTO),
        "taxa_reforma": round(reformas / n_recurso, 4) if n_recurso else None,
        "amostra_pequena": n_recurso < MIN_AMOSTRA,
    }

    return {
        "total": _fechar_grupo(total),
        "por_municipio": [
            {"municipio": k, "nome": MUNICIPIOS.get(k, {}).get("nome", "Outro"), **_fechar_grupo(v)}
            for k, v in sorted(por_municipio.items(), key=lambda kv: -kv[1]["n"])
        ],
        "por_assunto": [
            {"assunto_codigo": k[0], "assunto": k[1], **_fechar_grupo(v)}
            for k, v in sorted(por_assunto.items(), key=lambda kv: -kv[1]["n"])
        ],
        "reforma_2grau": reforma,
        "n_processos_1grau": len(por_processo),
        "n_registros_2grau": n_recurso,
    }
