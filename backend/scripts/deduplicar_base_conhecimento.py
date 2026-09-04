#!/usr/bin/env python
# ── scripts/deduplicar_base_conhecimento.py ──────────────────────────────────
# Rebaixa cópias redundantes dos GRANDES TEXTOS LEGAIS na base de conhecimento.
#
# POR QUE ESTE SCRIPT EXISTE
#
# A auditoria de 2026-08-27 mediu a base de produção e encontrou o mesmo texto
# legal ingerido várias vezes por caminhos diferentes:
#
#     Código de Processo Civil ....... 6 cópias (~4.230 trechos)
#     CLT ............................ 4 cópias (~3.449)
#     Código Civil ................... 4 cópias (~3.307)
#     Constituição Federal ........... 4 cópias (~2.966)
#     Código de Processo Penal ....... 2 cópias (~1.393)
#     + "VADE MECUM 2026" (5.103), uma compilação que repete todos os acima
#
# O dedup nativo (`chave_origem` + `versao`/`vigente`, migration 068) não pegou
# nada disso porque ele só age quando a MESMA chave é reingerida. Estas cópias
# entraram por caminhos distintos (upload manual sem fonte × ingestão curada
# com URL oficial), então nunca compartilharam chave.
#
# O PREJUÍZO NÃO É DE ESPAÇO, É DE QUALIDADE DA RESPOSTA JURÍDICA
#
# Quando o RAG busca um artigo do CPC, ele recebe o mesmo artigo seis vezes, e
# as seis ocupam as vagas do contexto enviado ao modelo — empurrando para fora
# a jurisprudência ou a doutrina que completariam a resposta. Duplicata não é
# neutra: ela degrada ativamente o resultado. (Efeito colateral positivo:
# rebaixar as redundantes tira ~21% dos trechos da fila de indexação.)
#
# POR QUE REBAIXAR (`vigente=False`) E NUNCA APAGAR
#
# `vigente` é o mecanismo que o próprio modelo já usa para versão superada
# (ver o comentário em `app/models/rag.py`): o documento sai do retrieval
# (`_FILTRO_VIGENTE_RAG` em `ai_service.py`) e sai da fila de reindexação
# (`_SQL_DOCS_COM_ORFAO`), mas os chunks permanecem intactos. Se uma petição
# já protocolada citou aquela cópia, a citação continua rastreável — exigência
# de auditabilidade num sistema jurídico. E desfazer é um UPDATE.
#
# COMO A CÓPIA VENCEDORA É ESCOLHIDA (`pontuar`)
#
# Em ordem de peso: revisada por humano > tem fonte oficial > veio de ingestão
# estruturada > atualizada mais recentemente > versão maior > mais completa.
# O critério é declarado em código e sai impresso no relatório: nenhuma decisão
# é tomada por heurística oculta.
#
# CONSERVADORISMO DELIBERADO
#
# Só agrupa documentos que casam com um CANÔNICO declarado abaixo — por número
# de lei (sinal mais confiável) ou por apelido explícito. Documento que não
# casa é LISTADO e NUNCA tocado. Isso torna impossível rebaixar por engano um
# texto que ninguém previu. Ampliar a cobertura = acrescentar um CANONICO aqui,
# com revisão de código.
#
# ⚠ PRÉ-REQUISITO antes de `--aplicar`: BACKUP do banco (`scripts/backup.sh`
#   ou o procedimento do RUNBOOK). A execução é ATO HUMANO no VPS.
#
# Execução (container ejc_backend):
#     docker exec -it ejc_backend python -m scripts.deduplicar_base_conhecimento
#     docker exec -it ejc_backend python -m scripts.deduplicar_base_conhecimento --aplicar
#     docker exec -it ejc_backend python -m scripts.deduplicar_base_conhecimento --reverter
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import text

from app.core.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.dedup_conhecimento")

PALAVRA_CONFIRMACAO = "DEDUPLICAR"

# Marca gravada em `extra` para que o rebaixamento seja reconhecível e
# reversível sem depender de log externo.
MARCA_DEDUP = "deduplicado_em"
MARCA_VENCEDOR = "duplicata_de"


