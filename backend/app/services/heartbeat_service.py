# ── app/services/heartbeat_service.py ────────────────────────────────────────
# Heartbeat honesto dos jobs do APScheduler (achado nº 1 da auditoria).
#
# Duas responsabilidades:
#   1. `registrar_heartbeat(db, job_name, status, detail=None)` — UPSERT best-effort
#      da última execução de um job (chamado ao FINAL de cada job crítico).
#   2. Lógica PURA de defasagem (`avaliar_job` / `avaliar_jobs`) consumida pela
#      Central de Diagnóstico e pelo painel status-captura para sinalizar jobs
#      que pararam de rodar (parada silenciosa do scheduler).
#
# O registro é best-effort: a falha do heartbeat NUNCA derruba o job — só loga.
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)


# ── Identificadores canônicos dos jobs monitorados ────────────────────────────
# Fonte única da verdade dos job_name: usados TANTO nas chamadas de heartbeat em
# scheduler.py QUANTO na avaliação de defasagem — evita strings soltas divergindo.
JOB_DJEN = "djen_intimacoes"
JOB_DATAJUD = "datajud_sync"
JOB_DIARIO = "diario_oficial"
JOB_PRAZOS_VENCIDOS = "prazos_vencidos"
JOB_PRAZOS_ALERTAS = "prazos_alertas"
JOB_AUDIENCIAS = "audiencias_agenda"
JOB_PRESCRICAO = "prescricao"


# Cadência esperada por job → limite de defasagem (horas). A folga acima do
# intervalo nominal absorve atraso de fila/reinício sem falso positivo:
#   - jobs DIÁRIOS  → 26h  (24h + 2h de folga)
#   - DataJud (2x/dia, 08h45 e 16h45) → 14h (maior gap entre execuções + folga)
#   - prescrição (SEMANAL, segundas) → 8 dias (192h)
_MAX_DIARIO = 26
_MAX_DATAJUD = 14
_MAX_SEMANAL = 24 * 8  # 192h

JOBS_MONITORADOS: dict[str, dict[str, Any]] = {
    JOB_DJEN: {
        "label": "Captura DJEN (intimações)",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 06h30",
    },
    JOB_DATAJUD: {
        "label": "Sincronização DataJud (movimentos)",
        "max_age_horas": _MAX_DATAJUD,
        "cadencia": "2x/dia 08h45 e 16h45",
    },
    JOB_DIARIO: {
        "label": "Monitor Diário Oficial (DOU)",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 06h00",
    },
    JOB_PRAZOS_VENCIDOS: {
        "label": "Marcação de prazos vencidos",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 07h10",
    },
    JOB_PRAZOS_ALERTAS: {
        "label": "Alertas de prazos (7/3/1 dia)",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 07h15",
    },
    JOB_AUDIENCIAS: {
        "label": "Alertas de audiências (agenda)",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 07h20",
    },
    JOB_PRESCRICAO: {
        "label": "Alertas de prescrição",
        "max_age_horas": _MAX_SEMANAL,
        "cadencia": "semanal (segundas 09h05)",
    },
}

# Domínio válido de status gravado.
_STATUS_VALIDOS = {"ok", "erro"}


def _resultado_djen_para_heartbeat(status_nominal: str) -> tuple[str, str]:
    """Converte as métricas acumuladas do DJEN em status/detail sanitizados.

    O scheduler legado informa apenas `ok`/`erro`. A fonte real da saúde passa a
    ser o resultado de todas as inscrições consultadas. Uma exceção externa ao
    laço continua prevalecendo e é registrada como código, nunca como mensagem
    bruta que possa conter OAB, e-mail, URL ou payload.
    """
    from app.services import djen_service

    resumo = djen_service.consumir_resumo_execucao()
    if status_nominal == "erro":
        erros = dict(resumo.get("erros") or {})
        erros["falha_job"] = erros.get("falha_job", 0) + 1
        resumo["erros"] = erros
        resumo["heartbeat_status"] = "erro"
        if resumo.get("resultado") == "configuracao_incompleta":
            resumo["resultado"] = "falha_job"
    return (
        resumo["heartbeat_status"],
        djen_service.codificar_resumo_heartbeat(resumo),
    )


