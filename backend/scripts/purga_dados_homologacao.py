#!/usr/bin/env python
# ── scripts/purga_dados_homologacao.py ───────────────────────────────────────
# Purga (SOFT-DELETE) dos resíduos de homologação deixados em produção pelo
# smoke E2E (`qa/e2e/run_fictitious_smoke.py`) — casos/clientes/peças/
# checklists marcados com "HOMOLOG-FICTICIO", "TESTE AUDITORIA EXCLUIR" ou
# "E2E-FICTICIO" no nome/título, e a conta `homolog.qa*` (superadmin criada
# pelo smoke).
#
# ⚠ PRÉ-REQUISITO OBRIGATÓRIO antes de rodar com --aplicar:
#     BACKUP do banco via `scripts/backup.sh` (raiz do repo) ou o procedimento
#     do RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md. A execução é ATO HUMANO no
#     VPS — este script é só a ferramenta.
#
# Garantias de segurança:
#   - DRY-RUN por PADRÃO: sem --aplicar, apenas LISTA o que seria afetado.
#   - NUNCA faz DELETE físico: registros marcados vão para a Lixeira
#     (deleted_at = NOW(), padrão dos models do EJC).
#   - A conta homolog.qa é DESATIVADA (is_active = FALSE), nunca apagada nem
#     soft-deletada — o registro fica íntegro como trilha de auditoria.
#   - RECUSA rodar se alguma tabela-alvo não tiver a coluna deleted_at no
#     banco real (verificação via information_schema, não via ORM).
#   - --aplicar exige confirmação interativa digitando exatamente "PURGAR".
#
# Execução (container ejc_backend, conecta pelo DATABASE_URL do ambiente):
#     docker exec -it ejc_backend python -m scripts.purga_dados_homologacao
#     docker exec -it ejc_backend python -m scripts.purga_dados_homologacao --aplicar
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.purga_homologacao")

# Marcadores que o smoke de homologação imprime nos nomes/títulos dos registros
# fictícios (auditoria jul/2026 + MARKER atual do run_fictitious_smoke.py).
MARCADORES: tuple[str, ...] = (
    "HOMOLOG-FICTICIO",
    "TESTE AUDITORIA EXCLUIR",
    "E2E-FICTICIO",
)

# Prefixo do e-mail da conta QA criada pelo smoke em produção
# (homolog.qa.<...>@depaulateixeira.adv.br) — desativar, NUNCA apagar.
PREFIXO_CONTA_QA = "homolog.qa"

PALAVRA_CONFIRMACAO = "PURGAR"


@dataclass(frozen=True)
class AlvoPurga:
    """Tabela sujeita a soft-delete + colunas onde o marcador é procurado."""

    tabela: str
    colunas_busca: tuple[str, ...]
    coluna_rotulo: str  # coluna exibida no relatório de IDs afetados


# Só entram tabelas cujo MODEL tem deleted_at (Lixeira); a existência da coluna
# no BANCO ainda é verificada em tempo de execução antes de qualquer UPDATE.
# case_checklists/case_checklist_items NÃO têm deleted_at: seguem visíveis
# apenas através do caso (soft-deletado), sem update direto aqui.
ALVOS: tuple[AlvoPurga, ...] = (
    AlvoPurga("clients", ("nome", "razao_social", "nome_fantasia"), "nome"),
    AlvoPurga("cases", ("titulo", "numero_interno"), "titulo"),
    AlvoPurga("legal_docs", ("titulo",), "titulo"),
    AlvoPurga("checklist_templates", ("nome",), "nome"),
)


# ── Montagem de SQL (funções puras — testáveis sem banco) ────────────────────

def montar_clausula_marcadores(colunas: Iterable[str]) -> tuple[str, dict[str, str]]:
    """Cláusula `(col ILIKE :m0 OR ...)` cobrindo todo marcador × toda coluna.

    Retorna (sql, params). ILIKE já é case-insensitive; os valores dos
    marcadores viajam SEMPRE como bind-param (nunca interpolados).
    """
    params = {f"m{i}": f"%{m}%" for i, m in enumerate(MARCADORES)}
    condicoes = [
        f"{col} ILIKE :m{i}"
        for col in colunas
        for i in range(len(MARCADORES))
    ]
    return "(" + " OR ".join(condicoes) + ")", params


