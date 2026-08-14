#!/usr/bin/env python3
"""Ingestão programática da Biblioteca Jurídica EJC — Lote Piloto.

Lê os arquivos-fonte canônicos (Markdown com front-matter YAML) produzidos no
lote piloto e insere os documentos na base RAG do EJC por meio da função
existente `upsert_documento` (backend/app/services/ingestion_service.py ou
backend/app/services/rag_service.py conforme a versão do repositório).

Uso:
  python3 ingestao_biblioteca_juridica.py                  # dry-run (validação)
  python3 ingestao_biblioteca_juridica.py --execute         # insere na base
  python3 ingestao_biblioteca_juridica.py --dir /caminho    # diretório raiz do lote

Requisitos de ambiente (só em --execute):
  - Variáveis DATABASE_URL ou acesso ao PostgreSQL do EJC via asyncpg/sqlalchemy
  - Executar a partir do diretório backend do repositório EJC (sys.path)

Validações executadas (sempre, inclusive em dry-run):
  - Front-matter YAML sintático e completo (todas as chaves canônicas)
  - Unicidade de canonical_id no lote
  - score_autoridade entre 0 e 100; nivel_confiaca em {ALTA, MEDIA, BAIXA}
  - area_juridica no vocabulário canônico
  - Ausência de padrões de jurisprudência inventada (heurística simples)
"""
import argparse
import os
import re
import sys
import unicodedata

import yaml

ROOT_AREA = ["tributario", "ambiental", "administrativo", "licitacoes",
             "empresarial", "consumidor_bancario", "trabalhista_empresarial",
             "processual_civil"]
AREA_VOCAB = set(ROOT_AREA)
TIPO_VOCAB = {"tese_juridica", "jurisprudencia_estruturada", "bloco_argumentativo",
              "pedido_juridico", "modelo_peca", "fonte_primaria"}
CATEGORIA_RAG = {
    "tese_juridica": "tese_juridica",
    "jurisprudencia_estruturada": "jurisprudencia_stj",  # mapear conforme tribunal no ingest real
    "bloco_argumentativo": "bloco_argumentativo",
    "pedido_juridico": "pedido_juridico",
    "modelo_peca": "modelo_documento_juridico",
    "fonte_primaria": "legislacao_tributaria",
}
CONF_VOCAB = {"ALTA", "MEDIA", "BAIXA"}

# Heurística anti-alucinação: seções de jurisprudência citam número de processo
# mas não citam tribunal/fonte — sinal de dado órfão. Verificação mínima.
TRIBUNAL_PAT = re.compile(r"\b(STF|STJ|TCU|TJMG|TST|TSE|TRF|TJ[- ][A-Z]{2})\b")
PROCESSO_PAT = re.compile(r"\b\d{7}\s*[-\.]\s*\d{2}\b|\b\d{1,2}\.\d{3,4}\.\d{3,4}[^\s]{0,12}\b|\b(REsp|RE|EREsp|ARE|AgInt|Tema|Súmula)\s*\d{1,3}[.,]?\s*\d{3,6}")


