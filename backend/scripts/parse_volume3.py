"""scripts/parse_volume3.py — conversor do "Compêndio de Modelos Processuais Volume III".

Transforma o DOCX "COMPÊNDIO DE MODELOS PROCESSUAIS — VOLUME III" (48 modelos
editáveis em 24 pares peça-de-iniciativa + reação, nas áreas bancário,
consumidor, empresarial, licitações/contratos administrativos, trabalhista
empresarial e ambiental) em documentos RAG no MESMO formato do corpus da
"Bíblia de Conhecimento EJC" (scripts/parse_biblia_ejc.py), gravando
seeds/biblia_ejc/modelos_vol3.jsonl para o seed_biblia_ejc.py ingerir via
ingestion_service.upsert_documento.

Governança (idêntica à Bíblia v2): todo o material é FICTÍCIO/DIDÁTICO — cada
documento leva extra["ficticio"]=True e o mesmo aviso (AVISO_FICTICIO) no início
do conteúdo, e usa a categoria "modelo_documento_juridico", que nunca entra nos
filtros de jurisprudência/súmula da busca RAG.

Estrutura reconhecida (python-docx, na ordem do corpo, incluindo tabelas):
  Heading 1 "5. MODELOS"                → início da seção de modelos
  Heading 1 "NN - <TÍTULO>"             → um modelo (NN = 01..48)
  Heading 1 "APÊNDICE ..."              → fim da seção de modelos
  Heading 2 "PARTE X - <ÁREA>" (sumário)→ mapeia número do modelo → área
  Tabelas (ficha de adaptação, matriz tese–prova) → texto achatado no conteúdo

Convenção do par: número ÍMPAR = peça de INICIATIVA, número PAR = REAÇÃO
(contestação/recurso/contrarrazões/resposta) — os 48 modelos formam 24 pares.

Uso (a partir de backend/):
    python scripts/parse_volume3.py <Volume_III.docx> [--out-dir seeds/biblia_ejc]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

# backend/ no sys.path quando rodado como script avulso (reuso das constantes/
# helpers de governança do parser da Bíblia — mesma identidade de corpus).
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from scripts.parse_biblia_ejc import (  # noqa: E402
    AVISO_FICTICIO,
    CATEGORIA_MODELO,
    limpar_texto,
    slugify,
)

ORIGEM = "Compêndio de Modelos Processuais Volume III"
VOLUME = "Modelos III"

# "NN - Título" (Heading 1 de cada modelo); tolera hífen/travessão.
_MODELO_H1_RE = re.compile(r"^(\d{2})\s*[—–-]\s*(.+)$")
# "PARTE I - DIREITO BANCÁRIO" (Heading 2 no sumário) → captura a área.
_PARTE_RE = re.compile(r"^PARTE\s+[IVX]+\s*[—–-]\s*(.+)$", re.IGNORECASE)
# "01. AÇÃO ..." (linha do sumário que vincula número → área corrente).
_SUMARIO_ITEM_RE = re.compile(r"^(\d{2})[.\-—–]")


def _titulo_area(bruto: str) -> str:
    """"DIREITO BANCÁRIO" → "Direito Bancário" (title-case preservando siglas curtas)."""
    palavras = limpar_texto(bruto).split()
    saida = []
    for p in palavras:
        if len(p) <= 2 or (p.isupper() and not p.isalpha()):
            saida.append(p.lower() if p.lower() in {"e", "de", "do", "da", "por"} else p)
        else:
            saida.append(p.capitalize())
    return " ".join(saida)


def _iter_blocos(caminho: Path) -> list[tuple[str, str]]:
    """Percorre o corpo do DOCX na ordem real, achatando tabelas.

    Retorna lista de (estilo, texto). Tabelas viram estilo "__table__" com as
    linhas achatadas (célula | célula), para não perder ficha de adaptação e
    matriz tese–prova (que são tabelas, invisíveis a document.paragraphs)."""
    import docx  # dependência só do conversor (offline), não do runtime do app
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(caminho))
    blocos: list[tuple[str, str]] = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            par = Paragraph(child, doc)
            texto = limpar_texto(par.text)
            if texto:
                blocos.append((par.style.name or "Normal", texto))
        elif child.tag == qn("w:tbl"):
            tbl = Table(child, doc)
            linhas: list[str] = []
            for row in tbl.rows:
                celulas = [limpar_texto(c.text) for c in row.cells]
                # remove duplicatas horizontais (células mescladas repetem texto)
                dedup: list[str] = []
                for cel in celulas:
                    if cel and (not dedup or dedup[-1] != cel):
                        dedup.append(cel)
                if dedup:
                    linhas.append(" | ".join(dedup))
            if linhas:
                blocos.append(("__table__", "\n".join(linhas)))
    return blocos


def _mapa_areas(blocos: list[tuple[str, str]]) -> dict[str, str]:
    """Do sumário ("3. SUMÁRIO DOS MODELOS"..."4. ...") deriva número → área."""
    mapa: dict[str, str] = {}
    area_atual: str | None = None
    dentro = False
    for estilo, texto in blocos:
        if estilo.startswith("Heading 1"):
            up = texto.upper()
            if "SUMÁRIO DOS MODELOS" in up or "SUMARIO DOS MODELOS" in up:
                dentro = True
                continue
            if dentro:  # próximo Heading 1 encerra o sumário
                break
        if not dentro:
            continue
        m_parte = _PARTE_RE.match(texto)
        if m_parte:
            area_atual = _titulo_area(m_parte.group(1))
            continue
        m_item = _SUMARIO_ITEM_RE.match(texto)
        if m_item and area_atual:
            mapa[m_item.group(1)] = area_atual
    return mapa


def _bloco_para_linhas(estilo: str, texto: str) -> list[str]:
    """Formata um bloco para o corpo do documento (estrutura preservada)."""
    if estilo == "__table__":
        return [texto]
    if estilo.startswith(("Heading 2", "Heading 3", "Heading 4")):
        return [f"\n{texto}\n"]      # subtítulo interno destacado
    if estilo.startswith("List Bullet"):
        return [f"- {texto}"]
    return [texto]


def parse_volume3(blocos: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Segmenta os 48 modelos. Puro (recebe blocos já extraídos) — testável."""
    docs: list[dict[str, Any]] = []
    stats: Counter = Counter()
    chaves_vistas: set[str] = set()
    mapa_areas = _mapa_areas(blocos)

    # Delimita a seção "5. MODELOS" .. primeiro "APÊNDICE".
    inicio = fim = None
    for i, (estilo, texto) in enumerate(blocos):
        if estilo.startswith("Heading 1"):
            up = texto.upper()
            if inicio is None and up.startswith("5.") and "MODELOS" in up:
                inicio = i
            elif inicio is not None and up.startswith("APÊNDICE"):
                fim = i
                break
    if inicio is None:
        raise SystemExit("[parse-vol3] seção '5. MODELOS' não encontrada no DOCX")
    if fim is None:
        fim = len(blocos)

    def fechar(num: str, titulo_bruto: str, corpo_blocos: list[tuple[str, str]]) -> None:
        linhas: list[str] = []
        for est, txt in corpo_blocos:
            linhas.extend(_bloco_para_linhas(est, txt))
        corpo = "\n\n".join(linhas).strip()
        if len(corpo) < 50:
            stats["modelos_vazios_descartados"] += 1
            return
        tema = titulo_bruto.strip()
        area = mapa_areas.get(num, "Direito (área não classificada)")
        iniciativa = "INICIATIVA" if int(num) % 2 == 1 else "REAÇÃO"
        titulo = (
            f"Bíblia EJC (fictício) — Modelo Vol. III — {num} — "
            f"{area}: {tema} ({iniciativa})"
        )[:500]
        chave = f"biblia_ejc:vol3:{num}-{slugify(tema, 55)}"
        base = chave
        n = 2
        while chave in chaves_vistas:
            chave = f"{base}-{n}"
            n += 1
        chaves_vistas.add(chave)
        conteudo = f"{AVISO_FICTICIO}\n\n{titulo}\n\n{corpo}"
        docs.append({
            "chave_origem": chave[:255],
            "titulo": titulo,
            "categoria": CATEGORIA_MODELO,
            "conteudo": conteudo,
            "extra": {
                "ficticio": True,
                "origem": ORIGEM,
                "parte": "B",
                "tipo": "modelo",
                "volume": VOLUME,
                "area": area,
                "tema": tema[:200],
                "iniciativa": iniciativa,
                "numero": num,
            },
        })
        stats["modelos"] += 1

    num_atual: str | None = None
    titulo_atual = ""
    corpo_atual: list[tuple[str, str]] = []
    for estilo, texto in blocos[inicio + 1:fim]:
        if estilo.startswith("Heading 1"):
            m = _MODELO_H1_RE.match(texto)
            if m:
                if num_atual is not None:
                    fechar(num_atual, titulo_atual, corpo_atual)
                num_atual, titulo_atual = m.group(1), m.group(2).strip()
                corpo_atual = []
                continue
        if num_atual is not None:
            corpo_atual.append((estilo, texto))
    if num_atual is not None:
        fechar(num_atual, titulo_atual, corpo_atual)

    stats["total_docs"] = len(docs)
    stats["areas_distintas"] = len(set(mapa_areas.values()))
    return docs, dict(stats)


