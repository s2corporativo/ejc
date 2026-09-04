"""Chunking jurídico semântico para a base de conhecimento do EJC.

Não substitui o chunker genérico para documentos arbitrários. É usado quando a
natureza jurídica do conteúdo é conhecida (fonte primária, jurisprudência,
tese, argumento, pedido ou modelo), evitando cortes que separem uma conclusão
do respectivo contexto normativo/jurisprudencial.
"""
from __future__ import annotations

import re

from app.core.config import get_settings


def teto_chars_embedding() -> int:
    """Teto de caracteres por chunk derivado da janela do modelo de embeddings
    (config EMBEDDINGS_MAX_CHARS). Piso de 800 para o chunker não degenerar."""
    try:
        return max(800, int(get_settings().EMBEDDINGS_MAX_CHARS or 1800))
    except Exception:  # noqa: BLE001 — config indisponível → default seguro
        return 1800


# C5 (análise E2E de IA 2026-09-03): antes 2.400 chars fixos, acima da janela
# de 512 tokens do e5-large — a cauda do chunk ficava sem vetor. O default agora
# NUNCA excede EMBEDDINGS_MAX_CHARS (teste de invariante em
# tests/test_rag_chunk_janela_modelo.py).
_MAX_DEFAULT = min(2400, teto_chars_embedding())
_MIN_SPLIT = 500

# Categorias RAG cuja natureza jurídica é conhecida: entram pelo chunker
# jurídico (artigo/heading) em vez do corte por tamanho da ingestão.
_PREFIXOS_CATEGORIA_JURIDICA = ("legislacao", "sumula", "jurisprudencia", "doutrina")


def categoria_usa_chunker_juridico(categoria: str | None) -> bool:
    cat = (categoria or "").strip().lower()
    return bool(cat) and cat.startswith(_PREFIXOS_CATEGORIA_JURIDICA)


def chunks_para_ingestao(texto: str, categoria: str | None) -> list[str] | None:
    """Chunks para `ingestion_service.upsert_documento(chunks=...)`.

    Devolve a lista quando a categoria é jurídica (legislacao*, sumula*,
    jurisprudencia*, doutrina) e o chunker produziu algo; senão None — e o
    upsert cai no corte por tamanho (`chunk_texto`). Nunca levanta: qualquer
    falha vira None (fallback). O `hash_conteudo` do documento é calculado
    pelo upsert sobre o CONTEÚDO inteiro normalizado, nunca sobre os chunks —
    trocar a estratégia de chunking não altera a idempotência.
    """
    if not categoria_usa_chunker_juridico(categoria):
        return None
    try:
        chunks = chunk_documento_juridico(texto, categoria=categoria)
    except Exception:  # noqa: BLE001 — fallback para o corte por tamanho
        return None
    return chunks or None


def _normalizar(texto: str) -> str:
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _com_prefixo(texto: str, prefixo: str) -> str:
    prefixo = (prefixo or "").strip()
    if not prefixo or texto.startswith(prefixo):
        return texto
    return f"{prefixo}\n\n{texto}"


def _agrupar_paragrafos(texto: str, max_chars: int, prefixo: str = "") -> list[str]:
    """Agrupa parágrafos sem cortar frases por tamanho quando possível."""
    texto = _normalizar(texto)
    if not texto:
        return []
    if len(texto) <= max_chars:
        return [_com_prefixo(texto, prefixo)]

    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    saida: list[str] = []
    atual = ""
    for par in paragrafos:
        candidato = f"{atual}\n\n{par}".strip() if atual else par
        if len(candidato) <= max_chars:
            atual = candidato
            continue
        if atual:
            saida.append(atual)
            atual = ""
        # Parágrafo excepcionalmente longo: recorta por fronteira de frase.
        resto = par
        while len(resto) > max_chars:
            janela = resto[:max_chars]
            cortes = [janela.rfind(x) for x in (". ", "; ", ": ", "\n")]
            corte = max(cortes)
            if corte < _MIN_SPLIT:
                corte = max_chars
            else:
                corte += 1
            trecho = resto[:corte].strip()
            if trecho:
                saida.append(trecho)
            resto = resto[corte:].strip()
        atual = resto
    if atual:
        saida.append(atual)

    if prefixo:
        return [_com_prefixo(c, prefixo) for c in saida]
    return saida


