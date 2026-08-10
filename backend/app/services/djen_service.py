# ── app/services/djen_service.py ─────────────────────────────────────────────
# Captura operacional de intimações/publicações via API Comunica (DJEN/CNJ).
# Pública, sem autenticação. Consulta por OAB (número + UF).
# Docs: https://comunicaapi.pje.jus.br/swagger
#
# Segurança operacional:
#  • janela móvel de reconciliação — tolera interrupções curtas do scheduler;
#  • paginação explícita — nunca assume que 100 itens representam a janela;
#  • teto de páginas fail-closed — execução incompleta não vira falso sucesso;
#  • data ausente/inválida permanece ausente — nunca é substituída por "hoje";
#  • nenhuma comunicação cria prazo automaticamente.
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from contextvars import ContextVar
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
ITENS_POR_PAGINA = 100
MAX_PAGINAS = 100
JANELA_RECONCILIACAO_DIAS = 7


@dataclass(slots=True)
class DjenConsultaResultado:
    """Resposta explícita da fonte externa.

    ``fonte_ok=True`` com ``items=[]`` significa consulta válida sem resultado.
    ``fonte_ok=False`` significa indisponibilidade, payload inválido ou leitura
    incompleta da janela solicitada.
    """

    fonte_ok: bool
    items: list[dict] = field(default_factory=list)
    erro: str | None = None
    paginas: int = 0
    janela_dias: int = 0

    @property
    def recebidas(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict:
        return {
            "fonte_ok": self.fonte_ok,
            "recebidas": self.recebidas,
            "erro": self.erro,
            "paginas": self.paginas,
            "janela_dias": self.janela_dias,
        }


@dataclass(slots=True)
class EmailDjenPendente:
    destinatario: str
    assunto: str
    html: str


@dataclass(slots=True)
class DjenCapturaResultado:
    """Resultado sanitizado de uma inscrição monitorada."""

    configurada: bool
    fonte_ok: bool
    recebidas: int
    novas: int
    duplicadas: int
    ignoradas: int
    erro: str | None = None
    paginas: int = 0
    janela_dias: int = 0
    emails_pendentes: list[EmailDjenPendente] = field(
        default_factory=list,
        repr=False,
    )

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

    @classmethod
    def falha_interna(cls) -> "DjenCapturaResultado":
        return cls(
            configurada=True,
            fonte_ok=False,
            recebidas=0,
            novas=0,
            duplicadas=0,
            ignoradas=0,
            erro="erro_interno",
        )

    def to_dict(self) -> dict:
        dados = asdict(self)
        dados.pop("emails_pendentes", None)
        return dados

    def __int__(self) -> int:
        return self.novas

    def __radd__(self, other: int) -> int:
        """Mantém compatibilidade com ``total += resultado`` do scheduler."""
        return int(other) + self.novas


# Tupla imutável + copy-on-write: tasks-filhas podem herdar o valor do ContextVar,
# mas nunca compartilham uma lista mutável. Captura manual e job ficam isolados.
_RESULTADOS_EXECUCAO: ContextVar[tuple[DjenCapturaResultado, ...]] = ContextVar(
    "djen_resultados_execucao",
    default=(),
)


def registrar_resultado_execucao(
    resultado: DjenCapturaResultado,
) -> DjenCapturaResultado:
    _RESULTADOS_EXECUCAO.set((*_RESULTADOS_EXECUCAO.get(), resultado))
    return resultado


def consumir_resultados_execucao() -> list[DjenCapturaResultado]:
    resultados = list(_RESULTADOS_EXECUCAO.get())
    _RESULTADOS_EXECUCAO.set(())
    return resultados


def limpar_resultados_execucao() -> None:
    _RESULTADOS_EXECUCAO.set(())


def _classificar_erro_fonte(exc: Exception) -> str:
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
            "paginas": 0,
            "janela_dias": 0,
            "erros": {"nenhuma_oab_configurada": 1},
        }

    elegiveis = sum(1 for resultado in resultados if resultado.configurada)
    sucessos = sum(
        1
        for resultado in resultados
        if resultado.configurada and resultado.fonte_ok
    )
    falhas = sum(1 for resultado in resultados if not resultado.fonte_ok)
    erros = Counter(
        resultado.erro for resultado in resultados if resultado.erro
    )

    if falhas and sucessos:
        heartbeat_status, estado = "erro", "parcial"
    elif falhas:
        heartbeat_status, estado = "erro", "falha_fonte"
    else:
        recebidas = sum(resultado.recebidas for resultado in resultados)
        heartbeat_status = "ok"
        estado = "sucesso" if recebidas else "sucesso_sem_resultados"

    return {
        "heartbeat_status": heartbeat_status,
        "resultado": estado,
        "oabs_elegiveis": elegiveis,
        "oabs_sucesso": sucessos,
        "oabs_falha": falhas,
        "recebidas": sum(resultado.recebidas for resultado in resultados),
        "novas": sum(resultado.novas for resultado in resultados),
        "duplicadas": sum(resultado.duplicadas for resultado in resultados),
        "ignoradas": sum(resultado.ignoradas for resultado in resultados),
        "paginas": sum(resultado.paginas for resultado in resultados),
        "janela_dias": max(
            (resultado.janela_dias for resultado in resultados),
            default=0,
        ),
        "erros": dict(sorted(erros.items())),
    }


