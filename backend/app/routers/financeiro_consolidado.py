"""Fachada compatível do módulo Financeiro.

A implementação foi dividida por responsabilidade. Este módulo preserva o
import histórico app.routers.financeiro_consolidado e todas as URLs.
"""
# ruff: noqa: F401
from fastapi import APIRouter

from app.routers.financeiro import dashboard, governanca, comissoes, fechamento

router = APIRouter()
router.include_router(dashboard.router)
router.include_router(governanca.router)
router.include_router(comissoes.router)
router.include_router(fechamento.router)

from app.routers.financeiro.dashboard import (
    consolidado, pendencias_operacionais, demonstrativo_gerencial, painel_operacional,
)
from app.routers.financeiro.governanca import (
    politica_financeira, atualizar_politica_financeira, listar_aprovacoes_financeiras,
    aprovar_pagamento_financeiro, rentabilidade_financeira, distribuicao_disponivel,
    obter_fechamento_financeiro, fechar_competencia_financeira, excecoes_financeiras,
    sugestoes_conciliacao_bancaria, confirmar_conciliacao_bancaria,
)
from app.routers.financeiro.fechamento import fechamento_inteligente
from app.routers.financeiro.comissoes import pagar_comissoes_em_lote
from app.routers.financeiro.common import (
    CommissionRuleIn, CommissionRulePatch, CommissionAdjustmentIn, CommissionBatchIn,
    CommissionCloseIn, FinanceCloseIn, FinancePolicyPatch, ReconcileConfirmIn,
    _classificar_fechamento,
)
