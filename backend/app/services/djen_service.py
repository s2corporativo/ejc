# ── app/services/djen_service.py ─────────────────────────────────────────────
# Captura de intimações/publicações via API Comunica (DJEN/CNJ).
# Pública, sem autenticação. Consulta por OAB (número + UF).
# Docs: https://comunicaapi.pje.jus.br/swagger
#
# IMPORTANTE (decisão jurídica de design): o sistema NÃO cria o prazo
# automaticamente — tipo e contagem dependem de leitura humana da intimação.
# Ele REGISTRA a comunicação, vincula ao caso (se nº de processo bater),
# cria movimento e ALERTA imediato. O advogado define o prazo na tela
# "Intimações" — eliminando o risco de prazo calculado errado.
from __future__ import annotations
import logging
import re
from datetime import date, timedelta
from uuid import uuid4

import httpx
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)
async def _djen_get(params: dict) -> dict | list:
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get(BASE, params=params)
        r.raise_for_status()
        return r.json()
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.case import Case, CaseMovimento
from app.models.djen import DjenComunicacao
from app.models.notification import Notification

logger = logging.getLogger("ejc.djen")
BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"


async def consultar_oab(numero: str, uf: str, dias: int = 2) -> list[dict]:
    """Comunicações disponibilizadas nos últimos `dias` para a OAB."""
    fim = date.today()
    ini = fim - timedelta(days=dias)
    params = {
        "numeroOab": re.sub(r"\D", "", numero),
        "ufOab": uf.upper(),
        "dataDisponibilizacaoInicio": ini.isoformat(),
        "dataDisponibilizacaoFim": fim.isoformat(),
        "itensPorPagina": 100,
    }
    try:
        data = await _djen_get(params)
        return data.get("items", data if isinstance(data, list) else [])
    except Exception as e:
        logger.warning(f"DJEN falhou OAB {numero}/{uf} (após retries): {e}")
        return []


async def capturar_para_advogado(db: AsyncSession, adv: User) -> int:
    """Insere comunicações NOVAS; vincula a casos; notifica. Retorna qtd novas."""
    if not adv.djen_oab_numero or not adv.djen_oab_uf:
        return 0
    items = await consultar_oab(adv.djen_oab_numero, adv.djen_oab_uf)
    novas = 0
    for it in items:
        ext_id = str(it.get("id") or it.get("hash") or "")
        if not ext_id:
            continue
        existe = (await db.execute(select(DjenComunicacao).where(
            DjenComunicacao.comunicacao_id_externo == ext_id
        ))).scalar_one_or_none()
        if existe:
            continue

        num_proc = re.sub(r"\D", "", it.get("numero_processo")
                          or it.get("numeroprocessocommascara") or "")
        # Vincular a caso existente pelo nº do processo
        case = None
        if num_proc:
            case = (await db.execute(select(Case).where(
                Case.deleted_at.is_(None),
            ))).scalars().all()
            case = next(
                (c for c in case
                 if c.numero_processo
                 and re.sub(r"\D", "", c.numero_processo) == num_proc),
                None,
            )

        texto = (it.get("texto") or "")[:2000]
        com = DjenComunicacao(
            id=str(uuid4()),
            comunicacao_id_externo=ext_id,
            advogado_id=adv.id,
            numero_processo=it.get("numero_processo") or num_proc,
            tribunal=it.get("siglaTribunal") or it.get("sigla_tribunal"),
            tipo_comunicacao=(it.get("tipoComunicacao")
                              or it.get("tipo_comunicacao") or "")[:60],
            data_disponibilizacao=date.fromisoformat(
                (it.get("data_disponibilizacao")
                 or it.get("dataDisponibilizacao") or str(date.today()))[:10]
            ),
            texto_resumo=texto,
            case_id=case.id if case else None,
        )
        db.add(com)

        if case:
            db.add(CaseMovimento(
                id=str(uuid4()), case_id=case.id, tipo="intimacao",
                descricao=f"📨 Intimação DJEN ({com.tribunal}): "
                          f"{com.tipo_comunicacao} — tratar na tela Intimações",
            ))

        db.add(Notification(
            id=str(uuid4()), user_id=adv.id,
            titulo="📨 Nova intimação no DJEN",
            mensagem=f"{com.tribunal or 'Tribunal'} · proc. "
                     f"{com.numero_processo or '—'} · {com.tipo_comunicacao}",
            tipo="intimacao", link="/intimacoes",
        ))
        novas += 1
    return novas
