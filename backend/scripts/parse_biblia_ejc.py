"""scripts/parse_biblia_ejc.py — parser da "Bíblia de Conhecimento EJC" para o corpus RAG.

Transforma os parágrafos extraídos do DOCX (lista JSON de pares [estilo, texto],
gerada offline a partir de "Bíblia de Conhecimento EJC — Edição Integral v2")
no corpus tratado e versionado em seeds/biblia_ejc/*.jsonl, pronto para o
seed_biblia_ejc.py ingerir via upsert_documento.

IMPORTANTE (governança de IA): todo o material é FICTÍCIO, criado para
treinamento e RAG — o próprio documento avisa que as situações e modelos não
são casos reais nem jurisprudência real. O parser marca cada documento com
extra["ficticio"]=True e prepõe um aviso no conteúdo, para que a IA use o
material apenas como referência metodológica, nunca como fonte citável de
caso/jurisprudência.

Estrutura reconhecida:
  PARTE A — Banco de Situações Jurídicas
    Heading1  = áreas do direito ("1. DIREITO CIVIL — ...") e seções especiais
                (AVISO FUNDAMENTAL, INTRODUÇÃO METODOLÓGICA, NOTAS FINAIS,
                "... VOLUME II" marca a troca de volume)
    Heading2  = situações "SIT-NN — <título> (Rotineira|Complexa|Atípica[...])"
  PARTE B — Biblioteca Jurídica (modelos, auditoria e integração)
    Heading2  = documentos de governança (B.2 mapa, Relatório de Auditoria,
                Índice Mestre, Padrão de Integração) e "Volume N — ..." de modelos
    Heading3  = cada modelo/seção dentro de um volume

Saída: 1 documento RAG por situação (SIT), por instrução de uso e por
modelo/seção da Parte B, com chave_origem estável ("biblia_ejc:<slug>") para
dedup/versionamento idempotentes.

Uso (a partir de backend/):
    python scripts/parse_biblia_ejc.py <biblia_paras.json> [--out-dir seeds/biblia_ejc]
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

# Identidade do corpus (usada também pelo seed e exibida no painel Conhecimento)
FONTE_BIBLIA = "biblia_ejc"
ORIGEM = "Bíblia de Conhecimento EJC — Edição Integral v2"

# Categorias compatíveis com a busca RAG (ai_service). Nenhuma delas integra
# _RESTRICTED_CATS nem os filtros de jurisprudência/súmula — o material NUNCA
# aparece quando a IA busca especificamente jurisprudência/precedente real.
CATEGORIA_REFERENCIA = "referencia_interna"          # situações + instruções + governança
CATEGORIA_MODELO = "modelo_documento_juridico"       # modelos de peça da Parte B

# Aviso prepend em TODO documento (governança): o 1º chunk sempre carrega o
# alerta; os metadados (extra.ficticio) cobrem os demais chunks.
AVISO_FICTICIO = (
    "[MATERIAL DIDÁTICO FICTÍCIO — Bíblia de Conhecimento EJC v2] "
    "Conteúdo criado para treinamento e RAG. NÃO se trata de caso real, "
    "jurisprudência real nem peça protocolada — usar apenas como referência "
    "metodológica. Citações legais devem ser conferidas na fonte oficial e "
    "toda peça derivada exige revisão e assinatura de advogado(a) responsável."
)

_HEADING_STYLES = {"Heading1", "Heading2", "Heading3", "Heading4", "Heading5"}

# "SIT-01 — Título (Rotineira)" — tolera travessão/hífen e qualificadores no
# parêntese, ex.: "(Atípica — tese controvertida)".
_SIT_RE = re.compile(
    r"^SIT-(\d+)\s*[—–-]\s*(.+?)\s*\(\s*(Rotineira|Complexa|Atípica)([^)]*)\)\s*$"
)
_AREA_RE = re.compile(r"^(\d+)\.\s+(.+?)\s*(?:\(ampliação\))?\s*$", re.IGNORECASE)
# Heading3 de modelo na Parte B: "01 — DIREITO CIVIL: ..." / "28 - MANIFESTAÇÃO ..."
_MODELO_H3_RE = re.compile(r"^\d{1,2}\s*[—–-]\s+\S")
_VOLUME_B_RE = re.compile(r"^Volume\s+([IVX]+)\s*[—–-]\s*(.+)$")


def limpar_texto(texto: str) -> str:
    """Normaliza um parágrafo: espaços não separáveis, zero-width, controles."""
    if not texto:
        return ""
    texto = texto.replace(" ", " ").replace("​", "").replace("﻿", "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Cc" or c in "\n\t")
    return re.sub(r"[ \t]+", " ", texto).strip()


def slugify(texto: str, max_len: int = 70) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:max_len].rstrip("-")


class _Secao:
    """Acumulador de uma seção (vira 1 documento RAG)."""

    def __init__(self, chave: str, titulo: str, categoria: str, extra: dict[str, Any]):
        self.chave = chave
        self.titulo = titulo
        self.categoria = categoria
        self.extra = extra
        self.linhas: list[str] = []
        self.primeiro_subtitulo: str | None = None

    def add(self, estilo: str, texto: str) -> None:
        texto = limpar_texto(texto)
        if not texto:
            return
        if estilo in _HEADING_STYLES:
            if self.primeiro_subtitulo is None:
                self.primeiro_subtitulo = texto
            # Subtítulo interno como linha destacada (estrutura preservada em texto limpo)
            self.linhas.append(f"\n{texto}\n")
        else:
            self.linhas.append(texto)

    def doc(self) -> dict[str, Any] | None:
        corpo = "\n\n".join(self.linhas).strip()
        if len(corpo) < 50:   # seção vazia/cover — não vira documento
            return None
        titulo = self.titulo
        # Vol. I/II repetem o mesmo tema como "MODELO A — PEÇA INICIAL" e
        # "MODELO B — DEFESA CORRESPONDENTE"; o 1º subtítulo desambigua.
        if (self.extra.get("tipo") == "modelo" and self.primeiro_subtitulo
                and self.primeiro_subtitulo.upper().startswith("MODELO ")):
            titulo = f"{titulo} ({self.primeiro_subtitulo})"
        conteudo = f"{AVISO_FICTICIO}\n\n{titulo}\n\n{corpo}"
        return {
            "chave_origem": f"{FONTE_BIBLIA}:{self.chave}",
            "titulo": titulo[:500],
            "categoria": self.categoria,
            "conteudo": conteudo,
            "extra": {"ficticio": True, "origem": ORIGEM, **self.extra},
        }


def _extra_base(parte: str, tipo: str, **kw: Any) -> dict[str, Any]:
    return {"parte": parte, "tipo": tipo, **{k: v for k, v in kw.items() if v}}


def parse_biblia(paras: list[list[str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse estruturado do documento inteiro.

    Retorna (documentos, estatísticas). Puro (sem I/O) — testável em unidade.
    """
    docs: list[dict[str, Any]] = []
    stats: Counter = Counter()
    chaves_vistas: set[str] = set()

    def fechar(sec: _Secao | None) -> None:
        if sec is None:
            return
        d = sec.doc()
        if d is None:
            stats["secoes_vazias_descartadas"] += 1
            return
        # chave única: sufixo -2, -3... para títulos repetidos (ex.: MODELO A/B).
        # ATENÇÃO — os sufixos são POSICIONAIS (ordem de aparição no DOCX):
        # reordenar/inserir/remover seções de mesmo título desloca as chaves
        # (-2 vira -3 etc.); como o seed deduplica por chave_origem, isso NÃO
        # duplica, mas cria VERSÕES novas dos docs cujas chaves mudaram (e as
        # versões antigas ficam no histórico). Ver seeds/biblia_ejc/README.md.
        chave = d["chave_origem"]
        n = 2
        while d["chave_origem"] in chaves_vistas:
            d["chave_origem"] = f"{chave}-{n}"
            n += 1
        chaves_vistas.add(d["chave_origem"])
        docs.append(d)

    # ── PARTE A ───────────────────────────────────────────────────────────
    idx_parte_b = next(
        (i for i, (s, t) in enumerate(paras)
         if s == "Heading1" and limpar_texto(t).upper().startswith("PARTE B")),
        len(paras),
    )

    volume = "I"
    area: str | None = None
    sec: _Secao | None = None
    especiais_vistos: Counter = Counter()

    for estilo, texto in paras[:idx_parte_b]:
        t = limpar_texto(texto)
        if not t:
            continue
        if estilo == "Heading1":
            fechar(sec)
            sec = None
            up = t.upper()
            m_area = _AREA_RE.match(t)
            if m_area:
                area = m_area.group(2).strip()
                continue
            especial = None
            if up.startswith("AVISO FUNDAMENTAL"):
                especial = "aviso-fundamental"
            elif up.startswith("INTRODUÇÃO METODOLÓGICA"):
                especial = "introducao-metodologica"
            elif up.startswith("NOTAS FINAIS"):
                especial = "notas-finais"
            elif "VOLUME II" in up:   # capa "BÍBLIA ... — VOLUME II" → troca de volume
                volume = "II"
                continue
            if especial:
                especiais_vistos[especial] += 1
                sufixo = "" if especiais_vistos[especial] == 1 else f"-vol{volume.lower()}"
                sec = _Secao(
                    chave=f"{especial}{sufixo}",
                    titulo=f"Bíblia EJC — {t} (Volume {volume})",
                    categoria=CATEGORIA_REFERENCIA,
                    extra=_extra_base("A", "instrucao_uso", volume=volume),
                )
                stats["instrucoes"] += 1
            # demais Heading1 (capa, "PARTE A ...") → apenas contexto
            continue
        if estilo == "Heading2":
            m = _SIT_RE.match(t)
            if m:
                fechar(sec)
                num = int(m.group(1))
                complexidade = m.group(3)
                sec = _Secao(
                    chave=f"sit-{num:02d}",
                    titulo=f"Bíblia EJC (fictício) — {t}",
                    categoria=CATEGORIA_REFERENCIA,
                    extra=_extra_base(
                        "A", "situacao", sit=f"SIT-{num:02d}", area=area,
                        complexidade=complexidade, volume=volume,
                    ),
                )
                stats["situacoes"] += 1
                continue
            # Heading2 não-SIT: subtítulo dentro da seção corrente (ou capa)
        if sec is not None:
            sec.add(estilo, t)
        else:
            stats["paragrafos_fora_de_secao"] += 1
    fechar(sec)
    sec = None

    # ── PARTE B ───────────────────────────────────────────────────────────
    vol_b: str | None = None
    vol_b_titulo = ""
    seq_modelo = 0

    for estilo, texto in paras[idx_parte_b:]:
        t = limpar_texto(texto)
        if not t:
            continue
        if estilo == "Heading1":  # "PARTE B — ..." (título da parte)
            fechar(sec)
            sec = None
            continue
        if estilo == "Heading2":
            fechar(sec)
            sec = None
            m_vol = _VOLUME_B_RE.match(t)
            if m_vol:
                vol_b, vol_b_titulo = m_vol.group(1), m_vol.group(2).strip()
                seq_modelo = 0
                sec = _Secao(  # preâmbulo do volume (avisos, checklist, matriz)
                    chave=f"b1-vol{vol_b.lower()}-preambulo",
                    titulo=f"Bíblia EJC — Modelos Vol. {vol_b} ({vol_b_titulo}) — avisos e instruções",
                    categoria=CATEGORIA_REFERENCIA,
                    extra=_extra_base("B", "governanca", volume=f"Modelos {vol_b}"),
                )
                stats["governanca"] += 1
                continue
            up = t.upper()
            if up.startswith(("B.0", "B.1")):
                continue   # cabeçalhos-contêiner sem conteúdo próprio
            vol_b = None
            sec = _Secao(   # B.2 mapa / Relatório de Auditoria / Índice Mestre / Padrão de Integração
                chave=f"b0-{slugify(t)}",
                titulo=f"Bíblia EJC — {t}",
                categoria=CATEGORIA_REFERENCIA,
                extra=_extra_base("B", "governanca"),
            )
            stats["governanca"] += 1
            continue
        if estilo == "Heading3" and vol_b is not None:
            fechar(sec)
            if _MODELO_H3_RE.match(t):
                seq_modelo += 1
                sec = _Secao(
                    chave=f"b1-vol{vol_b.lower()}-{seq_modelo:02d}-{slugify(t, 50)}",
                    titulo=f"Bíblia EJC (fictício) — Modelo Vol. {vol_b} — {t}",
                    categoria=CATEGORIA_MODELO,
                    extra=_extra_base("B", "modelo", volume=f"Modelos {vol_b}",
                                      tema=t[:200]),
                )
                stats["modelos"] += 1
            else:   # apêndices/instruções do volume
                sec = _Secao(
                    chave=f"b1-vol{vol_b.lower()}-{slugify(t, 50)}",
                    titulo=f"Bíblia EJC — Modelos Vol. {vol_b} — {t}",
                    categoria=CATEGORIA_REFERENCIA,
                    extra=_extra_base("B", "governanca", volume=f"Modelos {vol_b}"),
                )
                stats["governanca"] += 1
            continue
        if sec is not None:
            sec.add(estilo, t)
        else:
            stats["paragrafos_fora_de_secao"] += 1
    fechar(sec)

    stats["total_docs"] = len(docs)
    return docs, dict(stats)


