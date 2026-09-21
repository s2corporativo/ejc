# ── app/services/heartbeat_service.py ────────────────────────────────────────
# Heartbeat honesto dos jobs do APScheduler.
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

JOB_DJEN = "djen_intimacoes"
JOB_DATAJUD = "datajud_sync"
JOB_DIARIO = "diario_oficial"
JOB_PRAZOS_VENCIDOS = "prazos_vencidos"
JOB_PRAZOS_ALERTAS = "prazos_alertas"
JOB_AUDIENCIAS = "audiencias_agenda"
JOB_PRESCRICAO = "prescricao"
JOB_ENTRADA_EXPURGO = "entrada_expurgo"
JOB_BACKUP_DRIVE = "backup_drive"
JOB_REEMBED_RAG = "reembed_rag_orfaos"
JOB_QUERIDO_DIARIO = "querido_diario_monitor"
JOB_RADAR_LEGISLATIVO = "radar_legislativo"
JOB_JURIMETRIA_SNAPSHOT = "jurimetria_tribunais_snapshot"

_MAX_DIARIO = 26
_MAX_DATAJUD = 14
_MAX_SEMANAL = 24 * 8

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
    # Estava definido (JOB_ENTRADA_EXPURGO) e batendo ponto em
    # scheduler.job_expurgo_entrada_unica, mas FORA deste dict: o job registrava
    # execução e o painel nunca o avaliava. Cadência lida do add_job real
    # (scheduler: CronTrigger(hour=3, minute=50)); o gate interno
    # ENTRADA_EXPURGO_ENABLED é opt-in (default False) — enquanto desligado, o
    # job não bate ponto e o painel mostra "nunca_executou", que é a leitura
    # honesta: o expurgo LGPD não está acontecendo.
    JOB_ENTRADA_EXPURGO: {
        "label": "Expurgo LGPD da Entrada Única",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 03h50",
    },
    # F4 (análise E2E 03/09/2026): o backup — o job cuja falha é a mais cara —
    # e o auto-reembed do RAG não tinham heartbeat; o painel mandava "ler o
    # log". Ambos passam a ser monitorados por resultado.
    JOB_BACKUP_DRIVE: {
        "label": "Backup offsite (Drive/rclone)",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário (BACKUP_HORA_LOCAL)",
    },
    JOB_REEMBED_RAG: {
        "label": "Auto-reindex do RAG (chunks órfãos)",
        "max_age_horas": 3,
        "cadencia": "horário (:20)",
    },
    JOB_QUERIDO_DIARIO: {
        "label": "Monitor de diários oficiais municipais (Querido Diário)",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 11h00 UTC",
    },
    JOB_RADAR_LEGISLATIVO: {
        "label": "Radar Legislativo (Câmara, Senado, ALMG)",
        "max_age_horas": _MAX_DIARIO,
        "cadencia": "diário 07h00 UTC",
    },
    JOB_JURIMETRIA_SNAPSHOT: {
        "label": "Snapshot agregado da jurimetria dos tribunais",
        "max_age_horas": _MAX_SEMANAL,
        "cadencia": "semanal (sábados 06h00)",
    },
}

#: Job de captura/ingestão → slug da fonte correspondente em `fontes_ingestao`.
#: Fecha a armadilha confirmada pela auditoria ("captura DJEN reporta ok há
#: meses sem nunca ter capturado nada"): o heartbeat afere EXECUÇÃO; a saúde
#: da fonte (services/ingestao_saude.py) afere RESULTADO. Um job que roda em
#: dia mas cuja fonte está `nunca_produziu`/`parou_de_produzir` não pode
#: aparecer "ok" no painel.
#: Jobs sem fonte mapeada (alertas de prazos, DOU — que não registra linha em
#: fontes_ingestao) mantêm o comportamento por execução.
FONTE_POR_JOB: dict[str, str] = {
    JOB_DJEN: "djen",                    # ingestor DJEN (comunicações → RAG)
    JOB_DATAJUD: "datajud_processos",    # feed cognitivo DataJud/CNJ
}

_STATUS_VALIDOS = {"ok", "erro"}


async def _quantidade_oabs_elegiveis(db) -> int | None:
    """Espelha exatamente o contrato operacional da captura.

    A consulta roda em savepoint. Se o schema mínimo não possuir ``users``, o
    savepoint é revertido e o UPSERT do heartbeat continua utilizável na mesma
    sessão, inclusive em PostgreSQL.
    """
    try:
        async with db.begin_nested():
            resultado = await db.execute(
                text(
                    """
                    SELECT count(*) FROM users
                    WHERE deleted_at IS NULL
                      AND is_active = TRUE
                      AND length(trim(coalesce(djen_oab_numero, ''))) > 0
                      AND length(trim(coalesce(djen_oab_uf, ''))) > 0
                    """
                )
            )
            return int(resultado.scalar() or 0)
    except Exception:
        return None


