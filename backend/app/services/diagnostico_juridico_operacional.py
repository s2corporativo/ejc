# ── app/services/diagnostico_juridico_operacional.py ─────────────────────────
"""Probe jurídico-operacional somente leitura, sem PII.

Não substitui os probes de infraestrutura/scheduler. Resume filas que exigem
tratamento humano ou confirmação fiscal e que podem gerar risco mesmo quando a
infraestrutura está tecnicamente saudável.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _ms(inicio: float) -> float:
    return round((time.perf_counter() - inicio) * 1000, 2)


async def diagnosticar(db: AsyncSession) -> dict[str, Any]:
    inicio = time.perf_counter()
    try:
        # Durante rollout, a aplicação pode iniciar antes de a migration desta
        # versão ter sido aplicada. A query fica num SAVEPOINT: se uma coluna
        # nova ainda não existir, o erro não envenena a sessão compartilhada da
        # Central de Diagnóstico nem obriga rollback da transação externa.
        async with db.begin_nested():
            row = (
                await db.execute(
                    text(
                        """
                        SELECT
                          (SELECT COUNT(*) FROM deadlines
                             WHERE deleted_at IS NULL
                               AND status = 'pendente'
                               AND confirmado = FALSE) AS prazos_nao_confirmados,
                          (SELECT COUNT(*) FROM deadlines
                             WHERE deleted_at IS NULL
                               AND status = 'pendente'
                               AND calculo_automatico = TRUE
                               AND ciencia_confirmada = FALSE) AS prazos_auto_sem_ciencia,
                          (SELECT COUNT(*) FROM djen_comunicacoes
                             WHERE processada = FALSE) AS intimacoes_pendentes,
                          (SELECT COUNT(*) FROM notas_fiscais_servico
                             WHERE status = 'cancelada'
                               AND cancelamento_tipo = 'registro_local'
                               AND cancelamento_fiscal_confirmado = FALSE) AS nfse_canceladas_localmente,
                          (SELECT COUNT(*) FROM office_contracts
                             WHERE deleted_at IS NULL
                               AND status = 'vigente'
                               AND end_date IS NOT NULL
                               AND end_date < CURRENT_DATE) AS contratos_vencidos,
                          (SELECT COUNT(*) FROM office_contracts
                             WHERE deleted_at IS NULL
                               AND status = 'vigente'
                               AND end_date IS NOT NULL
                               AND end_date >= CURRENT_DATE
                               AND end_date <= CURRENT_DATE
                                   + (alert_days_before * INTERVAL '1 day'))
                            AS contratos_em_alerta
                        """
                    )
                )
            ).mappings().one()
    except Exception as exc:
        # Não vaza SQL, stack trace, nomes de clientes/processos ou credenciais.
        return {
            "nome": "Saúde jurídico-operacional",
            "status": "alerta",
            "detalhe": "Métricas jurídico-operacionais ainda não estão disponíveis no schema atual.",
            "acao_sugerida": "Confirme que as migrations da versão foram aplicadas e execute o diagnóstico novamente.",
            "latencia_ms": _ms(inicio),
            "coletado_em": datetime.now(timezone.utc).isoformat(),
            "codigo": type(exc).__name__,
        }

    dados = {k: int(v or 0) for k, v in row.items()}
    criticos = dados["prazos_nao_confirmados"] + dados["prazos_auto_sem_ciencia"]
    atencao = (
        dados["intimacoes_pendentes"]
        + dados["nfse_canceladas_localmente"]
        + dados["contratos_vencidos"]
    )

    if criticos:
        status = "erro"
        detalhe = (
            f"Há {criticos} pendência(s) de prazo que exigem confirmação/ciência humana; "
            f"{dados['intimacoes_pendentes']} intimação(ões) DJEN ainda não tratada(s)."
        )
        acao = "Priorize Prazos e Intimações antes das rotinas administrativas."
    elif atencao:
        status = "alerta"
        detalhe = (
            f"Sem prazo automático crítico, mas há {dados['intimacoes_pendentes']} intimação(ões) pendente(s), "
            f"{dados['nfse_canceladas_localmente']} NFS-e com cancelamento apenas local e "
            f"{dados['contratos_vencidos']} contrato(s) vigente(s) com data final vencida."
        )
        acao = "Trate as filas administrativas/jurídicas sinalizadas e confirme o estado externo quando aplicável."
    else:
        status = "ok"
        detalhe = (
            "Nenhum prazo automático sem ciência/confirmação e nenhum cancelamento local de NFS-e ou contrato vencido detectado."
        )
        acao = "Nenhuma ação imediata; acompanhe os contratos dentro da janela de alerta."

    return {
        "nome": "Saúde jurídico-operacional",
        "status": status,
        "detalhe": detalhe,
        "acao_sugerida": acao,
        "latencia_ms": _ms(inicio),
        **dados,
        "coletado_em": datetime.now(timezone.utc).isoformat(),
    }
