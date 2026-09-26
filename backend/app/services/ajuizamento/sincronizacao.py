# ── app/services/ajuizamento/sincronizacao.py ────────────────────────────────
# JudicialSyncService — depois do protocolo, sincroniza o caso pelo número
# CNJ: fonte autenticada (MNI via fila, quando o tribunal está cadastrado)
# tem precedência; DataJud público complementa. Reaproveita a sincronização
# existente (datajud_service.sincronizar_caso → case_movimentos com dedupe
# por hash) e registra o resultado em judicial_sync_events.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.ajuizamento import JudicialFiling, JudicialSyncEvent
from app.models.case import Case
from app.services import datajud_service, processo_service
from app.services.case_integrity_service import sincronizar_processo_principal_do_caso
from app.services.ajuizamento.conectores.datajud import DataJudConnector
from app.services.tribunal_registry import resolver_tribunal

PRECEDENCIA_FONTES = ("pje_mni", "datajud")


class JudicialSyncService:
    def __init__(self, db: AsyncSession, settings: Settings, datajud: DataJudConnector | None = None) -> None:
        self.db = db
        self.settings = settings
        self._datajud = datajud or DataJudConnector()

    def _evento(self, filing: JudicialFiling, fonte: str, estado: str, novos: int, detalhe: str) -> JudicialSyncEvent:
        ev = JudicialSyncEvent(
            id=str(uuid4()), case_id=filing.case_id, filing_id=filing.id, cnj_number=filing.numero_cnj,
            fonte=fonte, estado=estado, movimentos_novos=novos, detalhe=detalhe[:2000],
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(ev)
        return ev

    async def sincronizar(self, filing: JudicialFiling) -> dict[str, Any]:
        """Retorna {fontes: [...], movimentos_novos, reconciliacao}. Commit do chamador."""
        saida: dict[str, Any] = {"fontes": [], "movimentos_novos": 0, "reconciliacao": None}
        if not filing.numero_cnj:
            self._evento(filing, "manual", "vazio", 0, "sem número CNJ — nada a sincronizar")
            saida["fontes"].append({"fonte": "manual", "estado": "vazio"})
            return saida
        case = (await self.db.execute(select(Case).where(Case.id == filing.case_id))).scalar_one_or_none()
        if case is None:
            return saida
        if not case.numero_processo:
            try:
                await sincronizar_processo_principal_do_caso(
                    self.db,
                    case_id=case.id,
                    numero_processo=filing.numero_cnj,
                    tribunal=filing.tribunal_code,
                    comarca=filing.jurisdicao,
                    tipo="judicial",
                )
            except processo_service.ProcessConflict:
                self._evento(
                    filing,
                    "integridade",
                    "conflito",
                    0,
                    "CNJ já vinculado a outro caso; sincronização automática interrompida",
                )
                saida["fontes"].append(
                    {"fonte": "integridade", "estado": "conflito"}
                )
                return saida

        # 1) Fonte autenticada (MNI) — só sinaliza: a leitura real é task Celery.
        tribunal = await resolver_tribunal(self.db, filing.numero_cnj, grau=filing.degree or "1")
        if tribunal is not None and self.settings.CELERY_ENABLED and self.settings.REDIS_URL:
            self._evento(filing, "pje_mni", "ok", 0,
                         "tribunal habilitado ao MNI — sincronização enfileirada por /processo-eletronico/sincronizar")
            saida["fontes"].append({"fonte": "pje_mni", "estado": "enfileirar", "tribunal_id": tribunal.id})
        else:
            self._evento(filing, "pje_mni", "desabilitado", 0, "tribunal não cadastrado ao MNI ou fila desligada")
            saida["fontes"].append({"fonte": "pje_mni", "estado": "desabilitado"})

        # 2) DataJud público (acompanhamento complementar) — dedupe já embutido.
        if self.settings.DATAJUD_ENABLED and self.settings.DATAJUD_API_KEY:
            try:
                novos = await datajud_service.sincronizar_caso(self.db, case)
                self._evento(filing, "datajud", "ok", novos, f"{novos} movimento(s) novo(s)")
                saida["fontes"].append({"fonte": "datajud", "estado": "ok", "movimentos_novos": novos})
                saida["movimentos_novos"] += novos
                rec = await self._datajud.reconcile_process(
                    filing.numero_cnj, {"classe": filing.classe_nome, "orgao": filing.jurisdicao},
                )
                saida["reconciliacao"] = rec.to_dict()
            except Exception as exc:  # noqa: BLE001 — falha da fonte não derruba o fluxo
                self._evento(filing, "datajud", "falha", 0, f"{type(exc).__name__}")
                saida["fontes"].append({"fonte": "datajud", "estado": "falha", "erro": type(exc).__name__})
        else:
            self._evento(filing, "datajud", "desabilitado", 0, "DATAJUD_ENABLED/DATAJUD_API_KEY ausentes")
            saida["fontes"].append({"fonte": "datajud", "estado": "desabilitado"})
        return saida


def evento_para_dict(e: JudicialSyncEvent) -> dict[str, Any]:
    return {
        "id": e.id, "case_id": e.case_id, "filing_id": e.filing_id, "cnj_number": e.cnj_number,
        "fonte": e.fonte, "estado": e.estado, "movimentos_novos": e.movimentos_novos, "detalhe": e.detalhe,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
