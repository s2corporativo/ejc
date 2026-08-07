# ── app/tasks/processo_eletronico_tasks.py ───────────────────────────────────
# Tasks Celery da integração de processo eletrônico via MNI 2.2.2 — Issue
# #762, Fase A (SOMENTE LEITURA).
#
# Toda chamada SOAP ao MNI acontece aqui, nunca em request HTTP síncrona
# (ver MNIConnector). Erros por documento são isolados no mapper (não
# abortam a sincronização inteira); indisponibilidade do tribunal (erro de
# transporte/protocolo) tem retry com backoff exponencial.
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.celery_app import celery_app

logger = logging.getLogger("ejc.tasks.processo_eletronico")


async def _com_engine_limpo(coro):
    from app.core.database import engine
    try:
        return await coro
    finally:
        await engine.dispose()


async def _sincronizar_processo(case_id: str, numero_cnj: str) -> dict:
    from app.core.database import AsyncSessionLocal
    from app.models.audit_log import criar_audit_log
    from app.models.case import Case
    from app.models.processo_eletronico import (
        CredencialProcessoEletronico, SincronizacaoProcessoEletronico,
        StatusSincronizacaoProcesso,
    )
    from app.services import processo_eletronico_credential_service as cred_service
    from app.services import processo_eletronico_document_mapper as mapper
    from app.services import tribunal_registry
    from app.services.mni_connector import (
        MNIConnector, MNIConnectorError, MNICredencial,
    )

    async with AsyncSessionLocal() as db:
        case = (await db.execute(
            select(Case).where(Case.id == case_id, Case.deleted_at.is_(None))
        )).scalar_one_or_none()
        if case is None:
            raise ValueError(f"Caso {case_id} não encontrado")

        sync = (await db.execute(
            select(SincronizacaoProcessoEletronico).where(
                SincronizacaoProcessoEletronico.case_id == case_id,
            )
        )).scalar_one_or_none()
        if sync is None:
            sync = SincronizacaoProcessoEletronico(
                id=str(uuid4()), case_id=case_id,
                status=StatusSincronizacaoProcesso.sincronizando,
            )
            db.add(sync)
        else:
            sync.status = StatusSincronizacaoProcesso.sincronizando
            sync.mensagem_erro = None
        sync.numero_cnj = numero_cnj
        await db.commit()

        try:
            tribunal = await tribunal_registry.resolver_tribunal(db, numero_cnj)
            if tribunal is None:
                raise ValueError(
                    f"Tribunal não habilitado ao MNI para o número {numero_cnj}"
                )
            sync.tribunal_id = tribunal.id

            credencial_row = (await db.execute(
                select(CredencialProcessoEletronico).where(
                    CredencialProcessoEletronico.tribunal_id == tribunal.id,
                    CredencialProcessoEletronico.advogado_id == case.advogado_responsavel_id,
                    CredencialProcessoEletronico.ativo.is_(True),
                )
            )).scalar_one_or_none()
            if credencial_row is None:
                raise ValueError(
                    "Nenhuma credencial MNI ativa para o advogado responsável "
                    f"neste tribunal (case={case_id})"
                )

            credencial = MNICredencial(
                id_consultante=cred_service.decifrar_id_consultante(
                    credencial_row.id_consultante_cifrado) or "",
                senha_consultante=cred_service.decifrar_senha(
                    credencial_row.senha_consultante_ref) or "",
            )
            connector = MNIConnector(tribunal.endpoint_wsdl, credencial)
            resultado = connector.consultar_processo(numero_cnj)

            if not resultado.sucesso:
                raise MNIConnectorError(resultado.mensagem or "Consulta recusada pelo tribunal")

            contagem = await mapper.aplicar_resultado_consulta(
                db, case, tribunal.id, resultado,
                uploaded_by=case.advogado_responsavel_id,
            )
            sync.status = StatusSincronizacaoProcesso.sincronizado
            sync.docs_novos = contagem["docs_novos"]
            sync.last_synced_at = datetime.now(timezone.utc)
            sync.mensagem_erro = None

            await criar_audit_log(
                db, case.advogado_responsavel_id, None, "PROCESSO_ELETRONICO_SYNC",
                "cases", case_id,
                detalhes=(
                    f"Sincronização MNI {numero_cnj}: "
                    f"{contagem['docs_novos']} doc(s) novo(s), "
                    f"{contagem['andamentos_novos']} andamento(s) novo(s)"
                ),
            )
            await db.commit()
            return {"case_id": case_id, "status": "sincronizado", **contagem}
        except Exception as e:  # noqa: BLE001 — sempre grava o erro antes de propagar
            await db.rollback()
            sync.status = StatusSincronizacaoProcesso.erro
            sync.mensagem_erro = str(e)[:2000]
            db.add(sync)
            try:
                await criar_audit_log(
                    db, case.advogado_responsavel_id, None,
                    "PROCESSO_ELETRONICO_SYNC_ERRO", "cases", case_id,
                    detalhes=f"Sincronização MNI {numero_cnj} falhou: {e}",
                )
            except Exception:  # noqa: BLE001 — auditoria best-effort
                logger.error("[MNI] falha ao auditar erro de sync", exc_info=True)
            await db.commit()
            raise


