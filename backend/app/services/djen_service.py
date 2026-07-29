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

    def __int__(self) -> int:
        return self.novas

    def __radd__(self, other: int) -> int:
        """Compatibilidade com o scheduler legado (`total += resultado`)."""
        return int(other) + self.novas


# O scheduler roda em processo único por regra do EJC. Cada captura registra
# somente métricas sem identificadores; o heartbeat consome e limpa ao final.
_RESULTADOS_EXECUCAO: list[DjenCapturaResultado] = []


def registrar_resultado_execucao(
    resultado: DjenCapturaResultado,
) -> DjenCapturaResultado:
    _RESULTADOS_EXECUCAO.append(resultado)
    return resultado


def limpar_resultados_execucao() -> None:
    _RESULTADOS_EXECUCAO.clear()


def consumir_resumo_execucao() -> dict:
    resultados = list(_RESULTADOS_EXECUCAO)
    _RESULTADOS_EXECUCAO.clear()
    return resumir_execucao(resultados)


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
    """Agrega uma execução em formato próprio para heartbeat/painel."""
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
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    reraise=True,
)
async def _djen_get(params: dict) -> dict | list:
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(BASE, params=params)
        response.raise_for_status()
        return response.json()


CNJ_REGEX = re.compile(r"\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}")


def extrair_numero_cnj(texto: str | None) -> str | None:
    if not texto:
        return None
    match = CNJ_REGEX.search(texto)
    return match.group(0) if match else None


def normalizar_processo(numero: str | None) -> str:
    return re.sub(r"\D", "", numero or "")


def _parse_data_disp(raw: str | None) -> date:
    """Data de disponibilização tolerante a ISO ou DD/MM/YYYY."""
    valor = (raw or "").strip()
    if not valor:
        return date.today()
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        pass
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", valor)
    if match:
        try:
            return date(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
            )
        except ValueError:
            pass
    logger.warning("DJEN: data_disponibilizacao em formato inesperado; usando hoje")
    return date.today()


async def buscar_caso_ativo_por_processo(
    db: AsyncSession, numero: str | None
) -> Case | None:
    alvo = normalizar_processo(numero)
    if not alvo:
        return None
    casos = (
        await db.execute(
            select(Case).where(
                Case.deleted_at.is_(None),
                Case.numero_processo.isnot(None),
                Case.status.notin_([CaseStatus.encerrado, CaseStatus.arquivado]),
            )
        )
    ).scalars().all()
    return next(
        (caso for caso in casos if normalizar_processo(caso.numero_processo) == alvo),
        None,
    )


async def consultar_oab(
    numero: str, uf: str, dias: int = 2
) -> DjenConsultaResultado:
    """Consulta a fonte distinguindo zero legítimo de indisponibilidade."""
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    params = {
        "numeroOab": re.sub(r"\D", "", numero),
        "ufOab": uf.upper(),
        "dataDisponibilizacaoInicio": inicio.isoformat(),
        "dataDisponibilizacaoFim": fim.isoformat(),
        "itensPorPagina": 100,
    }
    try:
        payload = await _djen_get(params)
        if isinstance(payload, dict):
            items = payload.get("items", [])
        elif isinstance(payload, list):
            items = payload
        else:
            raise TypeError("payload DJEN sem coleção")
        if not isinstance(items, list) or any(
            not isinstance(item, dict) for item in items
        ):
            raise TypeError("items DJEN inválidos")
        return DjenConsultaResultado(fonte_ok=True, items=items)
    except Exception as exc:
        codigo = _classificar_erro_fonte(exc)
        logger.warning(
            "DJEN: consulta à fonte falhou após retries; codigo=%s", codigo
        )
        return DjenConsultaResultado(fonte_ok=False, erro=codigo)