async def _normalizar_resultado_djen(
    db,
    status_nominal: str,
    detail_nominal: str | None,
) -> tuple[str, str | None]:
    """Troca o status nominal pela produtividade real da task agendada."""
    from app.services import djen_service

    resultados = djen_service.consumir_resultados_execucao()
    if resultados:
        resumo = djen_service.resumir_execucao(resultados)
        for resultado in resultados:
            if resultado.fonte_ok:
                await djen_service.enviar_emails_pendentes(resultado)
    else:
        quantidade = await _quantidade_oabs_elegiveis(db)
        if quantidade is None:
            # Contrato genérico/ambiente com apenas scheduler_heartbeat.
            return status_nominal, detail_nominal
        resumo = djen_service.resumir_execucao([])
        if quantidade > 0:
            resumo.update(
                {
                    "resultado": "falha_job",
                    "oabs_elegiveis": quantidade,
                    "oabs_falha": quantidade,
                    "erros": {"sem_metricas_da_execucao": 1},
                }
            )

    if status_nominal == "erro":
        erros = dict(resumo.get("erros") or {})
        erros["falha_job"] = erros.get("falha_job", 0) + 1
        resumo["erros"] = erros
        resumo["heartbeat_status"] = "erro"
        resumo["resultado"] = "falha_job"
        if detail_nominal:
            logger.warning("DJEN: job encerrou com falha sanitizada")

    return (
        resumo["heartbeat_status"],
        djen_service.codificar_resumo_heartbeat(resumo),
    )


async def registrar_heartbeat(
    db,
    job_name: str,
    status: str,
    detail: str | None = None,
) -> bool:
    """UPSERT best-effort da última execução do job."""
    st = (status or "").strip().lower()
    if st not in _STATUS_VALIDOS:
        st = "erro" if st else "ok"

    if job_name == JOB_DJEN:
        st, detalhe = await _normalizar_resultado_djen(db, st, detail)
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
            {
                "job": job_name,
                "agora": agora,
                "status": st,
                "detail": detalhe,
            },
        )
        await db.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort, nunca propaga
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning("[Heartbeat] upsert de '%s' falhou: %s", job_name, exc)
        return False


def _idade_horas(last_run_at: datetime, agora: datetime) -> float:
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
    saude_fonte: Any = None,
) -> dict[str, Any]:
    """Estado do job: execução (cadência/erro) cruzada com RESULTADO.

    `saude_fonte` é o veredito da fonte correspondente em fontes_ingestao
    (ingestao_saude.SaudeFonte ou dict equivalente), quando o job tem uma.
    Um job que roda em dia ("ok" pela execução) mas cuja fonte está em
    situação CRÍTICA (`nunca_produziu`, `parou_de_produzir`, `erro`...) é
    rebaixado para "sem_resultado", com o motivo explícito — rodar sem
    entregar não é "ok". Sem `saude_fonte`, comportamento por execução
    preservado (jobs sem fonte mapeada).
    """
    agora = agora or datetime.now(timezone.utc)
    if last_run_at is None:
        return {"status": "nunca_executou", "idade_horas": None}
    idade = _idade_horas(last_run_at, agora)
    idade_arredondada = round(idade, 1)
    if idade > max_age_horas:
        return {"status": "defasado", "idade_horas": idade_arredondada}
    if (last_status or "").strip().lower() == "erro":
        return {"status": "erro", "idade_horas": idade_arredondada}
    if saude_fonte is not None:
        critico = bool(_saude_attr(saude_fonte, "critico"))
        if critico:
            situacao = str(_saude_attr(saude_fonte, "situacao") or "critica")
            motivo = str(_saude_attr(saude_fonte, "motivo") or "").strip()
            return {
                "status": "sem_resultado",
                "idade_horas": idade_arredondada,
                "fonte_situacao": situacao,
                "motivo": (
                    f"Job executou em dia, mas a fonte correspondente está "
                    f"'{situacao}'" + (f": {motivo}" if motivo else ".")
                ),
            }
    return {"status": "ok", "idade_horas": idade_arredondada}


def _saude_attr(saude: Any, campo: str) -> Any:
    """Lê um campo do veredito de saúde (aceita SaudeFonte ou dict)."""
    if isinstance(saude, dict):
        return saude.get(campo)
    return getattr(saude, campo, None)


def avaliar_jobs(
    heartbeats: dict[str, dict[str, Any]],
    agora: datetime | None = None,
    saudes_fontes: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Avalia os jobs monitorados cruzando execução com resultado.

    `saudes_fontes` — vereditos de ingestao_saude indexados por slug de fonte
    (ver FONTE_POR_JOB). Ausente ou sem o slug do job, a avaliação fica só na
    execução (comportamento anterior).
    """
    agora = agora or datetime.now(timezone.utc)
    saudes_fontes = saudes_fontes or {}
    saida: list[dict[str, Any]] = []
    for job_name, config in JOBS_MONITORADOS.items():
        heartbeat = heartbeats.get(job_name) or {}
        fonte_slug = FONTE_POR_JOB.get(job_name)
        avaliacao = avaliar_job(
            heartbeat.get("last_run_at"),
            heartbeat.get("last_status"),
            max_age_horas=config["max_age_horas"],
            agora=agora,
            saude_fonte=saudes_fontes.get(fonte_slug) if fonte_slug else None,
        )
        saida.append(
            {
                "job_name": job_name,
                "label": config["label"],
                "cadencia": config["cadencia"],
                "status": avaliacao["status"],
                "idade_horas": avaliacao["idade_horas"],
                "max_age_horas": config["max_age_horas"],
                "last_run_at": heartbeat.get("last_run_at"),
                "last_status": heartbeat.get("last_status"),
                "detail": heartbeat.get("detail"),
                # Cruzamento execução × resultado (None quando não se aplica):
                "fonte_slug": fonte_slug,
                "fonte_situacao": avaliacao.get("fonte_situacao"),
                "motivo": avaliacao.get("motivo"),
            }
        )
    return saida
