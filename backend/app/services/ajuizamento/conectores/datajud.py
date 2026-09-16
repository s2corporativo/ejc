# ── app/services/ajuizamento/conectores/datajud.py ───────────────────────────
# DataJudConnector — consolidação sobre app/services/datajud_service (caminho
# ÚNICO de saída ao CNJ: mesma chave, retry, cache, rate limit). API Pública
# do DataJud (https://datajud-wiki.cnj.jus.br/api-publica/): metadados de
# capa + movimentações. NUNCA protocola, peticiona, anexa, assina, trata
# sigilo nem vale como intimação — todas essas operações são UNSUPPORTED.
from __future__ import annotations

import re
from typing import Any

from app.services import datajud_service
from app.services.ajuizamento.canonico import CanonicalJudicialCase
from app.services.ajuizamento.capacidades import ContextoConector, EstadoCapacidade
from app.services.ajuizamento.conectores.base import (
    ConectorJudicial, ErroConector, ResultadoOperacao, hash_payload,
)


def _digitos(n: str) -> str:
    return re.sub(r"\D", "", n or "")


class DataJudConnector(ConectorJudicial):
    chave = "datajud"
    sistema = "datajud"

    def declaradas(self, ctx: ContextoConector) -> dict[str, tuple[EstadoCapacidade, str]]:
        s = ctx.settings
        if s.DATAJUD_ENABLED and s.DATAJUD_API_KEY:
            estado, motivo = EstadoCapacidade.SUPPORTED, "API Pública DataJud habilitada (DATAJUD_ENABLED + chave)"
        else:
            estado, motivo = EstadoCapacidade.CONDITIONAL, "exige DATAJUD_ENABLED=true e DATAJUD_API_KEY (chave pública do CNJ)"
        return {
            "read_process": (estado, motivo),
            "read_movements": (estado, motivo),
            # Sem `file_new_case`/`append_petition`/`sign`/`read_notices`: acompanhamento complementar apenas.
        }

    async def find_process(self, numero_cnj: str) -> ResultadoOperacao:
        """Localiza o processo por número CNJ (capa + movimentos normalizados)."""
        n = _digitos(numero_cnj)
        if len(n) != 20:
            return ResultadoOperacao(EstadoCapacidade.UNSUPPORTED, mensagem="número CNJ inválido (20 dígitos)")
        try:
            info = await datajud_service.consultar_processo(n)
        except datajud_service.DataJudDesabilitadoError as exc:
            return ResultadoOperacao(EstadoCapacidade.CONDITIONAL, mensagem=str(exc))
        except datajud_service.TribunalNaoMapeadoError as exc:
            return ResultadoOperacao(EstadoCapacidade.UNSUPPORTED, mensagem=str(exc))
        except Exception as exc:  # noqa: BLE001 — httpx/ValueError após retries
            raise ErroConector(f"DataJud indisponível ({type(exc).__name__})") from exc
        if info is None:
            return ResultadoOperacao(EstadoCapacidade.SUPPORTED, dados={"encontrado": False},
                                     mensagem="processo não localizado no DataJud")
        return ResultadoOperacao(EstadoCapacidade.SUPPORTED, dados={"encontrado": True, **info},
                                 response_hash=hash_payload(info))

    async def get_process(self, numero_cnj: str) -> ResultadoOperacao:
        return await self.find_process(numero_cnj)

    async def get_public_movements(self, numero_cnj: str) -> ResultadoOperacao:
        r = await self.find_process(numero_cnj)
        if r.ok:
            r.dados = {"movimentos": r.dados.get("movimentos", []), "encontrado": r.dados.get("encontrado", False)}
        return r

    async def reconcile_process(self, numero_cnj: str, esperado: dict[str, Any]) -> ResultadoOperacao:
        """Confronta o que o EJC espera (classe, órgão) com a capa pública.
        Divergência NÃO bloqueia — é sinal para revisão humana."""
        r = await self.find_process(numero_cnj)
        if not r.ok or not r.dados.get("encontrado"):
            return r
        divergencias: list[str] = []
        for campo in ("classe", "orgao"):
            esp = (esperado.get(campo) or "").strip().lower()
            obt = (r.dados.get(campo) or "").strip().lower()
            if esp and obt and esp not in obt and obt not in esp:
                divergencias.append(f"{campo}: EJC='{esperado.get(campo)}' DataJud='{r.dados.get(campo)}'")
        r.dados = {"encontrado": True, "divergencias": divergencias, "classe": r.dados.get("classe"),
                   "orgao": r.dados.get("orgao"), "movimentos": len(r.dados.get("movimentos") or [])}
        r.mensagem = "reconciliado" if not divergencias else "divergências encontradas"
        return r

    # ── Interface única ──────────────────────────────────────────────────
    async def read_process(self, ctx: ContextoConector, numero_cnj: str) -> ResultadoOperacao:
        return await self.find_process(numero_cnj)

    async def read_movements(self, ctx: ContextoConector, numero_cnj: str) -> ResultadoOperacao:
        return await self.get_public_movements(numero_cnj)

    async def validate_target(self, ctx: ContextoConector, canonico: CanonicalJudicialCase) -> ResultadoOperacao:
        return ResultadoOperacao(EstadoCapacidade.UNSUPPORTED,
                                 mensagem="DataJud não valida destino de protocolo — é acompanhamento complementar")
