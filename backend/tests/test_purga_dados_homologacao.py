"""Testes do script de purga dos dados de homologação (sem banco).

O que dá para travar sem Postgres: montagem das queries/filtros (marcadores ×
colunas, bind-params, soft-delete-nunca-DELETE), a guarda de deleted_at e a
exigência de confirmação explícita ("PURGAR"). A execução real é ato humano no
VPS, com backup prévio (scripts/backup.sh) — ver docstring do próprio script.
"""
from __future__ import annotations

from scripts.purga_dados_homologacao import (
    ALVOS,
    MARCADORES,
    PALAVRA_CONFIRMACAO,
    PREFIXO_CONTA_QA,
    confirmar_purga,
    montar_clausula_marcadores,
    montar_sql_desativar_conta_qa,
    montar_sql_pecas_de_casos_marcados,
    montar_sql_selecao,
    montar_sql_selecao_conta_qa,
    montar_sql_soft_delete,
    tabelas_sem_deleted_at,
)


# ── Marcadores e alvos ────────────────────────────────────────────────────────

def test_marcadores_cobrem_os_residuos_da_auditoria():
    assert "HOMOLOG-FICTICIO" in MARCADORES
    assert "TESTE AUDITORIA EXCLUIR" in MARCADORES
    # Marcador atual do qa/e2e/run_fictitious_smoke.py (MARKER).
    assert "E2E-FICTICIO" in MARCADORES


def test_alvos_cobrem_clientes_casos_pecas_e_checklists():
    tabelas = {a.tabela for a in ALVOS}
    assert tabelas == {"clients", "cases", "legal_docs", "checklist_templates"}
    # users NUNCA é alvo de soft-delete — a conta QA é só desativada.
    assert "users" not in tabelas


# ── Montagem dos filtros ─────────────────────────────────────────────────────

def test_clausula_cruza_todo_marcador_com_toda_coluna_via_bind_param():
    clausula, params = montar_clausula_marcadores(("nome", "razao_social"))
    # 2 colunas × N marcadores condições, todas com ILIKE (case-insensitive).
    assert clausula.count("ILIKE") == 2 * len(MARCADORES)
    assert "nome ILIKE :m0" in clausula
    assert "razao_social ILIKE :m0" in clausula
    # Valores viajam como bind-param com curinga, nunca interpolados no SQL.
    assert params == {
        f"m{i}": f"%{m}%" for i, m in enumerate(MARCADORES)
    }
    for marcador in MARCADORES:
        assert marcador not in clausula


def test_selecao_so_pega_registros_ainda_ativos():
    for alvo in ALVOS:
        sql, _ = montar_sql_selecao(alvo)
        assert sql.startswith("SELECT id, ")
        assert f"FROM {alvo.tabela} " in sql
        assert "deleted_at IS NULL" in sql


# ── Soft-delete: Lixeira, jamais DELETE físico ───────────────────────────────

def test_soft_delete_preenche_deleted_at_e_nunca_e_delete_fisico():
    for alvo in ALVOS:
        sql = montar_sql_soft_delete(alvo)
        assert sql.startswith(f"UPDATE {alvo.tabela} SET deleted_at = NOW()")
        assert "deleted_at IS NULL" in sql          # idempotente
        assert "DELETE" not in sql.upper().replace("DELETED_AT", "")
        assert "TRUNCATE" not in sql.upper()


def test_pecas_de_casos_marcados_tambem_sao_localizadas():
    sql = montar_sql_pecas_de_casos_marcados()
    assert "FROM legal_docs" in sql
    assert "case_id IN :case_ids" in sql
    assert "deleted_at IS NULL" in sql


# ── Conta homolog.qa: desativar, nunca apagar ────────────────────────────────

def test_conta_qa_e_localizada_pelo_prefixo_de_email():
    sql, params = montar_sql_selecao_conta_qa()
    assert "FROM users" in sql
    assert "email ILIKE :prefixo" in sql
    assert params == {"prefixo": f"{PREFIXO_CONTA_QA}%"}
    assert PREFIXO_CONTA_QA == "homolog.qa"


def test_desativacao_da_conta_qa_preserva_o_registro():
    sql = montar_sql_desativar_conta_qa()
    assert sql.startswith("UPDATE users SET is_active = FALSE")
    # Trilha de auditoria: nem DELETE físico, nem soft-delete do usuário.
    assert "DELETE" not in sql.upper()
    assert "deleted_at" not in sql


# ── Guarda: recusa sem coluna deleted_at na tabela-alvo ──────────────────────

def test_guarda_recusa_tabela_alvo_sem_deleted_at():
    colunas_ok = {
        "clients": ["id", "nome", "deleted_at"],
        "cases": ["id", "titulo", "deleted_at"],
        "legal_docs": ["id", "titulo", "deleted_at"],
        "checklist_templates": ["id", "nome", "deleted_at"],
    }
    assert tabelas_sem_deleted_at(colunas_ok) == []

    sem_coluna = dict(colunas_ok)
    sem_coluna["cases"] = ["id", "titulo"]  # sem deleted_at
    assert tabelas_sem_deleted_at(sem_coluna) == ["cases"]

    # Tabela ausente do dicionário (não existe no banco) também recusa.
    del sem_coluna["clients"]
    assert set(tabelas_sem_deleted_at(sem_coluna)) == {"clients", "cases"}


# ── Confirmação explícita ────────────────────────────────────────────────────

def test_confirmacao_exige_digitar_exatamente_purgar():
    assert PALAVRA_CONFIRMACAO == "PURGAR"
    assert confirmar_purga(lambda _msg: "PURGAR") is True
    assert confirmar_purga(lambda _msg: "  PURGAR  ") is True   # espaços tolerados
    assert confirmar_purga(lambda _msg: "purgar") is False      # case-sensitive
    assert confirmar_purga(lambda _msg: "sim") is False
    assert confirmar_purga(lambda _msg: "") is False


def test_confirmacao_sem_terminal_interativo_aborta():
    def _sem_tty(_msg: str) -> str:
        raise EOFError

    assert confirmar_purga(_sem_tty) is False


def test_prompt_de_confirmacao_lembra_o_backup():
    capturado: list[str] = []

    def _entrada(msg: str) -> str:
        capturado.append(msg)
        return "nao"

    confirmar_purga(_entrada)
    assert "backup" in capturado[0].lower()
    assert "PURGAR" in capturado[0]