@celery_app.task(
    name="app.tasks.sincronizar_processo",
    bind=True, max_retries=4, default_retry_delay=60,
    retry_backoff=True, retry_backoff_max=900, retry_jitter=True,
)
def sincronizar_processo_task(self, case_id: str, numero_cnj: str) -> dict:
    """Sincroniza um caso com o processo eletrônico via MNI. Retry com
    backoff exponencial só cobre indisponibilidade de transporte do tribunal
    (MNIConnectorError); erro de dado (caso/credencial não encontrado) não
    adianta retry — falha direto."""
    from app.services.mni_connector import MNIConnectorError
    try:
        return asyncio.run(_com_engine_limpo(_sincronizar_processo(case_id, numero_cnj)))
    except MNIConnectorError as exc:
        logger.warning(
            "[MNI] sincronizar_processo case=%s falhou (tribunal indisponível), "
            "retry: %s", case_id, exc,
        )
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error(
            "[MNI] sincronizar_processo case=%s falhou (sem retry): %s",
            case_id, exc,
        )
        raise


async def _sincronizar_avisos(advogado_id: str) -> dict:
    from app.core.database import AsyncSessionLocal
    from app.models.audit_log import criar_audit_log
    from app.models.processo_eletronico import CredencialProcessoEletronico
    from app.services import processo_eletronico_credential_service as cred_service
    from app.services.mni_connector import MNIConnector, MNICredencial

    total_avisos = 0
    erros: list[str] = []

    async with AsyncSessionLocal() as db:
        credenciais = (await db.execute(
            select(CredencialProcessoEletronico).where(
                CredencialProcessoEletronico.advogado_id == advogado_id,
                CredencialProcessoEletronico.ativo.is_(True),
            )
        )).scalars().all()

        for credencial_row in credenciais:
            tribunal = credencial_row.tribunal
            try:
                credencial = MNICredencial(
                    id_consultante=cred_service.decifrar_id_consultante(
                        credencial_row.id_consultante_cifrado) or "",
                    senha_consultante=cred_service.decifrar_senha(
                        credencial_row.senha_consultante_ref) or "",
                )
                connector = MNIConnector(tribunal.endpoint_wsdl, credencial)
                avisos = connector.consultar_avisos_pendentes()
                total_avisos += len(avisos)
                credencial_row.ultima_verificacao = datetime.now(timezone.utc)
            except Exception as e:  # noqa: BLE001 — um tribunal com erro não trava os demais
                erros.append(f"{tribunal.nome if tribunal else credencial_row.tribunal_id}: {e}")
                logger.error(
                    "[MNI] consultar_avisos_pendentes falhou (advogado=%s, "
                    "tribunal=%s): %s", advogado_id, credencial_row.tribunal_id, e,
                )

        await criar_audit_log(
            db, advogado_id, None, "PROCESSO_ELETRONICO_AVISOS_SYNC", "users",
            advogado_id,
            detalhes=f"{total_avisos} aviso(s) pendente(s), {len(erros)} erro(s)",
        )
        await db.commit()

    return {"advogado_id": advogado_id, "total_avisos": total_avisos, "erros": erros}


@celery_app.task(
    name="app.tasks.sincronizar_avisos",
    bind=True, max_retries=3, default_retry_delay=60,
    retry_backoff=True, retry_backoff_max=600, retry_jitter=True,
)
def sincronizar_avisos_task(self, advogado_id: str) -> dict:
    """Consulta avisos/intimações pendentes em todos os tribunais com
    credencial MNI ativa deste advogado. Erro em UM tribunal não aborta os
    demais (isolado dentro de _sincronizar_avisos); a task só faz retry se
    a rodada inteira levantar uma exceção não tratada."""
    try:
        return asyncio.run(_com_engine_limpo(_sincronizar_avisos(advogado_id)))
    except Exception as exc:
        logger.warning(
            "[MNI] sincronizar_avisos advogado=%s falhou, retry: %s",
            advogado_id, exc,
        )
        raise self.retry(exc=exc)