def montar_sql_selecao(alvo: AlvoPurga) -> tuple[str, dict[str, str]]:
    """SELECT dos registros marcados AINDA ATIVOS (deleted_at IS NULL)."""
    clausula, params = montar_clausula_marcadores(alvo.colunas_busca)
    sql = (
        f"SELECT id, {alvo.coluna_rotulo} AS rotulo FROM {alvo.tabela} "
        f"WHERE deleted_at IS NULL AND {clausula} ORDER BY id"
    )
    return sql, params


def montar_sql_soft_delete(alvo: AlvoPurga) -> str:
    """UPDATE de Lixeira — preencher deleted_at; JAMAIS DELETE físico."""
    return (
        f"UPDATE {alvo.tabela} SET deleted_at = NOW() "
        f"WHERE id IN :ids AND deleted_at IS NULL"
    )


def montar_sql_selecao_conta_qa() -> tuple[str, dict[str, str]]:
    """Conta(s) homolog.qa* ainda ativas — só listadas, para desativação."""
    sql = (
        "SELECT id, email FROM users "
        "WHERE email ILIKE :prefixo AND is_active IS NOT FALSE ORDER BY email"
    )
    return sql, {"prefixo": f"{PREFIXO_CONTA_QA}%"}


def montar_sql_desativar_conta_qa() -> str:
    """Desativa a conta QA (is_active=FALSE). Nunca DELETE, nunca deleted_at —
    o registro de usuário permanece como trilha de auditoria."""
    return "UPDATE users SET is_active = FALSE WHERE id IN :ids"


def montar_sql_pecas_de_casos_marcados() -> str:
    """Peças ativas vinculadas aos casos marcados (mesmo sem marcador próprio
    no título) — o smoke gera peças dentro dos casos fictícios."""
    return (
        "SELECT id, titulo AS rotulo FROM legal_docs "
        "WHERE deleted_at IS NULL AND case_id IN :case_ids ORDER BY id"
    )


def tabelas_sem_deleted_at(
    colunas_por_tabela: Mapping[str, Iterable[str]],
    alvos: Iterable[AlvoPurga] = ALVOS,
) -> list[str]:
    """Alvos de soft-delete cuja tabela NÃO tem deleted_at no banco real.

    Lista não-vazia ⇒ o script RECUSA rodar (não há como mandar para a
    Lixeira sem a coluna; DELETE físico está fora de questão).
    """
    return [
        alvo.tabela
        for alvo in alvos
        if "deleted_at" not in set(colunas_por_tabela.get(alvo.tabela, ()))
    ]


def confirmar_purga(entrada: Callable[[str], str] = input) -> bool:
    """Exige a digitação EXATA de "PURGAR" (case-sensitive) para aplicar."""
    try:
        resposta = entrada(
            f"Backup feito (scripts/backup.sh)? Digite {PALAVRA_CONFIRMACAO} "
            "para confirmar o soft-delete (qualquer outra coisa aborta): "
        )
    except EOFError:
        # Sem terminal interativo (pipe/cron) não há confirmação possível.
        return False
    return resposta.strip() == PALAVRA_CONFIRMACAO


# ── Execução contra o banco ──────────────────────────────────────────────────

async def _colunas_das_tabelas(db, tabelas: Iterable[str]) -> dict[str, list[str]]:
    from sqlalchemy import bindparam, text

    stmt = text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name IN :tabelas"
    ).bindparams(bindparam("tabelas", expanding=True))
    linhas = (await db.execute(stmt, {"tabelas": list(tabelas)})).all()
    colunas: dict[str, list[str]] = {}
    for tabela, coluna in linhas:
        colunas.setdefault(tabela, []).append(coluna)
    return colunas


