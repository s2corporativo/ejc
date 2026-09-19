from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


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
        qtd = int((await db.execute(
            select(func.count()).select_from(CredencialProcessoEletronico).where(CredencialProcessoEletronico.ativo.is_(True))
        )).scalar() or 0)
        estados["processo_eletronico"] = {
            "state": "ok" if qtd else "nao_homologado",
            "detail": f"Processo eletrônico com {qtd} credencial(is) ativa(s)." if qtd else "Infraestrutura MNI disponível, mas não há credencial ativa de tribunal.",
        }
    except Exception:
        await db.rollback()

    if get_settings().JUDICIAL_FILING_ENABLED:
        try:
            from app.models.ajuizamento import JudicialIntegrationProfile
            qtd = int((await db.execute(
                select(func.count()).select_from(JudicialIntegrationProfile).where(JudicialIntegrationProfile.ativo.is_(True))
            )).scalar() or 0)
            estados["ajuizamento"] = {
                "state": "ok" if qtd else "nao_homologado",
                "detail": f"Ajuizamento possui {qtd} perfil(is) ativo(s) de tribunal." if qtd else "Ajuizamento habilitado sem perfil de tribunal ativo/homologado.",
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
    return estados