def escrever(docs: list[dict[str, Any]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    caminho = out_dir / "modelos_vol3.jsonl"
    with caminho.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return caminho


def main() -> None:
    parser = argparse.ArgumentParser(description="Conversor do Volume III → corpus JSONL")
    parser.add_argument("docx", help="caminho do DOCX do Compêndio Volume III")
    parser.add_argument(
        "--out-dir",
        default=str(_BACKEND / "seeds" / "biblia_ejc"),
    )
    args = parser.parse_args()

    blocos = _iter_blocos(Path(args.docx))
    docs, stats = parse_volume3(blocos)
    caminho = escrever(docs, Path(args.out_dir))

    print(f"[parse-vol3] estatísticas: {stats}")
    print(f"[parse-vol3] gravado: {caminho} ({len(docs)} modelos)")
    por_area: Counter = Counter()
    tamanhos: list[int] = []
    for d in docs:
        por_area[d["extra"]["area"]] += 1
        tamanhos.append(len(d["conteudo"]))
    print("[parse-vol3] modelos por área:")
    for k, v in sorted(por_area.items()):
        print(f"  {k}: {v}")
    if tamanhos:
        print(f"[parse-vol3] tamanho: min={min(tamanhos)} médio={sum(tamanhos)//len(tamanhos)} "
              f"max={max(tamanhos)} chars")


if __name__ == "__main__":
    main()