def strip_frontmatter(text: str):
    m = re.match(r"^---\n(.*?)(?:\n---|---)\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    return dict(yaml.safe_load(m.group(1)) or {}), m.group(2)


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
                docs.append(meta)
    return docs


def validar(docs):
    erros = []
    ids = set()
    for d in docs:
        path = d.get("__file", "?")
        # chaves obrigatórias
        for k in ("tipo_camada", "canonical_id", "origem_conteudo",
                  "autoridade_juridica", "score_autoridade", "area_juridica",
                  "nivel_confiaca", "data_pesquisa"):
            if k not in d or not str(d.get(k, "")).strip():
                erros.append(f"[{path}] chave obrigatória ausente: {k}")
        if d.get("tipo_camada") not in TIPO_VOCAB:
            erros.append(f"[{path}] tipo_camada fora do vocabulário: {d.get('tipo_camada')}")
        if d.get("area_juridica") not in AREA_VOCAB:
            erros.append(f"[{path}] area_juridica fora do vocabulário: {d.get('area_juridica')}")
        try:
            sc = int(d.get("score_autoridade", -1))
        except (TypeError, ValueError):
            erros.append(f"[{path}] score_autoridade não numérico")
            sc = -1
        if not (0 <= sc <= 100):
            erros.append(f"[{path}] score_autoridade fora de 0-100: {d.get('score_autoridade')}")
        nc = str(d.get("nivel_confiaca", "")).upper().strip()
        if nc not in CONF_VOCAB:
            erros.append(f"[{path}] nivel_confiaca fora de {CONF_VOCAB}: {d.get('nivel_confiaca')}")
        cid = d.get("canonical_id")
        if cid in ids:
            erros.append(f"[{path}] canonical_id duplicado: {cid}")
        ids.add(cid)
        # heurística anti-alucinação: corpo cita processos sem tribunal?
        body = d.get("__body", "")
        if PROCESSO_PAT.search(body) and not TRIBUNAL_PAT.search(body):
            erros.append(f"[{path}] aviso: processos citados sem tribunal identificado")
    return erros


def build_extra(d):
    """Monta o JSONB extra canônico para o upsert do EJC."""
    extra = {
        "tipo_camada": d["tipo_camada"],
        "canonical_id": d["canonical_id"],
        "origem_conteudo": d["origem_conteudo"],
        "autoridade_juridica": d["autoridade_juridica"],
        "authority_level": d.get("authority_level", "jurisprudencia_oficial"),
        "score_autoridade": int(d["score_autoridade"]),
        "area_juridica": d["area_juridica"],
        "nivel_confiaca": str(d["nivel_confiaca"]).upper(),
        "data_pesquisa": d["data_pesquisa"],
        "gerado_por_IA": bool(d.get("gerado_por_IA")),
        "fontes_utilizadas": d.get("fontes_utilizadas") or [],
    }
    for k in ("tribunal", "orgao_julgador", "numero_processo", "relator",
              "data_julgamento", "ementa", "tese_adotada", "resultado",
              "posicao_estrategica", "legal_status", "link_official",
              "last_verified_at"):
        if d.get(k):
            extra[k] = d[k]
    return extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Executa a ingestão real")
    ap.add_argument("--dir", default=None, help="Diretório raiz do lote (autodetectado se omitido)")
    args = ap.parse_args()

    base = args.dir or ("/lote_piloto" if os.path.isdir("/lote_piloto") else "/home/ubuntu/lote_piloto")
    docs = load_piloto(base)
    print(f"[{len(docs)} documentos carregados de {base}]")

    erros = validar(docs)
    for e in erros:
        print("ERRO:", e)
    if erros:
        print(f"[{sum(1 for e in erros if e.startswith('['))} problemas detectados — revisão necessária antes de --execute]")
    else:
        print("[validação OK: metadados canônicos completos, IDs únicos, sem padrão de jurisprudência órfã]")

    if not args.execute:
        print("\n[DRY-RUN] Nenhuma inserção realizada. Para ingerir na base do EJC:")
        for d in sorted(docs, key=lambda x: x["canonical_id"]):
            categoria = CATEGORIA_RAG.get(d["tipo_camada"], "tese_juridica")
            print(f"  ingest {d['canonical_id']} | categoria={categoria} | {d['__file']}")
        return

    # Modo execução: depende do ambiente do EJC (sys.path do backend).
    # Caminho resolvido em runtime: funciona tanto no sandbox (/home/ubuntu/ejc/backend)
    # quanto na VPS/container do EJC (/opt/ejc/backend ou /app).
    _cand = ["/app", "/opt/ejc/backend", "/home/ubuntu/ejc/backend"]
    for _c in _cand:
        if os.path.isdir(_c) and os.path.isdir(os.path.join(_c, "app")):
            sys.path.insert(0, _c)
            break
    try:
        from app.services.ingestion_service import upsert_documento
    except Exception as exc2:  # noqa: BLE001
        print(f"[FALHA] Não foi possível importar upsert_documento: {exc2}")
        sys.exit(2)

    import asyncio

    async def run():
        from app.core.database import AsyncSessionLocal
        for d in docs:
            extra = build_extra(d)
            titulo = (d.get("__body") or "").split("\n")[0].lstrip("#").strip() or d["canonical_id"]
            categoria = CATEGORIA_RAG.get(d["tipo_camada"], "tese_juridica")
            async with AsyncSessionLocal() as db:
                try:
                    resultado = await upsert_documento(
                        db,
                        chave_origem=d["canonical_id"],
                        titulo=titulo,
                        categoria=categoria,
                        conteudo=d["__body"],
                        extra=extra,
                        confianca="alta" if d.get("nivel_confiaca") == "ALTA" else "media",
                        client_id=None,  # base publica do escritório (globalmente única)
                        embutir_vetores=True,
                    )
                    await db.commit()
                    print(f"[{resultado}] {d['canonical_id']}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[ERRO] {d['canonical_id']}: {exc}")

    asyncio.run(run())
    print("[ingestão concluída]")


if __name__ == "__main__":
    main()
