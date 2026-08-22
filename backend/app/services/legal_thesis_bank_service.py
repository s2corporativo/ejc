# ── app/services/legal_thesis_bank_service.py ────────────────────────────────
# Regras determinísticas da fundação do Banco Nacional de Teses.
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

from app.models.legal_thesis_bank import (
    PRECEDENT_STATUSES,
    THESIS_KINDS,
    THESIS_SIDES,
    THESIS_STATUSES,
)


STATUS_TESes_RECOMENDAVEIS = frozenset({"validada", "revisada"})
STATUS_PRECEDENTE_RECOMENDAVEL = "validado"


def normalizar_chave(texto: str) -> str:
    """Normaliza uma chave humana sem remover informação semântica relevante."""
    sem_acentos = unicodedata.normalize("NFKD", texto or "")
    sem_acentos = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sem_acentos.lower()).strip("-")


def hash_conteudo(conteudo: str) -> str:
    """Gera SHA-256 do conteúdo normalizado para deduplicação idempotente."""
    normalizado = " ".join((conteudo or "").split()).strip()
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def tese_pode_ser_recomendada(status: str, vigente: bool = True) -> bool:
    """Somente teses vigentes validadas ou revisadas podem entrar no retrieval."""
    return vigente and status in STATUS_TESes_RECOMENDAVEIS


def precedente_pode_ser_recomendado(
    status: str,
    url_oficial: str | None,
    publicidade: str = "publico",
    dados_minimizados: bool = True,
) -> bool:
    """Impede que precedente não validado ou sem origem oficial seja recomendado."""
    return (
        status == STATUS_PRECEDENTE_RECOMENDAVEL
        and bool((url_oficial or "").strip())
        and publicidade == "publico"
        and dados_minimizados
    )


def validar_dominios_tese(
    status: str,
    lado: str,
    tipo: str,
    score_forca: int,
) -> list[str]:
    """Retorna erros de domínio sem fazer inferências jurídicas."""
    erros: list[str] = []
    if status not in THESIS_STATUSES:
        erros.append(f"status inválido: {status}")
    if lado not in THESIS_SIDES:
        erros.append(f"lado inválido: {lado}")
    if tipo not in THESIS_KINDS:
        erros.append(f"tipo inválido: {tipo}")
    if not 0 <= score_forca <= 100:
        erros.append("score_forca deve estar entre 0 e 100")
    return erros


def validar_dominio_precedente(status: str) -> list[str]:
    """Valida somente o vocabulário persistido do precedente."""
    return [] if status in PRECEDENT_STATUSES else [f"status inválido: {status}"]


def contar_status(statuses: Iterable[str]) -> dict[str, int]:
    """Resume estados sem converter contagem em probabilidade de resultado."""
    resultado: dict[str, int] = {}
    for status in statuses:
        resultado[status] = resultado.get(status, 0) + 1
    return resultado
