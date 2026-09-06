# ── app/services/ajuizamento/conectores/roteador.py ──────────────────────────
# JudicialConnectorRouter — resolve o conector pelo sistema do destino e
# monta o ContextoConector (perfil + disponibilidade de credencial). Também
# calcula a matriz completa (todos os conectores × perfil) para o painel.
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.ajuizamento.capacidades import ContextoConector, MatrizCapacidades
from app.services.ajuizamento.conectores.base import ConectorJudicial
from app.services.ajuizamento.conectores.datajud import DataJudConnector
from app.services.ajuizamento.conectores.eproc import EprocConnector
from app.services.ajuizamento.conectores.pdpj import PDPJConnector
from app.services.ajuizamento.conectores.pje_mni import PJeMniConnector
from app.services.ajuizamento import perfis as perfis_service


class SistemaNaoSuportado(ValueError):
    pass


class JudicialConnectorRouter:
    def __init__(self, conectores: dict[str, ConectorJudicial] | None = None) -> None:
        self._conectores: dict[str, ConectorJudicial] = conectores or {
            c.chave: c for c in (PDPJConnector(), PJeMniConnector(), EprocConnector(), DataJudConnector())
        }

    @property
    def chaves(self) -> tuple[str, ...]:
        return tuple(self._conectores)

    def conector(self, sistema: str | None) -> ConectorJudicial:
        if not sistema or sistema not in self._conectores:
            raise SistemaNaoSuportado(f"sistema judicial não suportado: {sistema!r}")
        return self._conectores[sistema]

    @staticmethod
    def credencial_disponivel(settings: Settings, perfil: Any | None, sistema: str) -> bool:
        """Só verifica PRESENÇA de referência/credencial — nunca o valor."""
        if sistema == "datajud":
            return bool(settings.DATAJUD_ENABLED and settings.DATAJUD_API_KEY)
        if sistema == "pdpj":
            return bool(settings.PDPJ_CLIENT_ID and settings.PDPJ_CLIENT_SECRET)
        if sistema == "pje_mni":
            return bool(settings.PDPJ_CLIENT_ID and settings.PDPJ_CLIENT_SECRET) or bool(
                perfil is not None and perfil.client_id_ref
            )
        if sistema == "eproc":
            return bool(perfil is not None and (perfil.client_id_ref or perfil.certificate_ref))
        return False

    def contexto(self, settings: Settings, perfil: Any | None, sistema: str) -> ContextoConector:
        return ContextoConector(
            settings=settings, perfil=perfil,
            credencial_disponivel=self.credencial_disponivel(settings, perfil, sistema),
            ambiente=(perfil.environment if perfil is not None else settings.PDPJ_ENVIRONMENT),
        )

    async def resolver(
        self, db: AsyncSession, settings: Settings, *, sistema: str | None, tribunal_code: str | None,
        degree: str | None = "1", environment: str | None = None,
    ) -> tuple[ConectorJudicial, ContextoConector]:
        conector = self.conector(sistema)
        perfil = await perfis_service.resolver_perfil(
            db, tribunal_code=tribunal_code, system=sistema, degree=degree, environment=environment,
        )
        return conector, self.contexto(settings, perfil, sistema)

    def matriz(self, settings: Settings, perfil: Any | None, sistema: str) -> MatrizCapacidades:
        conector = self.conector(sistema)
        return conector.capacidades(self.contexto(settings, perfil, sistema))

    async def matriz_completa(self, db: AsyncSession, settings: Settings) -> list[dict[str, Any]]:
        """Todos os conectores × perfis cadastrados (+ linha sem perfil)."""
        perfis = await perfis_service.listar_perfis(db)
        por_sistema: dict[str, list[Any]] = {}
        for p in perfis:
            por_sistema.setdefault(p.system, []).append(p)
        saida: list[dict[str, Any]] = []
        for chave in self._conectores:
            lista = por_sistema.get(chave) or [None]
            for perfil in lista:
                m = self.matriz(settings, perfil, chave).to_dict()
                m["perfil_id"] = perfil.id if perfil else None
                m["grau"] = perfil.degree if perfil else None
                saida.append(m)
        return saida
