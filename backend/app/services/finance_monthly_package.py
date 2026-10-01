"""Pacote mensal único do Financeiro: PDF + JSON + CSVs auditáveis."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from app.services.pdf_service import relatorio_mensal_pdf


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if v is None else v for k, v in row.items()})
    return buf.getvalue().encode("utf-8-sig")


async def _rows(db, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    data = (await db.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in data]


async def gerar_pacote_financeiro_mensal(
    db,
    competencia: str,
    resumo: dict[str, Any],
) -> bytes:
    inicio = date.fromisoformat(f"{competencia}-01")
    ano, mes = (int(v) for v in competencia.split("-"))
    fim = date(ano + (1 if mes == 12 else 0), 1 if mes == 12 else mes + 1, 1)
    params = {"inicio": inicio, "fim": fim, "competencia": competencia}

    receitas = await _rows(db, """
        SELECT fp.id, fp.fee_id, f.case_id, f.client_id, f.descricao,
               fp.valor, fp.data_pagamento, fp.forma, fp.comprovante_doc_id
        FROM fee_payments fp
        JOIN fees f ON f.id=fp.fee_id
        WHERE f.deleted_at IS NULL
          AND fp.data_pagamento >= :inicio AND fp.data_pagamento < :fim
        ORDER BY fp.data_pagamento, fp.id
    """, params)

    despesas = await _rows(db, """
        SELECT id,categoria,subcategoria,tipo,descricao,valor,vencimento,pago_em,
               status,competencia,comprovante_doc_id
        FROM office_expenses
        WHERE deleted_at IS NULL
          AND (competencia=:competencia OR (pago_em >= :inicio AND pago_em < :fim))
        ORDER BY COALESCE(pago_em,vencimento),id
    """, params)

    comissoes = await _rows(db, """
        SELECT a.id AS allocation_id,a.case_id,a.advogado_responsavel_id,
               a.bruto_recebido,a.despesas_deduzidas,a.base_liquida,
               a.percentual_advogado,a.valor_advogado,a.valor_escritorio,
               pw.id AS withdrawal_id,pw.status AS withdrawal_status,
               pw.partner_share,pw.paid_at,pw.payment_method,
               pw.payment_reference,pw.comprovante_doc_id
        FROM case_receipt_allocations a
        JOIN fee_payments fp ON fp.id=a.fee_payment_id
        LEFT JOIN partner_withdrawals pw
          ON pw.id=a.withdrawal_id AND pw.deleted_at IS NULL
        WHERE fp.data_pagamento >= :inicio AND fp.data_pagamento < :fim
        ORDER BY fp.data_pagamento,a.created_at
    """, params)

    estornos = await _rows(db, """
        SELECT fe.id,fe.fee_id,fe.fee_payment_id,fe.valor,fe.motivo,fe.data_estorno
        FROM fee_estornos fe
        WHERE fe.data_estorno >= :inicio AND fe.data_estorno < :fim
        ORDER BY fe.data_estorno,fe.id
    """, params)

    conciliacoes = await _rows(db, """
        SELECT rm.id,rm.bank_transaction_id,rm.target_type,rm.target_id,
               rm.confidence,rm.status,rm.confirmed_at,bt.data,bt.descricao,bt.valor
        FROM finance_reconciliation_matches rm
        LEFT JOIN bank_transactions bt ON bt.id=rm.bank_transaction_id
        WHERE (bt.data >= :inicio AND bt.data < :fim)
           OR (rm.confirmed_at >= :inicio AND rm.confirmed_at < :fim)
        ORDER BY COALESCE(rm.confirmed_at,bt.data),rm.id
    """, params)

    distribuicoes = await _rows(db, """
        SELECT id,mes_referencia,valor_total,status,socios_json,created_by,created_at
        FROM distribuicoes_lucro
        WHERE mes_referencia=:competencia
        ORDER BY created_at,id
    """, params)

    auditoria = await _rows(db, """
        SELECT id,user_id,user_role,acao,entidade,registro_id,detalhes,created_at
        FROM audit_logs
        WHERE created_at >= :inicio AND created_at < :fim
          AND entidade IN (
            'fees','fee_payments','fee_estornos','office_expenses',
            'partner_withdrawals','commission_payment_batches',
            'commission_adjustments','finance_month_closings',
            'finance_reconciliation_matches','distribuicao_lucro','documents'
          )
        ORDER BY created_at,id
    """, params)

    fechamento = (
        await db.execute(
            text("""
                SELECT id,competencia,snapshot_json,closed_by,closed_at
                FROM finance_month_closings
                WHERE competencia=:competencia
            """),
            {"competencia": competencia},
        )
    ).mappings().first()

    pacote = {
        "competencia": competencia,
        "gerado_em": date.today().isoformat(),
        "resumo": resumo,
        "fechamento": dict(fechamento) if fechamento else None,
        "receitas": receitas,
        "despesas": despesas,
        "comissoes": comissoes,
        "estornos": estornos,
        "conciliacoes": conciliacoes,
        "distribuicoes": distribuicoes,
        "auditoria": auditoria,
    }

    fin = resumo.get("financeiro", {})
    casos = resumo.get("casos", {})
    prazos = resumo.get("prazos", {})
    pdf = relatorio_mensal_pdf(
        mes,
        ano,
        {
            "novos_casos": int(casos.get("novos_mes") or 0),
            "casos_ativos": int(casos.get("ativos") or 0),
            "casos_encerrados": int(casos.get("encerrados_mes") or 0),
            "novos_clientes": 0,
            "honorarios_recebido": float(fin.get("recebido_mes") or 0),
            "honorarios_pendente": float(fin.get("pendente") or 0),
            "prazos_vencidos": int(prazos.get("vencidos_abertos") or 0),
        },
    )

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"financeiro-{competencia}/resumo.json",
            json.dumps(
                jsonable_encoder(pacote),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        zf.writestr(f"financeiro-{competencia}/relatorio.pdf", pdf)
        for nome, rows in (
            ("receitas.csv", receitas),
            ("despesas.csv", despesas),
            ("comissoes.csv", comissoes),
            ("estornos.csv", estornos),
            ("conciliacoes.csv", conciliacoes),
            ("distribuicoes.csv", distribuicoes),
            ("auditoria.csv", auditoria),
        ):
            zf.writestr(f"financeiro-{competencia}/{nome}", _csv_bytes(rows))
    return out.getvalue()