async def executar(aplicar: bool, entrada: Callable[[str], str] = input) -> int:
    from sqlalchemy import bindparam, text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # 1) Guarda: toda tabela-alvo precisa de deleted_at no banco REAL.
        tabelas = [a.tabela for a in ALVOS] + ["users"]
        colunas = await _colunas_das_tabelas(db, tabelas)
        faltantes = tabelas_sem_deleted_at(colunas)
        if faltantes:
            logger.error(
                "RECUSADO: tabela(s) sem coluna deleted_at no banco: %s. "
                "Sem Lixeira não há purga segura — nada foi alterado.",
                ", ".join(faltantes),
            )
            return 2
        if "users" not in colunas or "is_active" not in colunas["users"]:
            logger.error("RECUSADO: users.is_active não encontrada — nada foi alterado.")
            return 2

        # 2) Localiza os resíduos (sempre — é o relatório do dry-run).
        afetados: dict[str, list[tuple[str, str]]] = {}
        for alvo in ALVOS:
            sql, params = montar_sql_selecao(alvo)
            linhas = (await db.execute(text(sql), params)).all()
            afetados[alvo.tabela] = [(str(r.id), str(r.rotulo or "")) for r in linhas]

        # Peças dentro dos casos marcados (podem não ter marcador no título).
        ids_casos = [rid for rid, _ in afetados.get("cases", [])]
        if ids_casos:
            stmt = text(montar_sql_pecas_de_casos_marcados()).bindparams(
                bindparam("case_ids", expanding=True)
            )
            linhas = (await db.execute(stmt, {"case_ids": ids_casos})).all()
            ja_listadas = {rid for rid, _ in afetados["legal_docs"]}
            afetados["legal_docs"] += [
                (str(r.id), str(r.rotulo or "")) for r in linhas
                if str(r.id) not in ja_listadas
            ]

        sql_qa, params_qa = montar_sql_selecao_conta_qa()
        contas_qa = [
            (str(r.id), str(r.email))
            for r in (await db.execute(text(sql_qa), params_qa)).all()
        ]

        # 3) Relatório.
        modo = "APLICAR (soft-delete)" if aplicar else "DRY-RUN (nada será alterado)"
        logger.info("Modo: %s | marcadores: %s", modo, ", ".join(MARCADORES))
        total = 0
        for tabela, linhas in afetados.items():
            logger.info("%s: %d registro(s) marcados", tabela, len(linhas))
            for rid, rotulo in linhas:
                logger.info("  - %s | %s", rid, rotulo[:90])
            total += len(linhas)
        logger.info("users (conta QA a desativar): %d", len(contas_qa))
        for rid, email in contas_qa:
            logger.info("  - %s | %s", rid, email)

        if not aplicar:
            logger.info(
                "DRY-RUN concluído: %d registro(s) iriam para a Lixeira. "
                "Para aplicar: --aplicar (EXIGE backup prévio via scripts/backup.sh).",
                total,
            )
            return 0

        if total == 0 and not contas_qa:
            logger.info("Nada a purgar — banco já limpo.")
            return 0

        # 4) Confirmação humana explícita.
        if not confirmar_purga(entrada):
            logger.warning("Confirmação ausente ou incorreta — ABORTADO, nada alterado.")
            return 1

        # 5) Soft-delete (Lixeira) + desativação da conta QA, numa transação só.
        for alvo in ALVOS:
            ids = [rid for rid, _ in afetados[alvo.tabela]]
            if not ids:
                continue
            stmt = text(montar_sql_soft_delete(alvo)).bindparams(
                bindparam("ids", expanding=True)
            )
            resultado = await db.execute(stmt, {"ids": ids})
            logger.info("%s: %d registro(s) enviados à Lixeira", alvo.tabela, resultado.rowcount)
        if contas_qa:
            stmt = text(montar_sql_desativar_conta_qa()).bindparams(
                bindparam("ids", expanding=True)
            )
            await db.execute(stmt, {"ids": [rid for rid, _ in contas_qa]})
            logger.info("users: %d conta(s) QA desativadas (registro preservado)", len(contas_qa))
        await db.commit()
        logger.info("Purga concluída — registros na Lixeira (reversível via deleted_at=NULL).")
        return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Purga (soft-delete) dos dados de homologação: dry-run por "
                    "padrão; --aplicar exige backup prévio e confirmação 'PURGAR'.")
    ap.add_argument(
        "--aplicar", action="store_true",
        help="Aplica o soft-delete (Lixeira) e desativa a conta homolog.qa. "
             "Sem esta flag, apenas lista (dry-run).",
    )
    args = ap.parse_args(argv)
    return asyncio.run(executar(aplicar=args.aplicar))


if __name__ == "__main__":
    sys.exit(main())