# ── UPSERT best-effort ────────────────────────────────────────────────────────
async def registrar_heartbeat(
    db, job_name: str, status: str, detail: str | None = None
) -> bool:
    """Grava (UPSERT por job_name) a última execução do job.

    `status` ∈ {'ok', 'erro'}. Para o DJEN, `detail` contém sempre métricas
    sanitizadas da execução — inclusive quando a consulta válida retorna zero.
    Nos demais jobs, preserva o comportamento anterior.

    Best-effort: qualquer falha (tabela ausente, sessão em erro) é logada e não
    propaga. Retorna True se gravou, False caso contrário.
    """
    st = (status or "").strip().lower()
    if st not in _STATUS_VALIDOS:
        st = "erro" if st else "ok"

    if job_name == JOB_DJEN:
        st, detalhe = _resultado_djen_para_heartbeat(st)
    else:
        detalhe = detail or None

    if detalhe is not None:
        detalhe = str(detalhe)[:500]
    agora = datetime.now(timezone.utc)
    try:
        await db.execute(
            text(
                """
                INSERT INTO scheduler_heartbeat
                    (job_name, last_run_at, last_status, detail, updated_at)
                VALUES (:job, :agora, :status, :detail, :agora)
                ON CONFLICT (job_name) DO UPDATE SET
                    last_run_at = EXCLUDED.last_run_at,
                    last_status = EXCLUDED.last_status,
                    detail      = EXCLUDED.detail,
                    updated_at  = EXCLUDED.updated_at
                """
            ),
            {"job": job_name, "agora": agora, "status": st, "detail": detalhe},
        )
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001 — best-effort, nunca propaga
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("[Heartbeat] upsert de '%s' falhou: %s", job_name, e)
        return False


# ── Lógica PURA de defasagem ──────────────────────────────────────────────────
def _idade_horas(last_run_at: datetime, agora: datetime) -> float:
    """Horas decorridas desde `last_run_at` (tolera datetime naive → assume UTC)."""
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    return (agora - last_run_at).total_seconds() / 3600.0


def avaliar_job(
    last_run_at: datetime | None,
    last_status: str | None,
    *,
    max_age_horas: float,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Classifica um job em ok | defasado | nunca_executou | erro.

    - sem heartbeat             → 'nunca_executou'
    - último status 'erro'      → 'erro' (rodou, mas falhou)
    - idade > cadência esperada → 'defasado' (parou de rodar / silêncio)
    - caso contrário            → 'ok'
    """
    agora = agora or datetime.now(timezone.utc)
    if last_run_at is None:
        return {"status": "nunca_executou", "idade_horas": None}
    idade = _idade_horas(last_run_at, agora)
    idade_arred = round(idade, 1)
    if idade > max_age_horas:
        return {"status": "defasado", "idade_horas": idade_arred}
    if (last_status or "").strip().lower() == "erro":
        return {"status": "erro", "idade_horas": idade_arred}
    return {"status": "ok", "idade_horas": idade_arred}


def avaliar_jobs(
    heartbeats: dict[str, dict[str, Any]], agora: datetime | None = None
) -> list[dict[str, Any]]:
    """Avalia todos os jobs monitorados contra os heartbeats lidos do banco."""
    agora = agora or datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for job_name, cfg in JOBS_MONITORADOS.items():
        hb = heartbeats.get(job_name) or {}
        aval = avaliar_job(
            hb.get("last_run_at"),
            hb.get("last_status"),
            max_age_horas=cfg["max_age_horas"],
            agora=agora,
        )
        out.append(
            {
                "job_name": job_name,
                "label": cfg["label"],
                "cadencia": cfg["cadencia"],
                "status": aval["status"],
                "idade_horas": aval["idade_horas"],
                "max_age_horas": cfg["max_age_horas"],
                "last_run_at": hb.get("last_run_at"),
                "last_status": hb.get("last_status"),
                "detail": hb.get("detail"),
            }
        )
    return out
