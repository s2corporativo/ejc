"""
Serviço de Aprendizado de Estilo do Advogado.

Versão v1 sem migration: calcula o perfil de estilo sob demanda a partir de
peças já existentes, revisadas por humano e em status qualificado. Não grava
perfil persistente nem altera dados sensíveis.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_doc import LegalDoc, PecaStatus

_STATUS_BASE = {PecaStatus.aprovada, PecaStatus.final, PecaStatus.protocolada}
_MAX_DOCS = 12
_MAX_CHARS_DOC = 12_000


@dataclass
class PerfilEstilo:
    user_id: str
    total_pecas: int
    total_palavras: int
    media_palavras_frase: float
    tamanho_medio_peca: int
    secoes_frequentes: list[str]
    conectores_frequentes: list[str]
    marcas_estilo: list[str]
    instrucoes_prompt: str


def _limpar_texto(texto: str) -> str:
    texto = re.sub(r"[#*_`>|]+", " ", texto or "")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ]{3,}", texto.lower())


def _frases(texto: str) -> list[str]:
    return [f.strip() for f in re.split(r"[.!?]+", texto or "") if len(f.strip()) > 20]


def _detectar_secoes(conteudos: list[str]) -> list[str]:
    padroes = [
        "dos fatos", "do direito", "dos pedidos", "da tutela", "da liminar",
        "da justiça gratuita", "da gratuidade", "das provas", "do mérito",
        "das preliminares", "da tempestividade", "do cabimento", "da responsabilidade",
        "do dano moral", "do dano material", "da inversão do ônus da prova",
    ]
    c = Counter()
    bloco = "\n".join(conteudos).lower()
    for p in padroes:
        c[p] = bloco.count(p)
    return [k for k, v in c.most_common(10) if v > 0]


def _detectar_conectores(palavras: list[str]) -> list[str]:
    conectores = [
        "ademais", "portanto", "assim", "contudo", "entretanto", "outrossim",
        "diante", "nesse", "neste", "logo", "destarte", "inclusive", "sobretudo",
        "conforme", "considerando", "todavia", "porquanto", "razão",
    ]
    c = Counter(p for p in palavras if p in conectores)
    return [k for k, v in c.most_common(8) if v > 0]


def _marcas_estilo(media_frase: float, tamanho_medio: int, secoes: list[str], conectores: list[str]) -> list[str]:
    marcas: list[str] = []
    if media_frase >= 28:
        marcas.append("períodos longos e argumentação desenvolvida")
    elif media_frase <= 16:
        marcas.append("frases mais diretas e objetivas")
    else:
        marcas.append("equilíbrio entre objetividade e fundamentação")

    if tamanho_medio >= 5500:
        marcas.append("peças extensas, com fundamentação detalhada")
    elif tamanho_medio <= 2200:
        marcas.append("peças sintéticas, com foco em objetividade")
    else:
        marcas.append("peças de extensão média")

    if "dos pedidos" in secoes:
        marcas.append("pedidos organizados em seção própria")
    if "do direito" in secoes:
        marcas.append("fundamentação jurídica em seção destacada")
    if conectores:
        marcas.append("uso recorrente de conectores argumentativos")
    return marcas[:8]


def _instrucoes_prompt(perfil: PerfilEstilo) -> str:
    secoes = ", ".join(perfil.secoes_frequentes) or "seções jurídicas clássicas"
    conectores = ", ".join(perfil.conectores_frequentes) or "conectores jurídicos moderados"
    marcas = "; ".join(perfil.marcas_estilo)
    return (
        "Adapte a redação ao estilo do advogado responsável, sem copiar trechos de peças anteriores. "
        f"Características observadas: {marcas}. "
        f"Estrutura preferida: {secoes}. "
        f"Conectores recorrentes: {conectores}. "
        "Preserve clareza, precisão técnica, revisão humana obrigatória e proibição de inventar fatos, documentos, jurisprudência ou números processuais."
    )


async def carregar_pecas_base_estilo(
    db: AsyncSession,
    user_id: str,
    *,
    limite: int = _MAX_DOCS,
) -> list[LegalDoc]:
    """Busca peças revisadas/aprovadas do usuário para extrair estilo."""
    q = (
        select(LegalDoc)
        .where(
            LegalDoc.deleted_at.is_(None),
            LegalDoc.human_reviewed.is_(True),
            LegalDoc.status.in_(list(_STATUS_BASE)),
            ((LegalDoc.revisor_id == user_id) | (LegalDoc.created_by == user_id)),
        )
        .order_by(LegalDoc.updated_at.desc())
        .limit(limite)
    )
    return (await db.execute(q)).scalars().all()


async def gerar_perfil_estilo(
    db: AsyncSession,
    user_id: str,
    *,
    limite: int = _MAX_DOCS,
) -> dict[str, Any]:
    """Gera perfil de estilo determinístico e explicável para o usuário."""
    pecas = await carregar_pecas_base_estilo(db, user_id, limite=limite)
    conteudos = [_limpar_texto((p.conteudo or "")[:_MAX_CHARS_DOC]) for p in pecas if p.conteudo]
    if not conteudos:
        return {
            "status": "sem_base",
            "user_id": user_id,
            "total_pecas": 0,
            "instrucoes_prompt": "",
            "mensagem": "Não há peças humanas aprovadas/finais/protocoladas suficientes para extrair estilo.",
        }

    todas_palavras: list[str] = []
    todas_frases: list[str] = []
    for c in conteudos:
        todas_palavras.extend(_palavras(c))
        todas_frases.extend(_frases(c))

    total_palavras = len(todas_palavras)
    media_frase = round(total_palavras / max(1, len(todas_frases)), 1)
    tamanho_medio = round(sum(len(c) for c in conteudos) / max(1, len(conteudos)))
    secoes = _detectar_secoes(conteudos)
    conectores = _detectar_conectores(todas_palavras)
    marcas = _marcas_estilo(media_frase, tamanho_medio, secoes, conectores)

    perfil = PerfilEstilo(
        user_id=user_id,
        total_pecas=len(conteudos),
        total_palavras=total_palavras,
        media_palavras_frase=media_frase,
        tamanho_medio_peca=tamanho_medio,
        secoes_frequentes=secoes,
        conectores_frequentes=conectores,
        marcas_estilo=marcas,
        instrucoes_prompt="",
    )
    perfil.instrucoes_prompt = _instrucoes_prompt(perfil)
    return {
        "status": "ok",
        "user_id": perfil.user_id,
        "total_pecas": perfil.total_pecas,
        "total_palavras": perfil.total_palavras,
        "media_palavras_frase": perfil.media_palavras_frase,
        "tamanho_medio_peca": perfil.tamanho_medio_peca,
        "secoes_frequentes": perfil.secoes_frequentes,
        "conectores_frequentes": perfil.conectores_frequentes,
        "marcas_estilo": perfil.marcas_estilo,
        "instrucoes_prompt": perfil.instrucoes_prompt,
        "modo": "sob_demanda_sem_persistencia",
    }


async def montar_instrucoes_estilo_para_prompt(db: AsyncSession, user_id: str) -> str:
    """Retorna bloco curto para ser usado no prompt de geração de peça."""
    perfil = await gerar_perfil_estilo(db, user_id)
    if perfil.get("status") != "ok":
        return ""
    return str(perfil.get("instrucoes_prompt") or "")[:1600]
