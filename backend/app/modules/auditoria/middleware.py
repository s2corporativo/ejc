# ── app/modules/auditoria/middleware.py ──────────────────────────────────────
# Camada de auditoria canônica do EJC (contrato do CLAUDE.md).
#
# Este módulo expõe `registrar_acao()` — a API que os módulos novos
# (checklists, dossiê, atendimentos, contratos, workflow, gestão societária)
# usam para registrar ações em `audit_logs`.
#
# Implementação: delega para o helper `criar_audit_log` (app/models/audit_log.py),
# que grava na tabela ÚNICA de auditoria `audit_logs` (plural). NUNCA insere em
# `audit_log` (singular) — que sequer existe neste backend.
#
# Mapeamento de parâmetros:
#   modulo     → entidade   (ex.: "checklists", "dossie_estrategico")
#   descricao  → detalhes
# O commit é responsabilidade do chamador (mesma transação da operação).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
from typing import Optional

from app.models.audit_log import criar_audit_log


async def registrar_acao(
    db,
    user_id: Optional[str],
    acao: str,
    modulo: str,
    registro_id: Optional[str] = None,
    descricao: Optional[str] = None,
    *,
    user_role: Optional[str] = None,
    ip: Optional[str] = None,
    dados_antes: Optional[dict] = None,
    dados_depois: Optional[dict] = None,
) -> None:
    """
    Registra uma ação de auditoria em `audit_logs`.

    Assinatura compatível com todos os call-sites do projeto:
        await registrar_acao(db, user_id, acao, modulo, registro_id, descricao)

    PERSISTÊNCIA: os call-sites chamam registrar_acao() como passo final, DEPOIS
    de já terem commitado a operação principal — e esperam que o registro de
    auditoria seja persistido de forma independente. Por isso esta função
    COMMITA o log de auditoria (diferente de criar_audit_log, que não commita).
    Sem este commit, o `db.add` do log seria descartado ao fechar a sessão.
    """
    await criar_audit_log(
        db,
        user_id=user_id,
        user_role=user_role,
        acao=acao,
        entidade=modulo,
        registro_id=registro_id,
        detalhes=descricao,
        ip=ip,
        dados_antes=dados_antes,
        dados_depois=dados_depois,
    )
    await db.commit()