# Arquivo de saída por tipo (diffs legíveis; modelos são o grosso do corpus)
_ARQUIVO_POR_TIPO = {
    "situacao": "situacoes.jsonl",
    "instrucao_uso": "instrucoes.jsonl",
    "governanca": "governanca.jsonl",
    "modelo": "modelos.jsonl",
}


def escrever_corpus(docs: list[dict[str, Any]], out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    grupos: dict[str, list[dict]] = {}
    for d in docs:
        nome = _ARQUIVO_POR_TIPO[d["extra"]["tipo"]]
        grupos.setdefault(nome, []).append(d)
    contagens: dict[str, int] = {}
    for nome, itens in sorted(grupos.items()):
        caminho = out_dir / nome
        with caminho.open("w", encoding="utf-8") as f:
            for d in itens:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        contagens[nome] = len(itens)
    return contagens


def main() -> None:
    parser = argparse.ArgumentParser(description="Parser da Bíblia EJC → corpus JSONL")
    parser.add_argument("paras_json", help="JSON com lista de pares [estilo, texto]")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "seeds" / "biblia_ejc"))
    args = parser.parse_args()

    paras = json.loads(Path(args.paras_json).read_text(encoding="utf-8"))
    docs, stats = parse_biblia(paras)
    contagens = escrever_corpus(docs, Path(args.out_dir))

    print(f"[parse-biblia] estatísticas: {stats}")
    for nome, n in contagens.items():
        print(f"  {nome}: {n} documentos")
    # Distribuição por área/volume das situações (validação rápida)
    por_area: Counter = Counter()
    tamanhos: list[int] = []
    for d in docs:
        tamanhos.append(len(d["conteudo"]))
        if d["extra"]["tipo"] == "situacao":
            por_area[f"Vol.{d['extra'].get('volume')} — {d['extra'].get('area')}"] += 1
    print("[parse-biblia] situações por volume/área:")
    for k, v in sorted(por_area.items()):
        print(f"  {k}: {v}")
    print(f"[parse-biblia] tamanho médio dos docs: {sum(tamanhos)//max(len(tamanhos),1)} chars; "
          f"total: {sum(tamanhos)} chars em {len(docs)} docs")


if __name__ == "__main__":
    main()