@dataclass(frozen=True)
class Canonico:
    """Texto legal cujas cópias podem ser deduplicadas com segurança.

    `numeros` é o sinal forte (número da lei, só dígitos). `aliases` só entra
    quando o título não traz número — "CLT", "Código Civil" avulsos. `excluir`
    impede colisão entre textos de nome parecido: sem ele, "Código de Processo
    Penal Militar" seria agrupado com o CPP comum, e o Militar é outra lei.
    """

    rotulo: str
    numeros: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    excluir: tuple[str, ...] = ()


# Cobertura inicial: os textos que a auditoria encontrou duplicados em
# produção. Acrescentar aqui é a forma de estender o alcance do script.
CANONICOS: tuple[Canonico, ...] = (
    Canonico(
        "Constituição Federal de 1988",
        aliases=("CONSTITUICAO FEDERAL", "CONSTITUICAO DA REPUBLICA",
                 "CONSTITUICAO FEDERAL DE 1988"),
        excluir=("ESTADUAL", "ESTADO DE"),
    ),
    Canonico(
        "Código de Processo Civil (Lei 13.105/2015)",
        numeros=("13105",),
        aliases=("CODIGO DE PROCESSO CIVIL", "CPC"),
        excluir=("PENAL", "1973", "5869"),  # CPC/1973 é outro diploma
    ),
    Canonico(
        "Código Civil (Lei 10.406/2002)",
        numeros=("10406",),
        aliases=("CODIGO CIVIL",),
        excluir=("PROCESSO", "1916", "3071"),  # CC/1916 é outro diploma
    ),
    Canonico(
        "Consolidação das Leis do Trabalho (DL 5.452/1943)",
        numeros=("5452",),
        aliases=("CLT", "CONSOLIDACAO DAS LEIS DO TRABALHO"),
    ),
    Canonico(
        "Código de Processo Penal (DL 3.689/1941)",
        numeros=("3689",),
        aliases=("CODIGO DE PROCESSO PENAL", "CPP"),
        excluir=("MILITAR",),  # CPPM é outra lei
    ),
    Canonico(
        "Código Penal (DL 2.848/1940)",
        numeros=("2848",),
        aliases=("CODIGO PENAL",),
        excluir=("PROCESSO", "MILITAR"),
    ),
    Canonico(
        "Código Tributário Nacional (Lei 5.172/1966)",
        numeros=("5172",),
        aliases=("CODIGO TRIBUTARIO NACIONAL", "CTN"),
    ),
    Canonico(
        "Código de Defesa do Consumidor (Lei 8.078/1990)",
        numeros=("8078",),
        aliases=("CODIGO DE DEFESA DO CONSUMIDOR", "CDC"),
    ),
)


# ── Funções puras (testáveis sem banco) ──────────────────────────────────────

