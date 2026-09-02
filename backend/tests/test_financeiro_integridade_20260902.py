"""Regressões da auditoria financeira E2E de 02/09/2026.

Cobrem invariantes de validação, normalização, ledger compatível, pré-fechamento
e integração do scheduler que não podem regredir silenciosamente, sem exigir
acesso a banco de produção.
"""
import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.fee import FeeStatus
from app.routers.despesas import DespesaCreate, DespesaUpdate, _normalizar_baixa
from app.routers.financeiro_consolidado import (
    _classificar_fechamento,
    pendencias_operacionais,
)
from app.routers.office_contracts import ContractCreate
from app.routers.partner_withdrawals import WithdrawalCreate
from app.routers.pix import PixCobrancaIn, gerar_brcode
from app.schemas.fee import FeePaymentCreate, FeeUpdate
from app.services.fee_ledger_compat import LEDGER_COMPAT_CTES, total_pago_efetivo


def test_fee_update_recusa_valor_negativo_e_campos_fantasmas():
    with pytest.raises(ValidationError):
        FeeUpdate(valor=Decimal("-0.01"))
    with pytest.raises(ValidationError):
        FeeUpdate(valor=Decimal("10.00"), campo_inexistente="x")


def test_pagamento_exige_valor_positivo_e_forma_controlada():
    base = {
        "valor": Decimal("10.00"),
        "data_pagamento": date(2026, 9, 2),
    }
    for forma in ("pix", "transferencia", "dinheiro", "cartao", "boleto", "outro", None):
        assert FeePaymentCreate(**base, forma=forma).valor == Decimal("10.00")

    with pytest.raises(ValidationError):
        FeePaymentCreate(**base, forma="cripto")
    with pytest.raises(ValidationError):
        FeePaymentCreate(**base, valor=Decimal("0"))
    with pytest.raises(ValidationError):
        FeePaymentCreate(**base, forma_pagamento="pix")


def test_despesa_exige_valor_positivo_status_e_competencia_validos():
    base = {
        "categoria": "tecnologia",
        "descricao": "Serviço",
        "valor": Decimal("100.00"),
        "competencia": "2026-09",
    }
    assert DespesaCreate(**base).valor == Decimal("100.00")

    for patch in (
        {**base, "valor": Decimal("0")},
        {**base, "status": "baixado"},
        {**base, "competencia": "2026-13"},
    ):
        with pytest.raises(ValidationError):
            DespesaCreate(**patch)

    with pytest.raises(ValidationError):
        DespesaUpdate(campo_inexistente="silencioso")


def test_despesa_normaliza_data_de_baixa_no_backend_sem_reescrever_historico():
    hoje = date.today()
    assert _normalizar_baixa({"status": "pago"})["pago_em"] == hoje
    assert _normalizar_baixa({"status": "pendente"}, status_atual="pago")["pago_em"] is None
    assert _normalizar_baixa({"status": "cancelado"}, status_atual="pago")["pago_em"] is None
    # Alterar descrição/categoria de despesa já paga não pode mover a baixa
    # histórica para a data de hoje.
    assert _normalizar_baixa(
        {"descricao": "Descrição corrigida"}, status_atual="pago"
    ) == {"descricao": "Descrição corrigida"}

    with pytest.raises(HTTPException) as exc:
        _normalizar_baixa(
            {"status": "pendente", "pago_em": date(2026, 9, 2)},
            status_atual="pendente",
        )
    assert exc.value.status_code == 422


def test_contrato_recusa_valor_negativo_e_vigencia_invertida():
    with pytest.raises(ValidationError):
        ContractCreate(
            title="Contrato",
            counterparty="Fornecedor",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 1),
        )
    with pytest.raises(ValidationError):
        ContractCreate(
            title="Contrato",
            counterparty="Fornecedor",
            start_date=date(2026, 9, 1),
            value=Decimal("-1.00"),
        )


def test_saque_recusa_bruto_nao_positivo_e_despesa_negativa():
    with pytest.raises(ValidationError):
        WithdrawalCreate(gross_value=Decimal("0"))
    with pytest.raises(ValidationError):
        WithdrawalCreate(
            gross_value=Decimal("100.00"),
            case_expenses=Decimal("-0.01"),
        )


def test_pix_recusa_valor_nao_positivo_e_payload_extra():
    with pytest.raises(ValidationError):
        PixCobrancaIn(
            chave="teste@example.com",
            nome="Escritorio",
            cidade="Betim",
            valor=Decimal("0"),
        )
    with pytest.raises(ValidationError):
        PixCobrancaIn(
            chave="teste@example.com",
            nome="Escritorio",
            cidade="Betim",
            segredo="nao-aceitar",
        )


def test_brcode_decimal_preserva_centavos_e_crc():
    codigo = gerar_brcode(
        chave="teste@example.com",
        nome="Escritorio",
        cidade="Betim",
        valor=Decimal("123.45"),
        txid="ABC123",
    )
    assert "5406123.45" in codigo
    assert codigo[-8:-4] == "6304"
    assert len(codigo[-4:]) == 4


