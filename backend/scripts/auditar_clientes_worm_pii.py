#!/usr/bin/env python3
"""Auditoria SOMENTE LEITURA de possível PII histórica no WORM de Clientes.

Não altera nem expurga `audit_logs`. A saída contém apenas IDs técnicos,
ação/entidade/data e categorias de risco; nunca imprime o conteúdo encontrado.

Uso em ambiente autorizado:
    python -m scripts.auditar_clientes_worm_pii
    python -m scripts.auditar_clientes_worm_pii --limit 5000 --json

Não executar apontando para produção sem procedimento operacional aprovado.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.models.audit_log import AuditLog


_ENTIDADES_CLIENTE = {"clients", "client_pending_items"}
_CHAVES_SENSIVEIS = {
    "cpf",
    "cpf_plain",
    "cnpj",
    "cnpj_plain",
    "documento",
    "documento_plain",
    "email",
    "telefone",
    "whatsapp",
    "nome",
    "razao_social",
    "nome_fantasia",
    "motivo",
    "justificativa",
    "justificativa_sanitizada",
}
_PADROES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CPF", re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")),
    ("CNPJ", re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PROCESSO_CNJ", re.compile(r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b")),
    (
        "TELEFONE",
        re.compile(r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)"),
    ),
)


def _preenchido(valor: Any) -> bool:
    return valor is not None and valor != "" and valor != [] and valor != {}


def detectar_riscos(valor: Any) -> set[str]:
    """Classifica risco sem devolver/reter o valor sensível analisado."""
    riscos: set[str] = set()
    if valor is None:
        return riscos

    if isinstance(valor, dict):
        for chave, item in valor.items():
            chave_norm = str(chave).strip().lower()
            if chave_norm in _CHAVES_SENSIVEIS and _preenchido(item):
                riscos.add(f"CAMPO:{chave_norm}")
            riscos.update(detectar_riscos(item))
        return riscos

    if isinstance(valor, (list, tuple, set)):
        for item in valor:
            riscos.update(detectar_riscos(item))
        return riscos

    if not isinstance(valor, str):
        return riscos

    for nome, padrao in _PADROES:
        if padrao.search(valor):
            riscos.add(nome)
    return riscos


def resumir_log(log: AuditLog) -> dict[str, Any] | None:
    """Retorna somente metadados técnicos quando houver algum indicador de PII."""
    riscos: set[str] = set()
    riscos.update(detectar_riscos(log.detalhes))
    riscos.update(detectar_riscos(log.dados_antes))
    riscos.update(detectar_riscos(log.dados_depois))
    if not riscos:
        return None
    return {
        "audit_log_id": log.id,
        "registro_id": log.registro_id,
        "entidade": log.entidade,
        "acao": log.acao,
        "created_at": log.created_at.isoformat() if log.created_at else None,
        "riscos": sorted(riscos),
    }


async def auditar(*, limit: int = 0) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(AuditLog)
            .where(AuditLog.entidade.in_(_ENTIDADES_CLIENTE))
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        if limit > 0:
            stmt = stmt.limit(limit)
        logs = (await db.execute(stmt)).scalars().all()

    achados = [resumo for log in logs if (resumo := resumir_log(log)) is not None]
    return {
        "modo": "somente_leitura",
        "registros_analisados": len(logs),
        "registros_com_indicador_pii": len(achados),
        "achados": achados,
        "observacao": (
            "Nenhum valor sensível é incluído neste relatório. Achado exige revisão "
            "de governança; não editar ou apagar WORM automaticamente."
        ),
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Quantidade máxima de logs a analisar; 0 = todos do escopo.",
    )
    parser.add_argument("--json", action="store_true", help="Saída JSON compacta.")
    return parser.parse_args()


async def _main() -> int:
    args = _args()
    if args.limit < 0:
        raise SystemExit("--limit deve ser >= 0")
    try:
        resultado = await auditar(limit=args.limit)
    finally:
        await engine.dispose()

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 2 if resultado["registros_com_indicador_pii"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