def codificar_resumo_heartbeat(resumo: dict) -> str:
    permitido = {
        "resultado",
        "oabs_elegiveis",
        "oabs_sucesso",
        "oabs_falha",
        "recebidas",
        "novas",
        "duplicadas",
        "ignoradas",
        "paginas",
        "janela_dias",
        "erros",
    }
    payload = {chave: resumo[chave] for chave in permitido if chave in resumo}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


async def enviar_emails_pendentes(resultado: DjenCapturaResultado) -> None:
    """Envia e-mails somente depois que o chamador confirmou a transação."""
    if not resultado.emails_pendentes:
        return
    from app.services.notification_service import enviar_email

    for pendente in resultado.emails_pendentes:
        try:
            await enviar_email(
                pendente.destinatario,
                pendente.assunto,
                pendente.html,
            )
        except Exception:
            logger.warning("DJEN: envio de e-mail pós-commit falhou")


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


def _parse_data_disp(raw: str | None) -> date | None:
    """Converte a data informada pela fonte sem inventar marco temporal.

    Data ausente ou inválida não aborta a captura, mas permanece ``None`` para
    impedir que camadas jurídicas tratem a data do servidor como fato da fonte.
    """
    valor = (raw or "").strip()
    if not valor:
        return None
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
    logger.warning(
        "DJEN: data de disponibilização ausente ou inválida; mantendo sem data"
    )
    return None


def _extrair_items(payload: dict | list) -> list[dict]:
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
    return items


async def buscar_caso_ativo_por_processo(
    db: AsyncSession,
    numero: str | None,
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
        (
            caso
            for caso in casos
            if normalizar_processo(caso.numero_processo) == alvo
        ),
        None,
    )