def test_fechamento_inteligente_classifica_pronto_revisao_e_bloqueio():
    assert _classificar_fechamento([]) == ("pronto", 100)

    revisao = [
        {"codigo": "pendente", "severidade": "revisao", "qtd": 50},
    ]
    assert _classificar_fechamento(revisao) == ("revisao", 93)

    bloqueado = [
        {"codigo": "overpayment", "severidade": "bloqueio", "qtd": 1},
        {"codigo": "sem_comprovante", "severidade": "revisao", "qtd": 20},
    ]
    assert _classificar_fechamento(bloqueado) == ("bloqueado", 68)


def test_fechamento_score_penaliza_categoria_e_nao_volume():
    um = [{"codigo": "x", "severidade": "bloqueio", "qtd": 1}]
    muitos = [{"codigo": "x", "severidade": "bloqueio", "qtd": 999}]
    assert _classificar_fechamento(um) == _classificar_fechamento(muitos)


def test_hardening_scheduler_substitui_apenas_callbacks_financeiros():
    from app.services import scheduler
    from app.services import scheduler_financeiro

    original_brief = scheduler._morning_brief
    original_honorarios = scheduler._alertar_honorarios
    try:
        scheduler_financeiro.instalar()
        assert scheduler._morning_brief is scheduler_financeiro._morning_brief_financeiro
        assert scheduler._alertar_honorarios is scheduler_financeiro._marcar_honorarios_atrasados
    finally:
        scheduler._morning_brief = original_brief
        scheduler._alertar_honorarios = original_honorarios


class _ResultadoFake:
    def __init__(self, *, mapping=None, scalar_value=None):
        self.mapping = mapping
        self.scalar_value = scalar_value

    def mappings(self):
        return self

    def first(self):
        return self.mapping

    def scalar(self):
        return self.scalar_value


class _ResultadoOneFake:
    def __init__(self, values):
        self.values = values

    def one(self):
        return self.values


class _DBFake:
    def __init__(self, resultados):
        self.resultados = list(resultados)

    async def execute(self, *_args, **_kwargs):
        return self.resultados.pop(0)


def test_ledger_real_prevalece_sobre_fallback_legado_sem_duplicar():
    fee = SimpleNamespace(
        id="fee-1",
        status=FeeStatus.pago,
        data_pagamento=date(2026, 8, 20),
        valor=Decimal("1000.00"),
    )
    db = _DBFake([_ResultadoOneFake((Decimal("400.00"), 1))])

    total, legado = asyncio.run(total_pago_efetivo(db, fee))

    assert total == Decimal("400.00")
    assert legado is False


def test_ledger_reconhece_quitacao_legada_somente_sem_subledger():
    fee = SimpleNamespace(
        id="fee-legado",
        status=FeeStatus.pago,
        data_pagamento=date(2026, 8, 20),
        valor=Decimal("1000.00"),
    )
    db = _DBFake([_ResultadoOneFake((Decimal("0"), 0))])

    total, legado = asyncio.run(total_pago_efetivo(db, fee))

    assert total == Decimal("1000.00")
    assert legado is True


def test_ledger_nao_inventa_recebimento_para_fee_aberto_sem_pagamentos():
    fee = SimpleNamespace(
        id="fee-aberto",
        status=FeeStatus.pendente,
        data_pagamento=None,
        valor=Decimal("1000.00"),
    )
    db = _DBFake([_ResultadoOneFake((Decimal("0"), 0))])

    total, legado = asyncio.run(total_pago_efetivo(db, fee))

    assert total == Decimal("0")
    assert legado is False


def test_cte_ledger_exclui_soft_deleted_e_exige_not_exists_no_fallback():
    assert "WHERE f.deleted_at IS NULL" in LEDGER_COMPAT_CTES
    assert "NOT EXISTS" in LEDGER_COMPAT_CTES
    assert "SELECT 1 FROM fee_payments fp WHERE fp.fee_id = f.id" in LEDGER_COMPAT_CTES
    assert "FALSE AS legado_sem_subledger" in LEDGER_COMPAT_CTES
    assert "TRUE AS legado_sem_subledger" in LEDGER_COMPAT_CTES


def test_fila_atencao_prioriza_risco_e_nao_expoe_pii():
    db = _DBFake(
        [
            _ResultadoFake(mapping={"qtd": 2, "total": Decimal("900.00")}),
            _ResultadoFake(
                mapping={
                    "vencidas_qtd": 1,
                    "vencidas_total": Decimal("200.00"),
                    "proximas_qtd": 3,
                    "proximas_total": Decimal("600.00"),
                }
            ),
            _ResultadoFake(mapping={"qtd": 4, "total": Decimal("1200.00")}),
            _ResultadoFake(scalar_value=2),
            _ResultadoFake(scalar_value=1),
        ]
    )
    usuario = SimpleNamespace(role=SimpleNamespace(value="financeiro"))

    resposta = asyncio.run(pendencias_operacionais(db=db, cu=usuario))

    assert resposta["total"] == 6
    assert [i["prioridade"] for i in resposta["itens"][:2]] == ["alta", "alta"]
    assert resposta["itens"][0]["codigo"] == "honorarios_vencidos"
    assert resposta["itens"][0]["valor"] == Decimal("900.00")
    for item in resposta["itens"]:
        assert "cliente" not in item
        assert "case_id" not in item
        assert "descricao" not in item
