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
from app.models.case import Case, CaseMovimento, CaseStatus
from app.models.djen import DjenComunicacao

logger = logging.getLogger("ejc.djen")
BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"

# ── Vinculação automática publicação → caso (R10/Seção 12) ────────────────────
# Padrão CNJ (Res. CNJ 65/2008): NNNNNNN-DD.AAAA.J.TR.OOOO — aceita com ou
# sem pontuação. A comparação com Case.numero_processo é feita normalizando
# os dois lados (apenas dígitos).
CNJ_REGEX = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")


def extrair_numero_cnj(texto: str | None) -> str | None:
    """Extrai o primeiro nº de processo no padrão CNJ do texto (ou None)."""
    if not texto:
        return None
    m = CNJ_REGEX.search(texto)
    return m.group(0) if m else None


def normalizar_processo(numero: str | None) -> str:
    """Remove toda pontuação/máscara — só dígitos, para comparação."""
    return re.sub(r"\D", "", numero or "")


def _parse_data_disp(raw: str | None) -> date:
    """Data de disponibilização TOLERANTE a formato: ISO (YYYY-MM-DD, com ou sem
    hora) ou BR (DD/MM/YYYY). NUNCA levanta — formato desconhecido → hoje, com
    warning. Antes, um date.fromisoformat direto abortava a captura INTEIRA do
    advogado quando a API devolvia a data em outro formato (ou vazia com hora
    inválida) — perdendo todas as intimações seguintes do lote (risco de prazo)."""
    s = (raw or "").strip()
    if not s:
        return date.today()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    logger.warning("DJEN: data_disponibilizacao em formato inesperado (%r) — usando hoje", raw)
    return date.today()


async def buscar_caso_ativo_por_processo(
    db: AsyncSession, numero: str | None
) -> Case | None:
    """
    Retorna o caso ATIVO (não deletado, não encerrado/arquivado) cujo
    numero_processo — normalizado (só dígitos) — bate com `numero`.
    Comparação em Python porque o banco guarda o nº com máscara variável.
    """
    alvo = normalizar_processo(numero)
    if not alvo:
        return None
    casos = (await db.execute(select(Case).where(
        Case.deleted_at.is_(None),
        Case.numero_processo.isnot(None),
        Case.status.notin_([CaseStatus.encerrado, CaseStatus.arquivado]),
    ))).scalars().all()
    return next(
        (c for c in casos if normalizar_processo(c.numero_processo) == alvo),
        None,
    )


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

        texto = (it.get("texto") or "")[:2000]
        num_proc = normalizar_processo(it.get("numero_processo")
                                       or it.get("numeroprocessocommascara") or "")
        # Fallback: se a API não trouxe o nº, extrai do texto (padrão CNJ)
        if not num_proc:
            num_proc = normalizar_processo(extrair_numero_cnj(texto))

        # Vinculação AUTOMÁTICA a caso ativo pelo nº do processo (normalizado).
        # Marcador no texto_resumo para conferência humana — o vínculo não
        # dispensa a leitura da publicação original.
        case = await buscar_caso_ativo_por_processo(db, num_proc)
        if case:
            marcador = (f"\n[vinculação automática ao caso pelo nº do processo "
                        f"{num_proc} — conferir]")
            texto = texto[:2000 - len(marcador)] + marcador

        com = DjenComunicacao(
            id=str(uuid4()),
            comunicacao_id_externo=ext_id,
            advogado_id=adv.id,
            numero_processo=it.get("numero_processo") or num_proc,
            tribunal=it.get("siglaTribunal") or it.get("sigla_tribunal"),
            tipo_comunicacao=(it.get("tipoComunicacao")
                              or it.get("tipo_comunicacao") or "")[:60],
            data_disponibilizacao=_parse_data_disp(
                it.get("data_disponibilizacao") or it.get("dataDisponibilizacao")
            ),
            texto_resumo=texto,
            case_id=case.id if case else None,
        )
        db.add(com)

        if case:
            db.add(CaseMovimento(
                id=str(uuid4()), case_id=case.id, tipo="intimacao",
                descricao=f"📨 Intimação DJEN ({com.tribunal}): "
                          f"{com.tipo_comunicacao} — tratar na tela Intimações"
                          f" [vinculação automática pelo nº do processo]",
            ))

        # ── Notificação ATIVA (só na criação — o dedup acima garante) ────────
        # Destinatário: advogado responsável do caso vinculado; sem caso (ou
        # caso sem responsável), o dono da OAB que originou a captura.
        from app.services.notification_service import (
            criar_notificacao_interna, enviar_email,
        )
        destinatario_id = (case.advogado_responsavel_id
                           if case and case.advogado_responsavel_id else adv.id)
        titulo_n = "📨 Nova intimação no DJEN"
        msg_n = (f"{com.tribunal or 'Tribunal'} · proc. "
                 f"{com.numero_processo or '—'} · {com.tipo_comunicacao}"
                 + (" · vinculada automaticamente ao caso (conferir)"
                    if case else ""))
        try:
            await criar_notificacao_interna(
                db, destinatario_id, titulo_n, msg_n,
                tipo="intimacao", link="/intimacoes",
            )
            # E-mail: enviar_email é no-op seguro se EMAIL_ENABLED=false
            if destinatario_id == adv.id:
                email_dest = adv.email
            else:
                email_dest = (await db.execute(select(User.email).where(
                    User.id == destinatario_id
                ))).scalar_one_or_none()
            if email_dest:
                await enviar_email(
                    email_dest, f"[EJC] {titulo_n}",
                    f"<p>{msg_n}</p><p>Trate a intimação na tela "
                    f"<b>Intimações</b> do EJC.</p>",
                )
        except Exception as e:
            logger.warning(f"DJEN notificação falhou (não-fatal): {e}")
        novas += 1
    return novas