async def consultar_oab(
    numero: str,
    uf: str,
    dias: int = JANELA_RECONCILIACAO_DIAS,
) -> DjenConsultaResultado:
    """Consulta paginada com janela sobreposta e sem sucesso truncado."""
    dias = max(1, min(int(dias), 90))
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    base_params = {
        "numeroOab": re.sub(r"\D", "", numero),
        "ufOab": uf.upper(),
        "dataDisponibilizacaoInicio": inicio.isoformat(),
        "dataDisponibilizacaoFim": fim.isoformat(),
        "itensPorPagina": ITENS_POR_PAGINA,
    }

    todos: list[dict] = []
    vistos: set[str] = set()
    paginas = 0
    try:
        for pagina in range(1, MAX_PAGINAS + 1):
            payload = await _djen_get({**base_params, "pagina": pagina})
            lote = _extrair_items(payload)
            paginas = pagina

            for item in lote:
                chave = str(item.get("id") or item.get("hash") or "")
                # Sem id/hash, a captura contabiliza como ignorada. Não usamos
                # conteúdo como chave para não fundir duas comunicações reais.
                if chave and chave in vistos:
                    continue
                if chave:
                    vistos.add(chave)
                todos.append(item)

            if len(lote) < ITENS_POR_PAGINA:
                return DjenConsultaResultado(
                    fonte_ok=True,
                    items=todos,
                    paginas=paginas,
                    janela_dias=dias,
                )

        logger.error(
            "DJEN: paginação atingiu teto de %s páginas; janela incompleta",
            MAX_PAGINAS,
        )
        return DjenConsultaResultado(
            fonte_ok=False,
            items=[],
            erro="paginacao_truncada",
            paginas=paginas,
            janela_dias=dias,
        )
    except Exception as exc:
        codigo = _classificar_erro_fonte(exc)
        logger.warning(
            "DJEN: consulta à fonte falhou após retries; codigo=%s",
            codigo,
        )
        return DjenConsultaResultado(
            fonte_ok=False,
            erro=codigo,
            paginas=paginas,
            janela_dias=dias,
        )


async def _capturar_configurado(
    db: AsyncSession,
    adv: User,
    consulta: DjenConsultaResultado,
) -> DjenCapturaResultado:
    novas = 0
    duplicadas = 0
    ignoradas = 0
    emails: list[EmailDjenPendente] = []

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
            or item.get("numeroProcesso")
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
            numero_processo=(
                item.get("numero_processo")
                or item.get("numeroProcesso")
                or numero_processo
            ),
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

        from app.services.notification_service import criar_notificacao_interna

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
            emails.append(
                EmailDjenPendente(
                    destinatario=email_destino,
                    assunto=f"[EJC] {titulo}",
                    html=(
                        f"<p>{mensagem}</p><p>Trate a intimação na tela "
                        "<b>Intimações</b> do EJC.</p>"
                    ),
                )
            )
        novas += 1

    return DjenCapturaResultado(
        configurada=True,
        fonte_ok=True,
        recebidas=consulta.recebidas,
        novas=novas,
        duplicadas=duplicadas,
        ignoradas=ignoradas,
        paginas=consulta.paginas,
        janela_dias=consulta.janela_dias,
        emails_pendentes=emails,
    )


async def capturar_para_advogado(
    db: AsyncSession,
    adv: User,
    *,
    dias: int = JANELA_RECONCILIACAO_DIAS,
) -> DjenCapturaResultado:
    """Captura uma inscrição em savepoint e registra métricas na task atual.

    O savepoint impede que a falha de um advogado reverta comunicações já
    processadas para advogados anteriores na mesma sessão do scheduler.
    """
    if not (adv.djen_oab_numero or "").strip() or not (
        adv.djen_oab_uf or ""
    ).strip():
        return registrar_resultado_execucao(
            DjenCapturaResultado.sem_configuracao()
        )

    consulta = await consultar_oab(
        adv.djen_oab_numero,
        adv.djen_oab_uf,
        dias=dias,
    )
    if not consulta.fonte_ok:
        return registrar_resultado_execucao(
            DjenCapturaResultado(
                configurada=True,
                fonte_ok=False,
                recebidas=0,
                novas=0,
                duplicadas=0,
                ignoradas=0,
                erro=consulta.erro,
                paginas=consulta.paginas,
                janela_dias=consulta.janela_dias,
            )
        )

    try:
        async with db.begin_nested():
            resultado = await _capturar_configurado(db, adv, consulta)
    except Exception:
        logger.error("DJEN: captura interna falhou; codigo=erro_interno")
        resultado = DjenCapturaResultado.falha_interna()
        resultado.paginas = consulta.paginas
        resultado.janela_dias = consulta.janela_dias

    return registrar_resultado_execucao(resultado)
