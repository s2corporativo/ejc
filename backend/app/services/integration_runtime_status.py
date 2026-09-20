from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings



def _classificar_backup_estado(row: Any | None) -> dict[str, Any]:
    """Traduz telemetria persistida em estado seguro, sem expor erro bruto."""
    if not row:
        return {
            "state": "nunca_executou",
            "detail": "Backup habilitado, mas ainda não há execução registrada.",
        }

    status = str(row.get("last_status") or "").strip().lower()
    offsite_ok = row.get("offsite_ok")
    checked_at = row.get("last_run_at")

    if status == "sucesso" and offsite_ok is True:
        state = "ok"
        detail = "Último backup cifrado concluiu o envio offsite com sucesso."
    elif status == "erro":
        state = "erro"
        detail = "A última execução do backup registrou falha."
    elif status == "parcial" or offsite_ok is False:
        state = "alerta"
        detail = (
            "A última execução preservou estado local, mas o envio offsite "
            "não foi confirmado."
        )
    else:
        state = "alerta"
        detail = (
            "Há execução de backup registrada, mas a prova do envio offsite "
            "está incompleta."
        )

    return {
        "state": state,
        "detail": detail,
        "checked_at": checked_at.isoformat() if checked_at else None,
    }


async def coletar_estados_operacionais(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Lê estado persistido; não faz chamadas externas nem expõe erro bruto."""
    estados: dict[str, dict[str, Any]] = {}
    fontes_monitoradas = {
        "djen", "tjmg", "lexml",
        "stj", "planalto", "camara", "senado", "anpd", "normas_rfb",
    }
    try:
        from app.models.rag import FonteIngestao

        result = await db.execute(
            select(FonteIngestao).where(FonteIngestao.slug.in_(fontes_monitoradas))
        )
        encontradas: set[str] = set()
        for fonte in result.scalars().all():
            encontradas.add(fonte.slug)
            status = (fonte.ultimo_status or "").strip().lower()
            if status == "erro":
                state = "erro"
                detail = f"Última execução de {fonte.slug} falhou; consulte o diagnóstico da fonte."
            elif status == "parcial":
                state = "alerta"
                detail = f"Última execução de {fonte.slug} foi parcial; há itens/falhas a revisar."
            elif not bool(fonte.ja_produziu) and int(fonte.execucoes_zeradas_consecutivas or 0) >= 3:
                state = "sem_resultado"
                detail = (
                    f"{fonte.slug} executa, mas ainda não produziu registros válidos "
                    f"após {fonte.execucoes_zeradas_consecutivas} execuções consecutivas."
                )
            else:
                state = "ok"
                detail = f"Última execução persistida de {fonte.slug} sem falha registrada."
            estados[fonte.slug] = {
                "state": state,
                "detail": detail,
                "checked_at": fonte.ultima_execucao.isoformat() if fonte.ultima_execucao else None,
            }

        for slug in fontes_monitoradas - encontradas:
            estados[slug] = {
                "state": "nunca_executou",
                "detail": f"Fonte {slug} sem execução registrada no ambiente.",
            }
    except Exception:
        await db.rollback()

    try:
        from app.models.processo_eletronico import CredencialProcessoEletronico

        ativas = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(CredencialProcessoEletronico)
                    .where(CredencialProcessoEletronico.ativo.is_(True))
                )
            ).scalar()
            or 0
        )
        verificadas = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(CredencialProcessoEletronico)
                    .where(
                        CredencialProcessoEletronico.ativo.is_(True),
                        CredencialProcessoEletronico.ultima_verificacao.is_not(None),
                    )
                )
            ).scalar()
            or 0
        )
        estados["processo_eletronico"] = {
            "state": "ok" if verificadas else "nao_homologado",
            "detail": (
                f"Processo eletrônico com {verificadas} credencial(is) ativa(s) já verificadas."
                if verificadas
                else (
                    f"Há {ativas} credencial(is) MNI ativa(s), mas nenhuma possui verificação registrada."
                    if ativas
                    else "Infraestrutura MNI disponível, mas não há credencial ativa de tribunal."
                )
            ),
        }
    except Exception:
        await db.rollback()

    if get_settings().JUDICIAL_FILING_ENABLED:
        try:
            from app.models.ajuizamento import JudicialIntegrationProfile

            homologados = int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(JudicialIntegrationProfile)
                        .where(
                            JudicialIntegrationProfile.ativo.is_(True),
                            JudicialIntegrationProfile.homologated_at.is_not(None),
                            JudicialIntegrationProfile.authorized.is_(True),
                            JudicialIntegrationProfile.production_endpoint_verified.is_(True),
                            JudicialIntegrationProfile.credentials_valid.is_(True),
                            JudicialIntegrationProfile.filing_supported.is_(True),
                        )
                    )
                ).scalar()
                or 0
            )
            estados["ajuizamento"] = {
                "state": "ok" if homologados else "nao_homologado",
                "detail": (
                    f"Ajuizamento possui {homologados} perfil(is) integralmente homologado(s)."
                    if homologados
                    else (
                        "Ajuizamento habilitado sem perfil que reúna homologação, "
                        "autorização, endpoint de produção verificado, credencial válida "
                        "e suporte a protocolo."
                    )
                ),
            }
        except Exception:
            await db.rollback()

    if __import__("os").getenv("GOOGLE_DRIVE_ENABLED", "").strip().casefold() in {"1", "true", "yes", "on", "sim"}:
        try:
            existe = (await db.execute(text("SELECT to_regclass('public.google_drive_sync_state')"))).scalar()
            if not existe:
                estados["google_drive_knowledge"] = {"state": "nunca_executou", "detail": "Google Drive configurado, mas nenhuma sincronização Knowledge foi executada."}
            else:
                row = (await db.execute(text("SELECT last_sync_at,last_status FROM google_drive_sync_state ORDER BY last_sync_at DESC NULLS LAST LIMIT 1"))).first()
                if not row:
                    estados["google_drive_knowledge"] = {"state": "nunca_executou", "detail": "Google Drive Knowledge ainda não possui execução registrada."}
                else:
                    ultimo = (row[1] or "").strip().lower()
                    if ultimo in {"ok", "sucesso"}:
                        drive_state = "ok"
                        drive_detail = "Última sincronização Google Drive Knowledge concluída."
                    elif ultimo == "parcial":
                        drive_state = "alerta"
                        drive_detail = "Última sincronização Google Drive Knowledge foi parcial."
                    else:
                        drive_state = "erro"
                        drive_detail = "Última sincronização Google Drive Knowledge registrou falha."
                    estados["google_drive_knowledge"] = {
                        "state": drive_state,
                        "detail": drive_detail,
                        "checked_at": row[0].isoformat() if row[0] else None,
                    }
        except Exception:
            await db.rollback()
            estados["google_drive_knowledge"] = {"state": "alerta", "detail": "Não foi possível ler o estado persistido do Google Drive Knowledge."}

    if get_settings().BACKUP_ENABLED:
        try:
            existe = (
                await db.execute(
                    text("SELECT to_regclass('public.backup_drive_state')")
                )
            ).scalar()
            if not existe:
                estados["backup_offsite"] = _classificar_backup_estado(None)
            else:
                row = (
                    await db.execute(
                        text(
                            "SELECT last_run_at,last_status,offsite_ok "
                            "FROM backup_drive_state WHERE id = 1"
                        )
                    )
                ).mappings().first()
                estados["backup_offsite"] = _classificar_backup_estado(row)
        except Exception:
            await db.rollback()
            estados["backup_offsite"] = {
                "state": "alerta",
                "detail": (
                    "Backup habilitado, mas o estado operacional persistido "
                    "não pôde ser lido."
                ),
            }

    return estados


