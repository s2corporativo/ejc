#!/usr/bin/env python3
"""Ingestão governada da Biblioteca Jurídica EJC.

O script é deliberadamente fail-closed: qualquer inconsistência de autenticidade,
proveniência, metadado obrigatório, classificação ou grafo impede ``--execute``.
Nenhum documento é autoaprovado: todo lote entra como PENDENTE de curadoria.
A escrita do lote é atômica: só existe commit após todos os documentos concluírem.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from urllib.parse import urlparse

import yaml

ROOT_AREA = [
    "tributario", "ambiental", "administrativo", "licitacoes", "empresarial",
    "consumidor_bancario", "trabalhista_empresarial", "processual_civil",
]
AREA_VOCAB = set(ROOT_AREA)
TIPO_VOCAB = {
    "tese_juridica", "jurisprudencia_estruturada", "bloco_argumentativo",
    "pedido_juridico", "modelo_peca", "fonte_primaria",
}
CONF_VOCAB = {"ALTA", "MEDIA", "BAIXA"}
ORIGEM_VOCAB = {
    "fonte_oficial", "jurisprudencia_oficial", "legislacao", "doutrina",
    "analise_IA", "modelo_IA", "modelo_simulado", "documento_usuario", "documento_processual_real",
}
AUTORIDADE_VOCAB = {
    "normativa", "vinculante", "jurisprudencial", "persuasiva", "doutrinaria",
    "analitica", "modelo_sem_autoridade",
}
DERIVADOS_EXIGEM_FONTE = {"tese_juridica", "bloco_argumentativo", "pedido_juridico"}
AUTORIDADES_QUE_NAO_ADMITEM_SIMULACAO = {
    "normativa", "vinculante", "jurisprudencial", "persuasiva",
}

TRIBUNAL_PAT = re.compile(
    r"\b(STF|STJ|TCU|TST|TSE|STM|TJMG|TJ[A-Z]{2}|TRF\s?-?\s?[1-6]|TRT\s?-?\s?\d{1,2})\b",
    re.I,
)
PROCESSO_PAT = re.compile(
    r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b|"
    r"\b(?:REsp|AREsp|EREsp|RE|ARE|AgInt|AgRg|EDcl|ADI|ADC|ADPF|HC|RHC|MS)\s*"
    r"(?:n[ºo°.]*\s*)?[\d.]+(?:\s*/\s*[A-Z]{2})?\b",
    re.I,
)
# Marcadores de fonte/processo SIMULADO. Deliberadamente não casa uma mera nota
# de auditoria como "a versão anterior continha referências simuladas" e não se
# aplica a modelo_peca sem autoridade, que pode usar exemplos fictícios isolados.
SIMULACAO_PAT = re.compile(
    r"(?:\burl\s+(?:oficial\s*:\s*)?simulad[oa]s?\b|"
    r"\b(?:processo|julgado|precedente|fonte)\s+(?:simulad[oa]s?|fict[ií]ci[oa]s?|inventad[oa]s?)\b|"
    r"\(\s*simulad[oa]s?\s*,?\s*fonte\s+oficial\b|"
    r"\burl\s+de\s+exemplo\b|\bexemplo\s+hipot[eé]tico\b)",
    re.I,
)
URL_PAT = re.compile(r"https?://[^\s)>\]]+", re.I)

OFFICIAL_DOMAIN_SUFFIXES = (
    "stf.jus.br", "stj.jus.br", "tst.jus.br", "tse.jus.br", "stm.jus.br",
    "cnj.jus.br", "tcu.gov.br", "gov.br", "planalto.gov.br", "senado.leg.br",
    "camara.leg.br", "lexml.gov.br", "jus.br",
)


def _normalizar_datas(valor):
    """YAML converte data ISO não citada (ex.: 2026-08-14) em datetime.date,
    o que quebra a serialização JSON do JSONB `extra` na ingestão. Normaliza
    para string ISO, recursivamente, preservando o valor legível."""
    if isinstance(valor, (datetime.date, datetime.datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _normalizar_datas(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_normalizar_datas(v) for v in valor]
    return valor


def strip_frontmatter(text: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        m = re.match(r"^---\s*\n(.*?)---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = _normalizar_datas(dict(yaml.safe_load(m.group(1)) or {}))
    return meta, m.group(2)


def load_piloto(base_dir: str):
    docs = []
    for area in ROOT_AREA:
        adir = os.path.join(base_dir, area)
        if not os.path.isdir(adir):
            continue
        for fn in sorted(os.listdir(adir)):
            if fn.endswith(".md") and not fn.startswith("RELATORIO"):
                path = os.path.join(adir, fn)
                with open(path, encoding="utf-8") as f:
                    raw = f.read()
                meta, body = strip_frontmatter(raw)
                meta["__file"] = path
                meta["__body"] = body
                meta["__raw"] = raw
                docs.append(meta)
    return docs


def load_grafo(path: str | None) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        raise ValueError("arquivo de grafo deve conter objeto YAML")
    return loaded


def _host_oficial(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return bool(host) and any(
        host == suffix or host.endswith("." + suffix)
        for suffix in OFFICIAL_DOMAIN_SUFFIXES
    )


def _urls(body: str, d: dict) -> list[str]:
    urls = list(URL_PAT.findall(body or ""))
    for key in ("link_official", "fonte_oficial", "url_oficial"):
        if d.get(key):
            urls.append(str(d[key]).strip())
    for item in d.get("fontes_utilizadas") or []:
        if isinstance(item, str) and item.startswith(("http://", "https://")):
            urls.append(item)
        elif isinstance(item, dict):
            url = item.get("url") or item.get("link")
            if url:
                urls.append(str(url))
    return sorted(set(urls))


def _urls_oficiais(body: str, d: dict) -> list[str]:
    return [url for url in _urls(body, d) if _host_oficial(url)]


def categoria_rag(d: dict) -> str:
    tipo = d.get("tipo_camada")
    area = str(d.get("area_juridica") or "").strip().lower()
    tribunal = str(d.get("tribunal") or "").upper().replace(" ", "")
    body = str(d.get("__body") or "")

    if tipo == "tese_juridica":
        return "tese_juridica"
    if tipo == "bloco_argumentativo":
        return "bloco_argumentativo"
    if tipo == "pedido_juridico":
        return "pedido_juridico"
    if tipo == "modelo_peca":
        return "modelo_documento_juridico"
    if tipo == "fonte_primaria":
        return f"legislacao_{area}" if area else "legislacao_geral"
    if tipo == "jurisprudencia_estruturada":
        if not tribunal:
            match = TRIBUNAL_PAT.search(body)
            tribunal = match.group(1).upper().replace(" ", "") if match else ""
        if tribunal.startswith("STF"):
            return "jurisprudencia_stf"
        if tribunal.startswith("STJ"):
            return "jurisprudencia_stj"
        if tribunal.startswith("TST"):
            return "jurisprudencia_tst"
        if tribunal.startswith("TCU"):
            return "jurisprudencia_tcu"
        if tribunal.startswith("TJMG"):
            return "jurisprudencia_tjmg_acordaos"
        if tribunal.startswith("TRF"):
            return "jurisprudencia_trf"
        if tribunal.startswith("TRT"):
            return "jurisprudencia_trt"
        return "jurisprudencia"
    raise ValueError(f"tipo_camada sem mapeamento: {tipo}")


def validar(docs):
    erros: list[str] = []
    ids: set[str] = set()
    for d in docs:
        path = d.get("__file", "?")
        raw = d.get("__raw", "")
        body = d.get("__body", "")

        obrigatorias = (
            "tipo_camada", "canonical_id", "origem_conteudo", "autoridade_juridica",
            "score_autoridade", "area_juridica", "nivel_confiaca", "data_pesquisa",
        )
        for key in obrigatorias:
            if key not in d or not str(d.get(key, "")).strip():
                erros.append(f"[{path}] chave obrigatória ausente: {key}")

        if raw.startswith("---") and not re.match(r"^---\s*\n.*?\n---\s*\n", raw, re.S):
            erros.append(
                f"[{path}] front-matter fora do formato canônico "
                "(fechamento '---' em linha própria)"
            )
        if d.get("tipo_camada") not in TIPO_VOCAB:
            erros.append(
                f"[{path}] tipo_camada fora do vocabulário: {d.get('tipo_camada')}"
            )
        if d.get("area_juridica") not in AREA_VOCAB:
            erros.append(
                f"[{path}] area_juridica fora do vocabulário: {d.get('area_juridica')}"
            )
        if d.get("origem_conteudo") not in ORIGEM_VOCAB:
            erros.append(
                f"[{path}] origem_conteudo fora do vocabulário: {d.get('origem_conteudo')}"
            )
        if d.get("autoridade_juridica") not in AUTORIDADE_VOCAB:
            erros.append(
                f"[{path}] autoridade_juridica fora do vocabulário: "
                f"{d.get('autoridade_juridica')}"
            )

        try:
            score = int(d.get("score_autoridade", -1))
        except (TypeError, ValueError):
            erros.append(f"[{path}] score_autoridade não numérico")
            score = -1
        if not (0 <= score <= 100):
            erros.append(
                f"[{path}] score_autoridade fora de 0-100: {d.get('score_autoridade')}"
            )

        nivel = str(d.get("nivel_confiaca", "")).upper().strip()
        if nivel not in CONF_VOCAB:
            erros.append(
                f"[{path}] nivel_confiaca fora de {CONF_VOCAB}: {d.get('nivel_confiaca')}"
            )

        canonical_id = str(d.get("canonical_id") or "").strip()
        if canonical_id in ids:
            erros.append(f"[{path}] canonical_id duplicado: {canonical_id}")
        if canonical_id:
            ids.add(canonical_id)

        tipo = d.get("tipo_camada")
        origem = d.get("origem_conteudo")
        autoridade = d.get("autoridade_juridica")
        urls = _urls(body, d)
        urls_validas = _urls_oficiais(body, d)

        if (
            autoridade in AUTORIDADES_QUE_NAO_ADMITEM_SIMULACAO
            and SIMULACAO_PAT.search(body)
        ):
            erros.append(
                f"[{path}] fonte/processo simulado é proibido em conteúdo "
                "com autoridade jurídica"
            )

        if tipo == "jurisprudencia_estruturada":
            if origem not in {"fonte_oficial", "jurisprudencia_oficial"}:
                erros.append(f"[{path}] jurisprudência estruturada exige origem oficial")
            if autoridade not in {"vinculante", "jurisprudencial", "persuasiva"}:
                erros.append(
                    f"[{path}] autoridade incompatível com jurisprudência estruturada: "
                    f"{autoridade}"
                )
            if not TRIBUNAL_PAT.search(body) and not str(d.get("tribunal") or "").strip():
                erros.append(f"[{path}] jurisprudência sem tribunal identificável")
            if PROCESSO_PAT.search(body) and not urls_validas:
                erros.append(
                    f"[{path}] processo/julgado citado sem URL oficial "
                    "em domínio institucional"
                )
            if nivel == "ALTA" and not urls_validas:
                erros.append(
                    f"[{path}] jurisprudência ALTA sem fonte oficial rastreável"
                )
            if nivel == "ALTA" and not (
                d.get("last_verified_at") or d.get("data_pesquisa")
            ):
                erros.append(
                    f"[{path}] jurisprudência ALTA sem data de verificação"
                )

        if tipo == "fonte_primaria":
            if origem not in {"fonte_oficial", "legislacao"}:
                erros.append(
                    f"[{path}] fonte_primaria exige origem fonte_oficial/legislacao"
                )
            if autoridade not in {"normativa", "vinculante"}:
                erros.append(
                    f"[{path}] fonte_primaria exige autoridade normativa/vinculante"
                )
            if nivel == "ALTA" and not urls_validas:
                erros.append(f"[{path}] fonte_primaria ALTA sem URL oficial")

        if tipo in DERIVADOS_EXIGEM_FONTE and not (
            d.get("fontes_utilizadas") or urls
        ):
            erros.append(
                f"[{path}] conteúdo derivado exige fontes_utilizadas ou URL rastreável"
            )

        if tipo == "modelo_peca" and autoridade != "modelo_sem_autoridade":
            erros.append(
                f"[{path}] modelo de peça não pode possuir autoridade jurídica própria"
            )

        if origem in {"analise_IA", "modelo_IA", "modelo_simulado"} and autoridade not in {
            "analitica", "modelo_sem_autoridade",
        }:
            erros.append(
                f"[{path}] conteúdo de IA deve ter autoridade analítica "
                "ou modelo_sem_autoridade"
            )
        if origem in {"modelo_IA", "modelo_simulado"} and score != 0:
            erros.append(f"[{path}] modelo de IA/simulado deve ter score_autoridade=0")

        if origem == "modelo_simulado":
            if tipo != "modelo_peca":
                erros.append(f"[{path}] modelo_simulado exige tipo_camada=modelo_peca")
            if not bool(d.get("gerado_por_IA")):
                erros.append(f"[{path}] modelo_simulado exige gerado_por_IA=true")
            authority_level = str(d.get("authority_level") or "").strip().lower()
            if authority_level and authority_level != "modelo_sem_autoridade":
                erros.append(
                    f"[{path}] modelo_simulado não pode declarar authority_level jurídico: "
                    f"{d.get('authority_level')}"
                )

        if (
            origem in {"fonte_oficial", "jurisprudencia_oficial", "legislacao"}
            and urls
            and not urls_validas
        ):
            erros.append(
                f"[{path}] origem declarada oficial, mas nenhuma URL pertence "
                "a domínio institucional permitido"
            )

        if bool(d.get("gerado_por_IA")) and autoridade in {
            "normativa", "vinculante", "jurisprudencial",
        }:
            erros.append(
                f"[{path}] conteúdo gerado por IA não pode receber "
                "autoridade jurídica própria"
            )

        try:
            categoria_rag(d)
        except ValueError as exc:
            erros.append(f"[{path}] {exc}")

    return erros


def build_extra(d):
    """Monta JSONB canônico. Ingestão do lote nasce PENDENTE até curadoria."""
    fontes = d.get("fontes_utilizadas") or _urls(d.get("__body", ""), d)
    extra = {
        "tipo_camada": d["tipo_camada"],
        "canonical_id": d["canonical_id"],
        "origem_conteudo": d["origem_conteudo"],
        "autoridade_juridica": d["autoridade_juridica"],
        "authority_level": d.get("authority_level", d["autoridade_juridica"]),
        "score_autoridade": int(d["score_autoridade"]),
        "area_juridica": d["area_juridica"],
        "nivel_confiaca": str(d["nivel_confiaca"]).upper(),
        "data_pesquisa": d["data_pesquisa"],
        "gerado_por_IA": bool(d.get("gerado_por_IA")),
        "fontes_utilizadas": fontes,
        "relacoes": d.get("__relacoes") or [],
        "rag_status": "pendente",
        "requires_human_review": True,
        "human_reviewed": False,
    }
    for key in (
        "tribunal", "orgao_julgador", "numero_processo", "relator",
        "data_julgamento", "ementa", "tese_adotada", "resultado",
        "posicao_estrategica", "legal_status", "legal_status_origem",
        "legal_status_verificado_em", "link_official", "last_verified_at",
    ):
        if d.get(key):
            extra[key] = d[key]
    return extra


def _bootstrap_backend() -> None:
    candidatos = [
        "/app",
        "/opt/ejc/backend",
        "/home/ubuntu/ejc/backend",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ]
    for candidato in candidatos:
        if os.path.isdir(os.path.join(candidato, "app")):
            if candidato not in sys.path:
                sys.path.insert(0, candidato)
            return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Executa a ingestão real")
    parser.add_argument(
        "--dir", default=None,
        help="Diretório raiz do lote (autodetectado se omitido)",
    )
    parser.add_argument(
        "--graph", default=None,
        help="YAML do grafo; se omitido usa <dir>/grafico_relacoes.yaml quando existir",
    )
    args = parser.parse_args()

    base = args.dir or (
        "/lote_piloto" if os.path.isdir("/lote_piloto") else "/home/ubuntu/lote_piloto"
    )
    docs = load_piloto(base)
    print(f"[{len(docs)} documentos carregados de {base}]")

    if not docs:
        print("[FALHA] Nenhum documento encontrado; ingestão abortada.")
        sys.exit(2)

    erros = validar(docs)

    graph_path = args.graph or os.path.join(base, "grafico_relacoes.yaml")
    if os.path.isfile(graph_path):
        try:
            grafo = load_grafo(graph_path)
            _bootstrap_backend()
            from app.services.legal_graph import indexar_relacoes, validar_grafo

            ids = {
                str(d.get("canonical_id") or "").strip()
                for d in docs if d.get("canonical_id")
            }
            erros_grafo = validar_grafo(grafo, ids)
            erros.extend(f"[GRAFO] {erro}" for erro in erros_grafo)
            if not erros_grafo:
                indice = indexar_relacoes(grafo)
                for d in docs:
                    d["__relacoes"] = indice.get(
                        str(d.get("canonical_id") or ""), []
                    )
                print(f"[grafo validado: {len(grafo.get('arestas') or [])} arestas]")
        except Exception as exc:
            erros.append(f"[GRAFO] falha ao carregar/validar: {exc}")
    else:
        print(
            "[INFO] grafo não fornecido; documentos serão ingeridos "
            "sem relações canônicas"
        )

    for erro in erros:
        print("ERRO:", erro)
    if erros:
        print(
            f"[BLOQUEADO] {len(erros)} problema(s) detectado(s). "
            "Nenhuma ingestão será executada."
        )
        sys.exit(3)

    print(
        "[validação OK: metadados, proveniência, classificação, "
        "fontes e grafo compatíveis]"
    )
    if not args.execute:
        print("\n[DRY-RUN] Nenhuma inserção realizada. Para ingerir na base do EJC:")
        for d in sorted(docs, key=lambda item: item["canonical_id"]):
            print(
                f"  ingest {d['canonical_id']} | categoria={categoria_rag(d)} "
                f"| {d['__file']}"
            )
        return

    _bootstrap_backend()
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.ingestion_service import upsert_documento
        from app.services.legal_chunker import chunk_documento_juridico
    except Exception as exc:
        print(f"[FALHA] Não foi possível importar serviços do EJC: {exc}")
        sys.exit(2)

    import asyncio

    async def run():
        resultados: list[tuple[str, str]] = []
        async with AsyncSessionLocal() as db:
            try:
                for d in docs:
                    extra = build_extra(d)
                    titulo = (
                        (d.get("__body") or "").split("\n")[0].lstrip("#").strip()
                        or d["canonical_id"]
                    )
                    categoria = categoria_rag(d)
                    chunks_juridicos = chunk_documento_juridico(
                        d["__body"],
                        tipo_camada=d["tipo_camada"],
                        categoria=categoria,
                    )
                    resultado = await upsert_documento(
                        db,
                        chave_origem=d["canonical_id"],
                        titulo=titulo,
                        categoria=categoria,
                        conteudo=d["__body"],
                        fonte=d.get("link_official") or None,
                        tribunal=d.get("tribunal") or None,
                        extra=extra,
                        confianca={
                            "ALTA": "alta",
                            "MEDIA": "media",
                            "BAIXA": "baixa",
                        }[str(d.get("nivel_confiaca") or "").upper().strip()],
                        client_id=None,
                        embutir_vetores=True,
                        chunks=chunks_juridicos,
                    )
                    resultados.append((resultado, d["canonical_id"]))
                # Commit ÚNICO: qualquer exceção antes daqui desfaz o lote inteiro.
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        for resultado, canonical_id in resultados:
            print(f"[{resultado}] {canonical_id} | pendente de curadoria")

    try:
        asyncio.run(run())
    except Exception as exc:
        print(f"[FALHA] ingestão transacional abortada: {exc}")
        print(
            "[BLOQUEADO] rollback integral executado; o lote não foi "
            "declarado concluído."
        )
        sys.exit(4)

    print(
        "[ingestão concluída atomicamente: documentos inseridos em estado PENDENTE; "
        "aprovação humana continua obrigatória]"
    )


if __name__ == "__main__":
    main()
