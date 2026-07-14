# ── app/services/feriados_service.py ─────────────────────────────────────────
# Sincronização de feriados NACIONAIS via BrasilAPI → tabela `feriados`.
#
# A tabela `feriados` (models/feriado.py, seed em seeds/seed_all.py) já é a
# fonte dos feriados municipais/estaduais do cálculo de prazos
# (deadline_calculator.carregar_feriados_db). Este serviço acrescenta os
# NACIONAIS de anos futuros automaticamente — o seed cobre anos passados, mas
# feriados móveis de anos novos (Carnaval, Corpus Christi) e mudanças de lei
# exigiriam re-seed manual.
#
# Regras:
#   • MERGE aditivo: só INSERE datas ausentes — municipais/estaduais/forenses
#     cadastrados à mão nunca são tocados (a coluna `data` é UNIQUE).
#   • Fail-safe: BrasilAPI fora do ar ou banco indisponível ⇒ warning, nunca
#     exceção ao chamador (job do scheduler).
#   • Flag FERIADOS_BRASILAPI_ENABLED (default True — API gratuita, sem chave).
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

import httpx

from app.core.config import get_settings

logger = logging.getLogger("ejc.feriados")

BRASILAPI_FERIADOS_URL = "https://brasilapi.com.br/api/feriados/v1/{ano}"
_TIMEOUT_S = 15

# Nomes (BrasilAPI) dos feriados móveis — marca `movel=True` na tabela.
_MOVEIS = {"carnaval", "sexta-feira santa", "corpus christi", "páscoa"}


async def _buscar_feriados_ano(ano: int) -> list[dict]:
    """GET BrasilAPI /feriados/v1/{ano} → [{date, name, type}, ...]."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as cli:
        r = await cli.get(BRASILAPI_FERIADOS_URL.format(ano=ano))
        r.raise_for_status()
        return r.json() or []


async def sincronizar_feriados_nacionais(anos: list[int] | None = None,
                                         db=None) -> dict:
    """Busca os feriados nacionais dos `anos` (default: ano atual e o próximo)
    na BrasilAPI e insere na tabela `feriados` apenas as datas AUSENTES.
    Depois recarrega o cache em memória do deadline_calculator.
    Retorna resumo {status, anos, inseridos, existentes}."""
    settings = get_settings()
    if not settings.FERIADOS_BRASILAPI_ENABLED:
        return {"status": "desabilitado", "inseridos": 0, "existentes": 0}

    ano_atual = date.today().year
    anos = anos or [ano_atual, ano_atual + 1]

    # 1) coleta (falha em um ano não descarta os demais)
    itens: list[dict] = []
    for ano in anos:
        try:
            itens.extend(await _buscar_feriados_ano(ano))
        except Exception as exc:
            logger.warning("[Feriados] BrasilAPI indisponível para %s: %s", ano, exc)
    if not itens:
        return {"status": "sem_dados", "anos": anos, "inseridos": 0, "existentes": 0}

    datas_api: dict[date, str] = {}
    for it in itens:
        try:
            d = datetime.strptime(it["date"], "%Y-%m-%d").date()
            datas_api[d] = (it.get("name") or "Feriado nacional").strip()
        except Exception:
            continue

    # 2) merge aditivo no banco
    inseridos = existentes = 0
    try:
        from sqlalchemy import select
        from app.models.feriado import Feriado

        async def _merge(sess) -> None:
            nonlocal inseridos, existentes
            ja = set((await sess.execute(
                select(Feriado.data).where(Feriado.data.in_(list(datas_api)))
            )).scalars().all())
            existentes = len(ja)
            for d, nome in sorted(datas_api.items()):
                if d in ja:
                    continue
                sess.add(Feriado(
                    id=str(uuid.uuid4()), data=d, nome=nome, tipo="nacional",
                    movel=nome.casefold() in _MOVEIS,
                ))
                inseridos += 1
            await sess.commit()

        if db is not None:
            await _merge(db)
        else:
            from app.core.database import AsyncSessionLocal
            async with AsyncSessionLocal() as sess:
                await _merge(sess)
    except Exception as exc:
        logger.warning("[Feriados] falha ao persistir feriados nacionais: %s", exc)
        return {"status": "erro_banco", "anos": anos, "inseridos": 0,
                "existentes": existentes}

    # 3) recarrega o cache em memória do cálculo de prazos (fail-safe interno)
    if inseridos:
        from app.services.deadline_calculator import carregar_feriados_db
        await carregar_feriados_db()

    logger.info("[Feriados] BrasilAPI sync %s: %d inserido(s), %d já existente(s)",
                anos, inseridos, existentes)
    return {"status": "ok", "anos": anos, "inseridos": inseridos,
            "existentes": existentes}