def normalizar(titulo: str) -> str:
    """Título em caixa alta, sem acento e sem pontuação, espaços colapsados.

    Serve só para comparação — o título original nunca é alterado.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", titulo or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", " ", sem_acento.upper()).strip()


def extrair_numeros_lei(titulo: str) -> set[str]:
    """Números de lei presentes no título, só dígitos ("13.105" -> "13105").

    Trabalha sobre o título ORIGINAL, não sobre o normalizado: `normalizar`
    troca ponto e barra por espaço, e aí "13.105/2015" vira "13 105 2015" —
    uma varredura por dígitos coladaria número e ano num "131052015" que não
    casa com nada. O ponto de milhar é justamente o que distingue os dois.

    Ignora 4 dígitos começando em 19/20: são anos ("DE 2015"), e tratá-los como
    número de lei agruparia diplomas distintos só por serem do mesmo ano.
    """
    original = titulo or ""
    numeros: set[str] = set()
    # Formato brasileiro com ponto de milhar: 13.105, 5.452, 10.406
    for bruto in re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", original):
        numeros.add(bruto.replace(".", ""))
    # Mesmo número escrito sem pontuação (13105); anos ficam de fora
    for bruto in re.findall(r"\b\d{4,6}\b", original):
        if not (len(bruto) == 4 and bruto.startswith(("19", "20"))):
            numeros.add(bruto)
    return numeros


def casa_canonico(titulo: str, canonico: Canonico) -> bool:
    """O título identifica este texto legal?

    Número de lei tem prioridade: é o sinal que não depende de como a pessoa
    escreveu o nome. Alias só vale quando NENHUM número aparece no título —
    caso contrário "Lei 9.099" com a palavra "CIVIL" no meio viraria CPC.
    """
    normalizado = normalizar(titulo)
    if any(termo in normalizado for termo in canonico.excluir):
        return False

    numeros = extrair_numeros_lei(titulo)
    if canonico.numeros and numeros & set(canonico.numeros):
        return True
    if numeros:
        return False
    return any(
        alias == normalizado or f" {alias} " in f" {normalizado} "
        for alias in canonico.aliases
    )


def chave_agrupamento(titulo: str) -> str | None:
    """Rótulo do canônico correspondente, ou None quando não há match.

    None significa "não agrupável" — e documento não agrupável JAMAIS é
    rebaixado. É essa a garantia de que o script não age sobre o inesperado.
    """
    for canonico in CANONICOS:
        if casa_canonico(titulo, canonico):
            return canonico.rotulo
    return None


@dataclass(frozen=True)
class DocCandidato:
    """Projeção mínima de knowledge_docs usada na decisão."""

    id: str
    titulo: str
    categoria: str
    tem_fonte: bool
    tem_chave_origem: bool
    revisado: bool
    versao: int
    atualizado_em_ts: float
    n_chunks: int


def pontuar(doc: DocCandidato) -> tuple:
    """Chave de ordenação — MAIOR vence. Critério declarado, não heurística.

    Ordem de peso, do mais para o menos decisivo:
      1. revisado por humano  — alguém conferiu que o texto está correto
      2. tem fonte oficial    — dá para auditar de onde veio
      3. veio de ingestão estruturada (chave_origem)
      4. atualizado mais recentemente
      5. versão maior
      6. mais trechos (texto mais completo)
    """
    return (
        doc.revisado,
        doc.tem_fonte,
        doc.tem_chave_origem,
        doc.atualizado_em_ts,
        doc.versao,
        doc.n_chunks,
    )


def decidir_grupo(docs: list[DocCandidato]) -> tuple[DocCandidato, list[DocCandidato]]:
    """(vencedor, perdedores) — empate resolvido pelo id, para ser determinístico."""
    ordenados = sorted(docs, key=lambda d: (pontuar(d), d.id), reverse=True)
    return ordenados[0], ordenados[1:]


# ── Acesso ao banco ──────────────────────────────────────────────────────────

_SQL_CANDIDATOS = text("""
    SELECT kd.id, kd.titulo, kd.categoria,
           (kd.fonte IS NOT NULL AND kd.fonte <> '') AS tem_fonte,
           (kd.chave_origem IS NOT NULL)             AS tem_chave_origem,
           COALESCE(kd.revisado, false)              AS revisado,
           COALESCE(kd.versao, 1)                    AS versao,
           COALESCE(EXTRACT(EPOCH FROM kd.atualizado_em), 0) AS atualizado_em_ts,
           count(kc.id)                              AS n_chunks
      FROM knowledge_docs kd
      LEFT JOIN knowledge_chunks kc ON kc.doc_id = kd.id
     WHERE kd.deleted_at IS NULL
       AND kd.vigente = true
       AND kd.client_id IS NULL          -- só acervo PÚBLICO; nada de cliente
       AND kd.categoria = 'legislacao'   -- só os grandes textos legais
  GROUP BY kd.id
  ORDER BY kd.id
""")

_SQL_REBAIXAR = text("""
    UPDATE knowledge_docs
       SET vigente = false,
           extra = COALESCE(extra, '{}'::jsonb) || CAST(:marca AS jsonb)
     WHERE id = :id AND vigente = true
""")

_SQL_REVERTER = text("""
    UPDATE knowledge_docs
       SET vigente = true,
           extra = extra - :chave_dedup - :chave_vencedor
     WHERE vigente = false
       AND extra ? :chave_dedup
