"""Chunking jurídico semântico para a base de conhecimento do EJC.

Não substitui o chunker genérico para documentos arbitrários. É usado quando a
natureza jurídica do conteúdo é conhecida (fonte primária, jurisprudência,
tese, argumento, pedido ou modelo), evitando cortes que separem uma conclusão
do respectivo contexto normativo/jurisprudencial.
"""
from __future__ import annotations

import re


_MAX_DEFAULT = 2400
_MIN_SPLIT = 500


def _normalizar(texto: str) -> str:
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _agrupar_paragrafos(texto: str, max_chars: int, prefixo: str = "") -> list[str]:
    """Agrupa parágrafos sem cortar frases por tamanho quando possível."""
    texto = _normalizar(texto)
    if not texto:
        return []
    if len(texto) <= max_chars:
        return [texto]

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
        prefixo = prefixo.strip()
        return [c if c.startswith(prefixo) else f"{prefixo}\n\n{c}" for c in saida]
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
        chunks.extend(_agrupar_paragrafos(corpo or secao, max_chars=max_chars, prefixo=heading))
    return [c for c in chunks if c.strip()]


def _chunk_legislacao(texto: str, max_chars: int) -> list[str]:
    """Segmenta preferencialmente no início de artigos, mantendo parágrafos/incisos juntos."""
    texto = _normalizar(texto)
    if not texto:
        return []
    # Captura início de artigo em formatos usuais: Art. 14, Artigo 5º, Art. 85-A.
    marcas = list(re.finditer(r"(?im)^(?:art\.?|artigo)\s*\d+[ºo°ª]?(?:-[A-Z])?\b.*$", texto))
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
    max_chars = max(800, int(max_chars or _MAX_DEFAULT))
    tipo = (tipo_camada or "").strip().lower()
    cat = (categoria or "").strip().lower()

    if tipo == "fonte_primaria" or "legislacao" in cat:
        return _chunk_legislacao(texto, max_chars)

    # Jurisprudência, teses, argumentos, pedidos e modelos do Manus são
    # documentos estruturados; heading deve permanecer junto do conteúdo.
    if tipo in {
        "jurisprudencia_estruturada", "tese_juridica", "bloco_argumentativo",
        "pedido_juridico", "modelo_peca",
    } or any(x in cat for x in ("jurisprud", "sumula", "tese", "argument", "pedido", "modelo")):
        return _chunk_markdown(texto, max_chars)

    return _agrupar_paragrafos(texto, max_chars)
