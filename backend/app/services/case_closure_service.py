"""Diagnóstico operacional para o fechamento de casos.

A regra é deliberadamente determinística: nenhum modelo de IA decide se um caso
pode ser encerrado. Prazos ativos bloqueiam o fechamento; outras pendências
relevantes viram alertas que exigem confirmação humana explícita.

Este serviço não faz commit. O advisory lock por caso é transacional e existe
para impedir que um prazo seja criado/alterado entre o diagnóstico e o commit do
encerramento; persistência e AuditLog continuam pertencendo ao router.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee import Fee, FeeStatus
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.process import Process
from app.models.task import Task, TaskStatus
from app.services.case_mutation_guard import (
    garantir_caso_editavel,
    serializar_mutacao_caso,
)


_URL_RE = re.compile(r"https?://\S+")


def _resumir_erro(erro: Any) -> str | None:
    """Erro de sync sem host/URL upstream e truncado — vai para a UI."""
    if not erro:
        return None
    texto = _URL_RE.sub("<url>", str(erro)).strip()
    return texto[:200] + ("…" if len(texto) > 200 else "")


async def diagnosticar_fechamento(
    db: AsyncSession, caso: Any, *, somente_leitura: bool = False
) -> dict[str, Any]:
    """Retorna bloqueios e alertas operacionais do caso sem persistir nada.

    Bloqueio fatal:
    - prazo pendente ou vencido, inclusive prazo de IA ainda não confirmado.

    Alertas com confirmação explícita:
    - tarefas abertas;
    - honorários pendentes/atrasados;
    - peças ainda não protocoladas em estados de produção/revisão;
    - próxima ação ainda preenchida no caso;
    - processo judicial ainda ativo (sugere "sincronizar antes de encerrar").

    Conteúdo retornado é limitado a metadados operacionais já pertencentes ao
    caso. O chamador deve aplicar ownership antes de expor o resultado.
    """
    case_id = str(caso.id)

    # O mesmo lock é usado pelas mutações fatais de prazo. No POST /encerrar ele
    # permanece retido até o commit do router, fechando a janela de corrida entre
    # "diagnóstico limpo" e a troca de status para encerrado. No GET de
    # diagnóstico não há mutação — sem lock, para não serializar o caso.
    if not somente_leitura:
        await serializar_mutacao_caso(db, case_id)
    refresh = getattr(db, "refresh", None)
    if refresh is not None:
        await refresh(caso)
    garantir_caso_editavel(caso)

    bloqueios: list[dict[str, Any]] = []
    alertas: list[dict[str, Any]] = []

    prazos = (
        await db.execute(
            select(Deadline).where(
                Deadline.case_id == case_id,
                Deadline.deleted_at.is_(None),
                Deadline.status.in_([DeadlineStatus.pendente, DeadlineStatus.vencido]),
            )
        )
    ).scalars().all()
    for prazo in prazos:
        status = prazo.status.value if hasattr(prazo.status, "value") else str(prazo.status)
        sufixo = " · a confirmar" if not bool(prazo.confirmado) else ""
        bloqueios.append(
            {
                "codigo": "prazo_ativo",
                "tipo": "prazo",
                "id": prazo.id,
                "titulo": prazo.titulo,
                "descricao": f"Prazo {status}: {prazo.data_prazo}{sufixo}",
                "destino": f"/casos/{case_id}?tab=timeline",
            }
        )

    tarefas = (
        await db.execute(
            select(Task).where(
                Task.case_id == case_id,
                Task.deleted_at.is_(None),
                Task.status.in_([TaskStatus.a_fazer, TaskStatus.fazendo]),
            )
        )
    ).scalars().all()
    for tarefa in tarefas:
        status = tarefa.status.value if hasattr(tarefa.status, "value") else str(tarefa.status)
        alertas.append(
            {
                "codigo": "tarefa_aberta",
                "tipo": "tarefa",
                "id": tarefa.id,
                "titulo": tarefa.titulo,
                "descricao": f"Tarefa {status.replace('_', ' ')}",
                "destino": f"/casos/{case_id}?tab=timeline",
            }
        )

    honorarios = (
        await db.execute(
            select(Fee).where(
                Fee.case_id == case_id,
                Fee.deleted_at.is_(None),
                Fee.status.in_([FeeStatus.pendente, FeeStatus.atrasado]),
            )
        )
    ).scalars().all()
    for honorario in honorarios:
        status = (
            honorario.status.value
            if hasattr(honorario.status, "value")
            else str(honorario.status)
        )
        alertas.append(
            {
                "codigo": "financeiro_pendente",
                "tipo": "honorario",
                "id": honorario.id,
                "titulo": honorario.descricao,
                "descricao": f"Honorário {status}",
                "destino": f"/casos/{case_id}?tab=financeiro",
            }
        )

    pecas = (
        await db.execute(
            select(LegalDoc).where(
                LegalDoc.case_id == case_id,
                LegalDoc.deleted_at.is_(None),
                LegalDoc.status.in_(
                    [
                        PecaStatus.rascunho,
                        PecaStatus.em_revisao,
                        PecaStatus.corrigida,
                        PecaStatus.aprovada,
                        PecaStatus.final,
                    ]
                ),
            )
        )
    ).scalars().all()
    for peca in pecas:
        status = peca.status.value if hasattr(peca.status, "value") else str(peca.status)
        alertas.append(
            {
                "codigo": "peca_nao_protocolada",
                "tipo": "peca",
                "id": peca.id,
                "titulo": peca.titulo,
                "descricao": f"Peça {status.replace('_', ' ')}",
                "destino": f"/casos/{case_id}?tab=documentos",
            }
        )

    proxima_acao = (getattr(caso, "proxima_acao", None) or "").strip()
    if proxima_acao:
        alertas.append(
            {
                "codigo": "proxima_acao_pendente",
                "tipo": "proxima_acao",
                "id": case_id,
                "titulo": "Próxima ação ainda definida",
                "descricao": proxima_acao,
                "destino": f"/casos/{case_id}?tab=resumo",
            }
        )

    processos = (
        await db.execute(
            select(Process).where(
                Process.case_id == case_id,
                Process.deleted_at.is_(None),
                Process.status == "ativo",
            )
        )
    ).scalars().all()
    for processo in processos:
        alertas.append(
            {
                "codigo": "processo_ativo",
                "tipo": "processo",
                "id": processo.id,
                "titulo": processo.numero_cnj or "Processo sem número CNJ",
                "descricao": (
                    "Processo judicial ainda ativo no caso — sincronize e "
                    "confirme o desfecho (trânsito/arquivamento) antes de encerrar"
                ),
                "destino": f"/casos/{case_id}?tab=processos",
            }
        )

    numero_processo = (getattr(caso, "numero_processo", None) or "").strip()
    last_synced_at = getattr(caso, "last_synced_at", None)
    processo_info = {
        "numero_processo": numero_processo or None,
        "processos_ativos": len(processos),
        "pode_sincronizar": bool(numero_processo),
        "ultima_sincronizacao": (
            last_synced_at.isoformat() if hasattr(last_synced_at, "isoformat") else last_synced_at
        ),
        "erro_sincronizacao": _resumir_erro(getattr(caso, "sync_error", None)),
    }

    resumo = {
        "prazos_ativos": len(prazos),
        "prazos_nao_confirmados": sum(1 for p in prazos if not bool(p.confirmado)),
        "tarefas_abertas": len(tarefas),
        "financeiro_pendente": len(honorarios),
        "pecas_nao_protocoladas": len(pecas),
        "proxima_acao_pendente": bool(proxima_acao),
        "processos_ativos": len(processos),
    }
    return {
        "case_id": case_id,
        "pode_encerrar": not bloqueios,
        "requer_confirmacao_alertas": bool(alertas),
        "bloqueios": bloqueios,
        "alertas": alertas,
        "resumo": resumo,
        "processo": processo_info,
    }