""")


async def carregar_candidatos(db) -> list[DocCandidato]:
    linhas = (await db.execute(_SQL_CANDIDATOS)).mappings().all()
    return [
        DocCandidato(
            id=l["id"], titulo=l["titulo"], categoria=l["categoria"],
            tem_fonte=bool(l["tem_fonte"]), tem_chave_origem=bool(l["tem_chave_origem"]),
            revisado=bool(l["revisado"]), versao=int(l["versao"]),
            atualizado_em_ts=float(l["atualizado_em_ts"]), n_chunks=int(l["n_chunks"]),
        )
        for l in linhas
    ]


def agrupar(docs: list[DocCandidato]) -> dict[str, list[DocCandidato]]:
    grupos: dict[str, list[DocCandidato]] = {}
    for doc in docs:
        chave = chave_agrupamento(doc.titulo)
        if chave:
            grupos.setdefault(chave, []).append(doc)
    return {k: v for k, v in grupos.items() if len(v) > 1}


async def executar(aplicar: bool) -> int:
    async with AsyncSessionLocal() as db:
        docs = await carregar_candidatos(db)
        grupos = agrupar(docs)

        if not grupos:
            logger.info("Nenhum grupo de duplicatas encontrado entre os canônicos.")
            return 0

        total_rebaixar = 0
        total_chunks = 0
        plano: list[tuple[DocCandidato, DocCandidato]] = []

        for rotulo, membros in sorted(grupos.items()):
            vencedor, perdedores = decidir_grupo(membros)
            logger.info("")
            logger.info("=== %s — %d cópias ===", rotulo, len(membros))
            logger.info("  MANTER   %s  [%s]  fonte=%s revisado=%s chunks=%d",
                        vencedor.id, vencedor.titulo[:58],
                        vencedor.tem_fonte, vencedor.revisado, vencedor.n_chunks)
            for p in perdedores:
                logger.info("  rebaixar %s  [%s]  fonte=%s revisado=%s chunks=%d",
                            p.id, p.titulo[:58], p.tem_fonte, p.revisado, p.n_chunks)
                plano.append((p, vencedor))
                total_rebaixar += 1
                total_chunks += p.n_chunks

        logger.info("")
        logger.info("RESUMO: %d cópias a rebaixar, %d trechos saem do retrieval "
                    "e da fila de indexação.", total_rebaixar, total_chunks)

        if not aplicar:
            logger.info("DRY-RUN — nada foi alterado. Use --aplicar para efetivar.")
            return 0

        confirmacao = input(f'Digite "{PALAVRA_CONFIRMACAO}" para confirmar: ').strip()
        if confirmacao != PALAVRA_CONFIRMACAO:
            logger.warning("Confirmação incorreta — abortado sem alterar nada.")
            return 1

        import json
        from datetime import datetime, timezone

        agora = datetime.now(timezone.utc).isoformat()
        for perdedor, vencedor in plano:
            marca = json.dumps({MARCA_DEDUP: agora, MARCA_VENCEDOR: vencedor.id})
            await db.execute(_SQL_REBAIXAR, {"id": perdedor.id, "marca": marca})
        await db.commit()
        logger.info("Aplicado: %d cópias rebaixadas (vigente=false). "
                    "Nada foi apagado; reverta com --reverter.", total_rebaixar)
        return 0


async def reverter() -> int:
    """Desfaz o rebaixamento — devolve vigente=true a tudo que ESTE script marcou."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(_SQL_REVERTER, {
            "chave_dedup": MARCA_DEDUP, "chave_vencedor": MARCA_VENCEDOR,
        })
        await db.commit()
        logger.info("Revertidas %d cópias para vigente=true.", r.rowcount or 0)
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true",
                    help="efetiva o rebaixamento (exige confirmação digitada)")
    ap.add_argument("--reverter", action="store_true",
                    help="desfaz um rebaixamento anterior deste script")
    args = ap.parse_args()

    if args.reverter and args.aplicar:
        logger.error("--aplicar e --reverter são mutuamente exclusivos.")
        return 2
    if args.reverter:
        return asyncio.run(reverter())
    return asyncio.run(executar(aplicar=args.aplicar))


if __name__ == "__main__":
    raise SystemExit(main())
