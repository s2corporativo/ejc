"""Extensões jurídicas da Central de Diagnóstico.

Mantém o agregador técnico existente como fonte principal e acrescenta somente
sinais de alto impacto jurídico que não devem ficar escondidos em endpoints
separados: saúde do calendário de prazos e heartbeat do DOU.

Nenhum probe retorna keyword monitorada, conteúdo de publicação, número de
processo, cliente ou credencial.
"""
from __future__ import annotations

from typing import Any

from app.services import diagnostico_service
from app.services.deadline_calculator import calendario_runtime_status
from app.services.diario_oficial_service import status_dou


def _probe_calendario_prazos() -> dict[str, Any]:
    estado = calendario_runtime_status()
    status = str(estado.get("status") or "nao_inicializado")

    if status == "validado":
        return diagnostico_service._sub(
            "Calendário jurídico de prazos",
            "ok",
            "Feriados e suspensões de tribunal foram carregados no runtime atual.",
            "Nenhuma ação necessária.",
            feriados_ok=True,
            suspensoes_ok=True,
        )

    if status == "degradado":
        tipos = sorted(
            {
                str(v)
                for v in (
                    estado.get("feriados_erro_tipo"),
                    estado.get("suspensoes_erro_tipo"),
                )
                if v
            }
        )
        detalhe = (
            "Falha ao validar feriados e/ou suspensões no runtime. "
            "Cálculos dependentes de tribunal devem permanecer preliminares."
        )
        if tipos:
            detalhe += " Tipos técnicos: " + ", ".join(tipos) + "."
        return diagnostico_service._sub(
            "Calendário jurídico de prazos",
            "erro",
            detalhe,
            "Restabeleça a carga do calendário e reconfira prazos afetados antes de confirmação humana.",
            feriados_ok=estado.get("feriados_ok"),
            suspensoes_ok=estado.get("suspensoes_ok"),
        )

    return diagnostico_service._sub(
        "Calendário jurídico de prazos",
        "alerta",
        "Feriados e suspensões ainda não foram validados no runtime atual. "
        "O sistema não deve tratar cálculo dependente de tribunal como definitivo.",
        "Confirme a inicialização do calendário antes de validar prazos processuais.",
        feriados_ok=estado.get("feriados_ok"),
        suspensoes_ok=estado.get("suspensoes_ok"),
    )


def _probe_dou_runtime() -> dict[str, Any]:
    estado = status_dou()
    status = str(estado.get("status") or "nunca_executado")
    ultima = estado.get("ultima_execucao")
    falhas = int(estado.get("falhas_consecutivas") or 0)

    if status == "ok":
        quantidade = int(estado.get("ultima_quantidade") or 0)
        return diagnostico_service._sub(
            "DOU — heartbeat de captura",
            "ok",
            f"Última consulta técnica concluída com sucesso; {quantidade} resultado(s) normalizado(s).",
            "Nenhuma ação necessária.",
            ultima_execucao=ultima,
            falhas_consecutivas=0,
        )

    if status == "degradado":
        erro_tipo = str(estado.get("ultimo_erro_tipo") or "erro técnico")
        severidade = "erro" if falhas >= 3 else "alerta"
        return diagnostico_service._sub(
            "DOU — heartbeat de captura",
            severidade,
            f"A fonte DOU está degradada; {falhas} falha(s) consecutiva(s). "
            f"Tipo técnico mais recente: {erro_tipo}.",
            "Verifique conectividade/contrato da fonte. Não interprete ausência de publicação como resultado válido enquanto o heartbeat estiver degradado.",
            ultima_execucao=ultima,
            falhas_consecutivas=falhas,
        )

    return diagnostico_service._sub(
        "DOU — heartbeat de captura",
        "desligado",
        "Nenhuma execução do monitor DOU foi registrada neste processo desde a inicialização.",
        "Se houver monitoramento DOU ativo, confirme o scheduler e a primeira execução do job.",
        ultima_execucao=None,
        falhas_consecutivas=0,
    )


async def diagnostico_completo_com_juridico(db=None) -> dict[str, Any]:
    """Agrega saúde técnica existente e sinais jurídicos críticos."""
    payload = await diagnostico_service.diagnostico_completo(db)
    subsistemas = list(payload.get("subsistemas") or [])
    subsistemas.extend([_probe_calendario_prazos(), _probe_dou_runtime()])
    geral, resumo = diagnostico_service.agregar(subsistemas)

    return {
        **payload,
        "status_geral": geral,
        "resumo": resumo,
        "subsistemas": subsistemas,
    }
