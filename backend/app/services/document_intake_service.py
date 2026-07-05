# ── app/services/document_intake_service.py ──────────────────────────────────
"""Intake documental jurídico.

Este módulo prepara documentos importados para análise estratégica por IA sem
perder o miolo/final do arquivo. O objetivo não é apenas resumir: é montar um
DOSSIÊ documental para que o Núcleo de IA atue como advogado sênior, com fatos,
partes, pedidos, provas, prazos, riscos e lacunas rastreáveis.

Fase 1 (segura e determinística):
- divide documento longo em chunks jurídicos;
- extrai sinais estruturais por regex/parser local;
- seleciona trechos juridicamente relevantes de todo o documento;
- monta um contexto compacto preservando início, meio e fim;
- evita o antigo padrão de analisar somente os primeiros 4.000 caracteres.
"""
from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, Field


CHUNK_SIZE = 6_000
CHUNK_OVERLAP = 450
MAX_DOSSIE_CHARS = 18_000
MAX_SINAIS = 20


class DocumentoChunk(BaseModel):
    """Trecho textual com posição de origem no documento OCR."""

    indice: int
    inicio: int
    fim: int
    texto: str


class SinaisDocumento(BaseModel):
    """Sinais determinísticos extraídos localmente antes da IA."""

    numeros_processo: list[str] = Field(default_factory=list)
    cpfs: list[str] = Field(default_factory=list)
    cnpjs: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    valores_monetarios: list[str] = Field(default_factory=list)
    datas: list[str] = Field(default_factory=list)


_RE_CNJ = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
_RE_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_RE_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_RE_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_RE_VALOR = re.compile(r"\bR\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?\b")
_RE_DATA = re.compile(r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})\b")

_KEYWORDS_JURIDICAS = (
    "dos fatos", "fatos", "pedido", "pedidos", "requer", "requerimento",
    "causa de pedir", "valor da causa", "liminar", "tutela", "urgência",
    "contestação", "impugnação", "sentença", "decisão", "acórdão",
    "prova", "documento", "testemunha", "laudo", "perícia", "contrato",
    "prazo", "intimação", "citação", "audiência", "prescrição", "decadência",
    "risco", "dano", "multa", "honorários", "sucumbência", "recurso",
    "autor", "réu", "requerente", "requerido", "exequente", "executado",
    "cpf", "cnpj", "processo", "vara", "tribunal", "comarca",
)


def _normalizar_texto(texto: str) -> str:
    return (texto or "").replace("\x00", "").replace("\r\n", "\n").strip()


def _unicos(seq: Iterable[str], limite: int = MAX_SINAIS) -> list[str]:
    vistos: set[str] = set()
    out: list[str] = []
    for item in seq:
        item = (item or "").strip()
        if item and item not in vistos:
            vistos.add(item)
            out.append(item)
        if len(out) >= limite:
            break
    return out


def extrair_sinais_documento(texto: str) -> SinaisDocumento:
    """Extrai sinais objetivos do documento sem chamar LLM.

    Esses sinais ajudam a IA a perceber a estrutura do caso, mas a validação e a
    gravação definitiva continuam dependendo de revisão humana.
    """
    texto = _normalizar_texto(texto)
    return SinaisDocumento(
        numeros_processo=_unicos(_RE_CNJ.findall(texto)),
        cpfs=_unicos(_RE_CPF.findall(texto)),
        cnpjs=_unicos(_RE_CNPJ.findall(texto)),
        emails=_unicos(_RE_EMAIL.findall(texto)),
        valores_monetarios=_unicos(_RE_VALOR.findall(texto)),
        datas=_unicos(_RE_DATA.findall(texto)),
    )


