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

import json
import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.models.case import Case, CaseMovimento, CaseStatus
from app.models.djen import DjenComunicacao
from app.models.user import User

logger = logging.getLogger("ejc.djen")
BASE = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"


@dataclass(slots=True)
class DjenConsultaResultado:
    """Resultado explícito da fonte externa.

    `items=[]` com `fonte_ok=True` significa consulta válida sem comunicações.
    `items=[]` com `fonte_ok=False` significa falha da fonte. Os dois estados não
    podem ser confundidos, pois apenas o segundo exige ação operacional.
    """

    fonte_ok: bool
    items: list[dict] = field(default_factory=list)
    erro: str | None = None

    @property
    def recebidas(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict:
        # Não inclui conteúdo das comunicações, OAB, e-mail ou exceção bruta.
        return {
            "fonte_ok": self.fonte_ok,
            "recebidas": self.recebidas,
            "erro": self.erro,
        }


@dataclass(slots=True)
class DjenCapturaResultado:
    """Métricas sanitizadas da captura de uma inscrição monitorada."""

    configurada: bool
    fonte_ok: bool
    recebidas: int
    novas: int
    duplicadas: int
    ignoradas: int
    erro: str | None = None

    @classmethod
    def sem_configuracao(cls) -> "DjenCapturaResultado":
        return cls(
            configurada=False,
            fonte_ok=False,
            recebidas=0,
            novas=0,
            duplicadas=0,
            ignoradas=0,
            erro="oab_nao_configurada",
        )

    def to_dict(self) -> dict:
        return asdict(self)


def _classificar_erro_fonte(exc: Exception) -> str:
    """Transforma exceção externa em código acionável sem vazar conteúdo."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        if status >= 500:
            return "http_5xx"
        if status >= 400:
            return "http_4xx"
        return "http_status"
    if isinstance(exc, httpx.TransportError):
        return "transporte"
    if isinstance(exc, (TypeError, ValueError)):
        return "payload_invalido"
    return "erro_interno"


def resumir_execucao(resultados: list[DjenCapturaResultado]) -> dict:
    """Agrega uma execução do job em formato próprio para heartbeat/painel.

    Sem migration: o resumo cabe no `SchedulerHeartbeat.detail` já existente.
    Qualquer falha parcial deixa o heartbeat vermelho; zero legítimo continua
    verde, mas explicitamente rotulado como `sucesso_sem_resultados`.
    """
    if not resultados:
        return {
            "heartbeat_status": "erro",
            "resultado": "configuracao_incompleta",
            "oabs_elegiveis": 0,
            "oabs_sucesso": 0,
            "oabs_falha": 0,
            "recebidas": 0,
            "novas": 0,
            "duplicadas": 0,
            "ignoradas": 0,
            "erros": {"nenhuma_oab_configurada": 1},
        }

    elegiveis = sum(1 for r in resultados if r.configurada)
    sucessos = sum(1 for r in resultados if r.configurada and r.fonte_ok)
    falhas = sum(1 for r in resultados if not r.fonte_ok)
    erros = Counter(r.erro for r in resultados if r.erro)

    if falhas and sucessos:
        heartbeat_status, resultado = "erro", "parcial"
    elif falhas:
        heartbeat_status, resultado = "erro", "falha_fonte"
    else:
        recebidas = sum(r.recebidas for r in resultados)
        heartbeat_status = "ok"
        resultado = "sucesso" if recebidas else "sucesso_sem_resultados"

    return {
        "heartbeat_status": heartbeat_status,
        "resultado": resultado,
        "oabs_elegiveis": elegiveis,
        "oabs_sucesso": sucessos,
        "oabs_falha": falhas,
        "recebidas": sum(r.recebidas for r in resultados),
        "novas": sum(r.novas for r in resultados),
        "duplicadas": sum(r.duplicadas for r in resultados),
        "ignoradas": sum(r.ignoradas for r in resultados),
        "erros": dict(sorted(erros.items())),
    }


def codificar_resumo_heartbeat(resumo: dict) -> str:
    """JSON estável, curto e sem identificadores pessoais."""
    permitido = {
        "resultado",
        "oabs_elegiveis",
        "oabs_sucesso",
        "oabs_falha",
        "recebidas",
        "novas",
        "duplicadas",
        "ignoradas",
        "erros",
    }
    payload = {k: resumo[k] for k in permitido if k in resumo}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    """Data de disponibilização tolerante a ISO ou DD/MM/YYYY.

    Formato ausente/inesperado continua usando hoje para preservar compatibilidade,
    mas registra warning sem conteúdo da comunicação.
    """
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
    logger.warning("DJEN: data_disponibilizacao em formato inesperado; usando hoje")
    return date.today()


async def buscar_caso_ativo_por_processo(
    db: AsyncSession, numero: str | None
) -> Case | None:
    """Retorna caso operacional cujo número normalizado coincide."""
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


async def consultar_oab(
    numero: str, uf: str, dias: int = 2
) -> DjenConsultaResultado:
    """Consulta a fonte distinguindo zero legítimo de indisponibilidade."""
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
        if isinstance(data, dict):
            items = data.get("items", [])
        elif isinstance(data, list):
            items = data
        else:
            raise TypeError("payload DJEN sem coleção")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise TypeError("items DJEN inválidos")
        return DjenConsultaResultado(fonte_ok=True, items=items)
    except Exception as exc:
        codigo = _classificar_erro_fonte(exc)
        logger.warning("DJEN: consulta à fonte falhou após retries; codigo=%s", codigo)
        return DjenConsultaResultado(fonte_ok=False, erro=codigo)


async def capturar_para_advogado(
    db: AsyncSession, adv: User
) -> DjenCapturaResultado:
    """Insere comunicações novas e devolve métricas sanitizadas da captura."""
    if not adv.djen_oab_numero or not adv.djen_oab_uf:
        return DjenCapturaResultado.sem_configuracao()

    consulta = await consultar_oab(adv.djen_oab_numero, adv.djen_oab_uf)
    if not consulta.fonte_ok:
        return DjenCapturaResultado(
            configurada=True,
            fonte_ok=False,
            recebidas=0,
            novas=0,
            duplicadas=0,
            ignoradas=0,
            erro=consulta.erro,
        )

    novas = 0
    duplicadas = 0
    ignoradas = 0
    for it in consulta.items:
        ext_id = str(it.get("id") or it.get("hash") or "")
        if not ext_id:
            ignoradas += 1
            continue
        existe = (await db.execute(select(DjenComunicacao).where(
            DjenComunicacao.comunicacao_id_externo == ext_id
        ))).scalar_one_or_none()
        if existe:
            duplicadas += 1
            continue

        texto = (it.get("texto") or "")[:2000]
        num_proc = normalizar_processo(
            it.get("numero_processo") or it.get("numeroprocessocommascara") or ""
        )
        if not num_proc:
            num_proc = normalizar_processo(extrair_numero_cnj(texto))

        case = await buscar_caso_ativo_por_processo(db, num_proc)
        if case:
            marcador = (
                "\n[vinculação automática ao caso pelo nº do processo "
                f"{num_proc} — conferir]"
            )
            texto = texto[: 2000 - len(marcador)] + marcador

        com = DjenComunicacao(
            id=str(uuid4()),
            comunicacao_id_externo=ext_id,
            advogado_id=adv.id,
            numero_processo=it.get("numero_processo") or num_proc,
            tribunal=it.get("siglaTribunal") or it.get("sigla_tribunal"),
            tipo_comunicacao=(
                it.get("tipoComunicacao") or it.get("tipo_comunicacao") or ""
            )[:60],
            data_disponibilizacao=_parse_data_disp(
                it.get("data_disponibilizacao") or it.get("dataDisponibilizacao")
            ),
            texto_resumo=texto,
            case_id=case.id if case else None,
        )
        db.add(com)

        if case:
            db.add(CaseMovimento(
                id=str(uuid4()),
                case_id=case.id,
                tipo="intimacao",
                descricao=(
                    f"📨 Intimação DJEN ({com.tribunal}): "
                    f"{com.tipo_comunicacao} — tratar na tela Intimações "
                    "[vinculação automática pelo nº do processo]"
                ),
            ))

        from app.services.notification_service import (
            criar_notificacao_interna,
            enviar_email,
        )

        destinatario_id = (
            case.advogado_responsavel_id
            if case and case.advogado_responsavel_id
            else adv.id
        )
        titulo_n = "📨 Nova intimação no DJEN"
        msg_n = (
            f"{com.tribunal or 'Tribunal'} · proc. "
            f"{com.numero_processo or '—'} · {com.tipo_comunicacao}"
            + (
                " · vinculada automaticamente ao caso (conferir)"
                if case
                else ""
            )
        )
        try:
            await criar_notificacao_interna(
                db,
                destinatario_id,
                titulo_n,
                msg_n,
                tipo="intimacao",
                link="/intimacoes",
            )
            if destinatario_id == adv.id:
                email_dest = adv.email
            else:
                email_dest = (await db.execute(select(User.email).where(
                    User.id == destinatario_id
                ))).scalar_one_or_none()
            if email_dest:
                await enviar_email(
                    email_dest,
                    f"[EJC] {titulo_n}",
                    f"<p>{msg_n}</p><p>Trate a intimação na tela "
                    "<b>Intimações</b> do EJC.</p>",
                )
        except Exception:
            logger.warning("DJEN: notificação de item falhou (não fatal)")
        novas += 1

    return DjenCapturaResultado(
        configurada=True,
        fonte_ok=True,
        recebidas=consulta.recebidas,
        novas=novas,
        duplicadas=duplicadas,
        ignoradas=ignoradas,
    )
