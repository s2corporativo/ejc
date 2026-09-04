# ── app/services/saneamento/tpu.py ───────────────────────────────────────────
# TPU — Tabelas Processuais Unificadas (Resolução CNJ nº 46/2007).
#
# Os movimentos retornados pelo DataJud vêm no campo `movimentos`, cada um com
# `codigo` (código TPU) e `nome`.
#
# DESENHO DELIBERADO: os códigos terminativos NÃO são embutidos no código-fonte
# como verdade absoluta. Eles vivem na tabela `saneamento.tpu_movimento`,
# versionada e auditável (fonte + revisado_por), porque:
#   1. a TPU é atualizada periodicamente pelo CNJ (há boletins de atualização);
#   2. a Justiça do Trabalho publica acréscimos próprios à tabela;
#   3. errar um código aqui significa marcar processo ativo como encerrado.
#
# SEMENTE VERIFICADA (migration 154): apenas o código 246 — "Arquivado
# definitivamente" (TJDFT, significado dos andamentos) — está confirmado em
# fonte oficial. Os demais códigos terminativos (baixa definitiva, extinção
# da execução, trânsito em julgado, cancelamento de distribuição, remessa a
# outro órgão) NÃO foram confirmados e por isso não estão semeados — carregar
# com `scripts/carregar_tpu.py` a partir do SGT (Sistema de Gestão de Tabelas
# Processuais Unificadas — CNJ) e classificar com revisão de advogado antes
# de habilitar o indicativo automático para eles.
#
# Enquanto a tabela não estiver completa, o módulo opera em modo degradado:
# sinaliza menos, nunca sinaliza a mais (ver encerramento.py).
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.saneamento import TpuMovimento

__all__ = [
    "ClasseMovimento",
    "MovimentoTPU",
    "CatalogoTPU",
    "carregar_catalogo",
]


class ClasseMovimento(str, Enum):
    """Classificação funcional de um movimento para fins de saneamento."""

    TERMINATIVO = "terminativo"
    """Encerra o processo naquele grau. Candidato a encerramento."""

    SUSPENSIVO = "suspensivo"
    """Suspende ou sobresta. NÃO encerra — impede o indicativo."""

    REATIVADOR = "reativador"
    """Desarquivamento, recurso, cumprimento de sentença. Cancela o indicativo."""

    ORDINARIO = "ordinario"
    """Tramitação comum. Neutro."""

    NAO_CLASSIFICADO = "nao_classificado"
    """Código presente na TPU mas ainda sem revisão jurídica. Tratado como ordinário."""


@dataclass(frozen=True, slots=True)
class MovimentoTPU:
    codigo: int
    nome: str
    classe: ClasseMovimento = ClasseMovimento.NAO_CLASSIFICADO
    fonte: str = ""
    """De onde veio a classificação. Exigido para auditoria."""


@dataclass(slots=True)
class CatalogoTPU:
    """Catálogo consultável de movimentos, carregado de `saneamento.tpu_movimento`."""

    movimentos: dict[int, MovimentoTPU] = field(default_factory=dict)

    def adicionar(self, mov: MovimentoTPU) -> None:
        self.movimentos[mov.codigo] = mov

    def classe_de(self, codigo: int | str | None) -> ClasseMovimento:
        try:
            c = int(codigo)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return ClasseMovimento.NAO_CLASSIFICADO
        mov = self.movimentos.get(c)
        return mov.classe if mov else ClasseMovimento.NAO_CLASSIFICADO

    def nome_de(self, codigo: int | str | None) -> str:
        try:
            c = int(codigo)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return "desconhecido"
        mov = self.movimentos.get(c)
        return mov.nome if mov else "desconhecido"

    @property
    def terminativos(self) -> set[int]:
        return {
            c for c, m in self.movimentos.items()
            if m.classe is ClasseMovimento.TERMINATIVO
        }

    @property
    def cobertura(self) -> dict[str, int]:
        """Diagnóstico: quantos códigos já receberam revisão jurídica.

        Fonte de `GET /saneamento/tpu/cobertura`.
        """
        total = len(self.movimentos)
        classificados = sum(
            1 for m in self.movimentos.values()
            if m.classe is not ClasseMovimento.NAO_CLASSIFICADO
        )
        return {
            "total": total,
            "classificados": classificados,
            "pendentes": total - classificados,
        }

    @classmethod
    def de_registros(cls, registros: list[dict]) -> "CatalogoTPU":
        """Constrói a partir de linhas do banco ou de JSON:
        {"codigo": 246, "nome": "...", "classe": "terminativo", "fonte": "..."}
        """
        cat = cls()
        for r in registros:
            cat.adicionar(
                MovimentoTPU(
                    codigo=int(r["codigo"]),
                    nome=str(r.get("nome", "")),
                    classe=ClasseMovimento(r.get("classe", "nao_classificado")),
                    fonte=str(r.get("fonte", "")),
                )
            )
        return cat


async def carregar_catalogo(db: AsyncSession) -> CatalogoTPU:
    """Carrega o catálogo vigente de `saneamento.tpu_movimento`."""
    rows = (await db.execute(select(TpuMovimento))).scalars().all()
    return CatalogoTPU.de_registros(
        [
            {"codigo": r.codigo, "nome": r.nome, "classe": r.classe, "fonte": r.fonte}
            for r in rows
        ]
    )