def dividir_em_chunks_juridicos(
    texto: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[DocumentoChunk]:
    """Divide texto OCR em chunks estáveis, preferindo quebras naturais.

    A divisão preserva sobreposição para não quebrar raciocínio jurídico em
    pontos sensíveis, como pedido, fundamento ou trecho de decisão.
    """
    texto = _normalizar_texto(texto)
    if not texto:
        return []
    if len(texto) <= chunk_size:
        return [DocumentoChunk(indice=1, inicio=0, fim=len(texto), texto=texto)]

    chunks: list[DocumentoChunk] = []
    pos = 0
    n = len(texto)
    indice = 1
    min_break = int(chunk_size * 0.55)

    while pos < n:
        fim = min(pos + chunk_size, n)
        if fim < n:
            janela_inicio = min(pos + min_break, fim)
            candidatos = [
                texto.rfind("\n\n", janela_inicio, fim),
                texto.rfind("\n", janela_inicio, fim),
                texto.rfind(". ", janela_inicio, fim),
                texto.rfind("; ", janela_inicio, fim),
            ]
            corte = max(candidatos)
            if corte > pos:
                fim = corte + 1

        trecho = texto[pos:fim].strip()
        if trecho:
            chunks.append(DocumentoChunk(indice=indice, inicio=pos, fim=fim, texto=trecho))
            indice += 1

        if fim >= n:
            break
        prox = max(0, fim - overlap)
        if prox <= pos:
            prox = fim
        pos = prox

    return chunks


def _score_trecho(trecho: str) -> int:
    lower = trecho.lower()
    score = 0
    for kw in _KEYWORDS_JURIDICAS:
        if kw in lower:
            score += 3
    # Trechos com valores, datas e processo tendem a ser juridicamente úteis.
    score += len(_RE_CNJ.findall(trecho)) * 4
    score += len(_RE_VALOR.findall(trecho)) * 2
    score += len(_RE_DATA.findall(trecho))
    return score


def _selecionar_trechos_relevantes(chunks: list[DocumentoChunk], *, max_chars: int) -> str:
    candidatos: list[tuple[int, int, str]] = []
    for ch in chunks:
        # Parágrafos grandes são reduzidos; parágrafos pequenos demais não ajudam.
        paragrafos = [p.strip() for p in re.split(r"\n{2,}", ch.texto) if len(p.strip()) >= 80]
        if not paragrafos:
            paragrafos = [ln.strip() for ln in ch.texto.split("\n") if len(ln.strip()) >= 80]
        for p in paragrafos[:12]:
            score = _score_trecho(p)
            if score > 0:
                candidatos.append((score, ch.indice, p[:1_200]))

    candidatos.sort(key=lambda x: (-x[0], x[1]))
    partes: list[str] = []
    total = 0
    usados: set[str] = set()

    for score, indice, trecho in candidatos:
        assinatura = trecho[:140]
        if assinatura in usados:
            continue
        usados.add(assinatura)
        bloco = f"[chunk {indice} | relevância {score}]\n{trecho}"
        if total + len(bloco) > max_chars:
            break
        partes.append(bloco)
        total += len(bloco)

    return "\n\n".join(partes)


def _formatar_sinais(sinais: SinaisDocumento) -> str:
    dados = sinais.model_dump() if hasattr(sinais, "model_dump") else sinais.dict()
    linhas = []
    for chave, valores in dados.items():
        if valores:
            linhas.append(f"- {chave}: {', '.join(valores[:MAX_SINAIS])}")
    return "\n".join(linhas) if linhas else "- nenhum sinal estruturado detectado localmente"


def montar_dossie_documental(
    texto: str,
    *,
    titulo: str | None = None,
    max_chars: int = MAX_DOSSIE_CHARS,
) -> str:
    """Monta contexto jurídico compacto para IA a partir do documento inteiro.

    Para documentos curtos, devolve o texto integral. Para documentos longos,
    preserva: sinais estruturais, início, trechos relevantes de todos os chunks e
    final. Isso melhora muito a qualidade da análise em comparação com cortar os
    primeiros 4.000 caracteres.
    """
    texto = _normalizar_texto(texto)
    if not texto:
        return ""
    if len(texto) <= max_chars:
        return texto

    chunks = dividir_em_chunks_juridicos(texto)
    sinais = extrair_sinais_documento(texto)
    inicio = texto[:3_500]
    final = texto[-2_800:]
    espaco_trechos = max(4_000, max_chars - len(inicio) - len(final) - 3_500)
    trechos = _selecionar_trechos_relevantes(chunks, max_chars=espaco_trechos)

    cabecalho = [
        "DOSSIÊ DOCUMENTAL JURÍDICO — DOCUMENTO LONGO",
        f"Título informado: {titulo or 'não informado'}",
        f"Tamanho OCR: {len(texto)} caracteres",
        f"Chunks jurídicos: {len(chunks)}",
        "",
        "SINAIS ESTRUTURADOS EXTRAÍDOS LOCALMENTE:",
        _formatar_sinais(sinais),
        "",
        "ORIENTAÇÃO PARA A IA:",
        "- Analise este dossiê como advogado sênior.",
        "- Considere início, trechos relevantes e final; não presuma dados ausentes.",
        "- Se algo não estiver no dossiê, marque como lacuna/null e peça revisão humana.",
    ]

    blocos = [
        "\n".join(cabecalho),
        "\n\nINÍCIO DO DOCUMENTO:\n" + inicio,
    ]
    if trechos:
        blocos.append("\n\nTRECHOS JURIDICAMENTE RELEVANTES AO LONGO DO DOCUMENTO:\n" + trechos)
    blocos.append("\n\nFINAL DO DOCUMENTO:\n" + final)

    dossie = "\n\n---\n\n".join(blocos)
    if len(dossie) > max_chars:
        dossie = dossie[:max_chars] + "\n\n[TRUNCADO PELO LIMITE DO DOSSIÊ — revisar OCR/RAG do documento completo]"
    return dossie