def _secoes_markdown(texto: str) -> list[tuple[str, str]]:
    """Retorna (cabeçalho, conteúdo), preservando a seção inicial sem heading."""
    linhas = _normalizar(texto).splitlines()
    secoes: list[tuple[str, list[str]]] = []
    cabecalho = ""
    corpo: list[str] = []
    for linha in linhas:
        if re.match(r"^#{1,4}\s+\S", linha):
            if corpo or cabecalho:
                secoes.append((cabecalho, corpo))
            cabecalho = linha.strip()
            corpo = []
        else:
            corpo.append(linha)
    if corpo or cabecalho:
        secoes.append((cabecalho, corpo))
    return [(h, "\n".join(c).strip()) for h, c in secoes if h or "\n".join(c).strip()]


def _chunk_markdown(texto: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    for heading, corpo in _secoes_markdown(texto):
        secao = f"{heading}\n\n{corpo}".strip() if heading else corpo
        if len(secao) <= max_chars:
            if secao:
                chunks.append(secao)
            continue
        # Em seção longa, todo subchunk repete o heading para não perder o contexto.
        # O orçamento do corpo desconta o heading (+ "\n\n") para que o subchunk
        # COM prefixo continue dentro do teto (C5) sem perder o heading.
        orcamento = max(_MIN_SPLIT + 1, max_chars - len(heading) - 2) if heading else max_chars
        chunks.extend(_agrupar_paragrafos(corpo or secao, max_chars=orcamento, prefixo=heading))
    return [c for c in chunks if c.strip()]


def _chunk_legislacao(texto: str, max_chars: int) -> list[str]:
    """Segmenta preferencialmente no início de artigos, mantendo parágrafos/incisos juntos."""
    texto = _normalizar(texto)
    if not texto:
        return []
    # Captura: Art. 14, Artigo 5º, Art. 85-A. Lookahead evita falha de \b após "º".
    marcas = list(re.finditer(
        r"(?im)^(?:art\.?|artigo)\s*\d+[ºo°ª]?(?:-[A-Z])?(?=\s|[.,;:()\-]|$).*$",
        texto,
    ))
    if not marcas:
        return _chunk_markdown(texto, max_chars)

    blocos: list[str] = []
    if marcas[0].start() > 0:
        preambulo = texto[:marcas[0].start()].strip()
        if preambulo:
            blocos.extend(_agrupar_paragrafos(preambulo, max_chars))
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        bloco = texto[m.start():fim].strip()
        blocos.extend(_agrupar_paragrafos(bloco, max_chars))
    return blocos


def chunk_documento_juridico(
    texto: str,
    *,
    tipo_camada: str | None = None,
    categoria: str | None = None,
    max_chars: int = _MAX_DEFAULT,
) -> list[str]:
    """Escolhe estratégia de chunking conforme a natureza jurídica conhecida.

    ``tipo_camada`` é o metadado canônico da Biblioteca Jurídica. ``categoria``
    aceita as categorias RAG existentes, permitindo reutilização fora do lote.
    """
    texto = _normalizar(texto)
    if not texto:
        return []
    # Teto duro = janela do modelo (C5): pedido acima dele é rebaixado.
    max_chars = max(800, min(int(max_chars or _MAX_DEFAULT), teto_chars_embedding()))
    tipo = (tipo_camada or "").strip().lower()
    cat = (categoria or "").strip().lower()

    if tipo == "fonte_primaria" or "legislacao" in cat:
        chunks = _chunk_legislacao(texto, max_chars)
    elif tipo in {
        "jurisprudencia_estruturada", "tese_juridica", "bloco_argumentativo",
        "pedido_juridico", "modelo_peca",
    } or any(x in cat for x in ("jurisprud", "sumula", "tese", "argument", "pedido", "modelo")):
        chunks = _chunk_markdown(texto, max_chars)
    else:
        chunks = _agrupar_paragrafos(texto, max_chars)
    return _garantir_teto(chunks, max_chars)


def _garantir_teto(chunks: list[str], max_chars: int) -> list[str]:
    """Nenhum chunk sai acima de `max_chars`: o prefixo de heading repetido
    pelo chunker de markdown pode empurrar um trecho além do teto — aqui ele é
    re-segmentado por parágrafo/frase (o excedente perde o prefixo, mas ganha
    vetor; o inverso deixava a cauda sem embedding)."""
    saida: list[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            saida.append(c)
            continue
        saida.extend(_agrupar_paragrafos(c, max_chars))
    return saida