async def _capturar_configurado(
    db: AsyncSession,
    adv: User,
) -> DjenCapturaResultado:
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
    for item in consulta.items:
        external_id = str(item.get("id") or item.get("hash") or "")
        if not external_id:
            ignoradas += 1
            continue

        existente = (
            await db.execute(
                select(DjenComunicacao).where(
                    DjenComunicacao.comunicacao_id_externo == external_id
                )
            )
        ).scalar_one_or_none()
        if existente:
            duplicadas += 1
            continue

        texto = (item.get("texto") or "")[:2000]
        numero_processo = normalizar_processo(
            item.get("numero_processo")
            or item.get("numeroprocessocommascara")
            or ""
        )
        if not numero_processo:
            numero_processo = normalizar_processo(extrair_numero_cnj(texto))

        caso = await buscar_caso_ativo_por_processo(db, numero_processo)
        if caso:
            marcador = (
                "\n[vinculação automática ao caso pelo nº do processo "
                f"{numero_processo} — conferir]"
            )
            texto = texto[: 2000 - len(marcador)] + marcador

        comunicacao = DjenComunicacao(
            id=str(uuid4()),
            comunicacao_id_externo=external_id,
            advogado_id=adv.id,
            numero_processo=item.get("numero_processo") or numero_processo,
            tribunal=item.get("siglaTribunal") or item.get("sigla_tribunal"),
            tipo_comunicacao=(
                item.get("tipoComunicacao")
                or item.get("tipo_comunicacao")
                or ""
            )[:60],
            data_disponibilizacao=_parse_data_disp(
                item.get("data_disponibilizacao")
                or item.get("dataDisponibilizacao")
            ),
            texto_resumo=texto,
            case_id=caso.id if caso else None,
        )
        db.add(comunicacao)

        if caso:
            db.add(
                CaseMovimento(
                    id=str(uuid4()),
                    case_id=caso.id,
                    tipo="intimacao",
                    descricao=(
                        f"📨 Intimação DJEN ({comunicacao.tribunal}): "
                        f"{comunicacao.tipo_comunicacao} — tratar na tela "
                        "Intimações [vinculação automática pelo nº do processo]"
                    ),
                )
            )

        from app.services.notification_service import (
            criar_notificacao_interna,
            enviar_email,
        )

        destinatario_id = (
            caso.advogado_responsavel_id
            if caso and caso.advogado_responsavel_id
            else adv.id
        )
        titulo = "📨 Nova intimação no DJEN"
        mensagem = (
            f"{comunicacao.tribunal or 'Tribunal'} · proc. "
            f"{comunicacao.numero_processo or '—'} · "
            f"{comunicacao.tipo_comunicacao}"
            + (
                " · vinculada automaticamente ao caso (conferir)"
                if caso
                else ""
            )
        )
        try:
            await criar_notificacao_interna(
                db,
                destinatario_id,
                titulo,
                mensagem,
                tipo="intimacao",
                link="/intimacoes",
            )
            if destinatario_id == adv.id:
                email_destino = adv.email
            else:
                email_destino = (
                    await db.execute(
                        select(User.email).where(User.id == destinatario_id)
                    )
                ).scalar_one_or_none()
            if email_destino:
                await enviar_email(
                    email_destino,
                    f"[EJC] {titulo}",
                    f"<p>{mensagem}</p><p>Trate a intimação na tela "
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


async def capturar_para_advogado(
    db: AsyncSession, adv: User
) -> DjenCapturaResultado:
    """Captura uma inscrição sem permitir que erro por usuário fique invisível."""
    if not adv.djen_oab_numero or not adv.djen_oab_uf:
        return registrar_resultado_execucao(
            DjenCapturaResultado.sem_configuracao()
        )

    try:
        resultado = await _capturar_configurado(db, adv)
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        logger.error("DJEN: captura interna falhou; codigo=erro_interno")
        resultado = DjenCapturaResultado(
            configurada=True,
            fonte_ok=False,
            recebidas=0,
            novas=0,
            duplicadas=0,
            ignoradas=0,
            erro="erro_interno",
        )
    return registrar_resultado_execucao(resultado)
