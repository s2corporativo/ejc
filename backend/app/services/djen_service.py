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
#  • comunicação externa é deduplicada atomicamente no PostgreSQL;
#  • vinculação automática só ocorre quando há um único caso ativo compatível;
#  • nenhuma comunicação cria prazo automaticamente.
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter, defaultdict
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
from app.services.djen_http import (
    DJEN_COMUNICACAO_URL,
    DJEN_ITENS_POR_PAGINA,
    criar_cliente_djen,
)

# Siglas de duas letras que aparecem em rótulos de OAB e NÃO são unidade
# federativa — sem isto, "OAB 252599" viria com uf="OA".
_NAO_UF = frozenset({"OA", "NO", "DE", "DA", "DO", "Nº", "N"})

logger = logging.getLogger("ejc.djen")
BASE = DJEN_COMUNICACAO_URL
ITENS_POR_PAGINA = DJEN_ITENS_POR_PAGINA
MAX_PAGINAS = 200
MAX_RETRIES_PAGINA_VAZIA = 2
PAUSA_ENTRE_PAGINAS = 0.25
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


# A API do Comunica/CNJ fica atrás de uma distribuição CloudFront com
# restrição por país: de fora do Brasil ela devolve 403 em QUALQUER rota,
# inclusive /swagger, com este texto no corpo. Sem distinguir esse caso, o
# diagnóstico mostra `http_4xx` e o operador procura o defeito no cadastro de
# OAB — quando a causa é a localização do servidor, que nenhum ajuste de
# cadastro corrige. Verificado em 04/09/2026 (x-amz-cf-pop IAD55).
_MARCA_BLOQUEIO_GEOGRAFICO = "block access from your country"


def _e_bloqueio_geografico(resposta: httpx.Response | None) -> bool:
    if resposta is None or resposta.status_code != 403:
        return False
    try:
        corpo = resposta.text or ""
    except Exception:  # resposta em streaming/consumida — não dá para afirmar
        return False
    return _MARCA_BLOQUEIO_GEOGRAFICO in corpo.lower()


def _classificar_erro_fonte(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        if _e_bloqueio_geografico(exc.response):
            return "geo_bloqueado"
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

def classificar_erro_fonte(exc: Exception) -> str:
    """Classificação sanitizada reutilizável pelos dois fluxos DJEN.

    Retorna somente códigos operacionais estáveis; nunca inclui OAB, URL de
    proxy, credencial ou corpo integral da resposta upstream.
    """
    return _classificar_erro_fonte(exc)


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
    async with criar_cliente_djen(timeout=25) as client:
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


def _numero_processo_item(item: dict) -> str:
    """Extrai o número CNJ de um item sem assumir um único nome de campo."""
    numero = normalizar_processo(
        item.get("numero_processo")
        or item.get("numeroProcesso")
        or item.get("numeroprocessocommascara")
        or ""
    )
    if numero:
        return numero
    return normalizar_processo(extrair_numero_cnj(item.get("texto") or ""))


def _indexar_casos_unicos(casos: list[Case]) -> tuple[dict[str, Case], int]:
    """Indexa apenas números CNJ que apontam para exatamente um caso ativo.

    Mais de um caso ativo com o mesmo número é situação ambígua: nenhuma
    vinculação automática é feita. O item continua capturado para revisão.
    """
    por_numero: dict[str, list[Case]] = defaultdict(list)
    for caso in casos:
        numero = normalizar_processo(caso.numero_processo)
        if numero:
            por_numero[numero].append(caso)

    unicos = {
        numero: encontrados[0]
        for numero, encontrados in por_numero.items()
        if len(encontrados) == 1
    }
    ambiguos = sum(1 for encontrados in por_numero.values() if len(encontrados) > 1)
    return unicos, ambiguos


async def buscar_casos_ativos_por_processos(
    db: AsyncSession,
    numeros: set[str],
) -> dict[str, Case]:
    """Resolve todos os vínculos do lote com uma única consulta ao banco.

    Sem migration disponível nesta etapa, normalizamos o número na expressão
    SQL. Isso troca o antigo custo O(itens × casos) por um scan por captura.
    Índice normalizado fica para a migration estrutural posterior da #968.
    """
    alvos = {normalizar_processo(numero) for numero in numeros}
    alvos.discard("")
    if not alvos:
        return {}

    numero_normalizado = func.regexp_replace(
        Case.numero_processo,
        r"\D",
        "",
        "g",
    )
    casos = (
        await db.execute(
            select(Case).where(
                Case.deleted_at.is_(None),
                Case.numero_processo.isnot(None),
                Case.status.notin_([CaseStatus.encerrado, CaseStatus.arquivado]),
                numero_normalizado.in_(alvos),
            )
        )
    ).scalars().all()
    unicos, ambiguos = _indexar_casos_unicos(list(casos))
    if ambiguos:
        logger.warning(
            "DJEN: %s número(s) de processo com vínculo ambíguo; sem auto-vinculação",
            ambiguos,
        )
    return unicos


async def buscar_caso_ativo_por_processo(
    db: AsyncSession,
    numero: str | None,
) -> Case | None:
    """Adapter compatível; novos lotes usam ``buscar_casos_ativos_por_processos``."""
    alvo = normalizar_processo(numero)
    if not alvo:
        return None
    return (await buscar_casos_ativos_por_processos(db, {alvo})).get(alvo)


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


def extrair_total_djen(payload: dict | list) -> int | None:
    """Total reportado pela API, quando presente e válido."""
    if not isinstance(payload, dict):
        return None
    for chave in ("count", "total", "totalElements"):
        valor = payload.get(chave)
        if valor is None:
            continue
        try:
            total = int(valor)
        except (TypeError, ValueError):
            continue
        if total >= 0:
            return total
    return None


async def consultar_oab(
    numero: str,
    uf: str,
    dias: int = JANELA_RECONCILIACAO_DIAS,
) -> DjenConsultaResultado:
    """Consulta paginada, count-aware e fail-closed para páginas incompletas."""
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
    total_fonte: int | None = None
    pagina = 1
    retries_vazia = 0
    try:
        while pagina <= MAX_PAGINAS:
            payload = await _djen_get({**base_params, "pagina": pagina})
            lote = _extrair_items(payload)
            paginas = pagina
            reportado = extrair_total_djen(payload)
            if reportado is not None:
                total_fonte = reportado

            if not lote:
                # Sem itens só prova exaustão quando a própria fonte não afirma
                # que ainda existem resultados. Caso contrário, retenta a MESMA
                # página: o Comunica pode devolver vazio transitório com HTTP 200.
                if total_fonte is not None and len(todos) < total_fonte:
                    if retries_vazia < MAX_RETRIES_PAGINA_VAZIA:
                        retries_vazia += 1
                        await asyncio.sleep(PAUSA_ENTRE_PAGINAS * retries_vazia)
                        continue
                    logger.error(
                        "DJEN: página %s vazia com %s/%s itens; janela incompleta",
                        pagina, len(todos), total_fonte,
                    )
                    return DjenConsultaResultado(
                        fonte_ok=False,
                        items=[],
                        erro="pagina_vazia_incompleta",
                        paginas=paginas,
                        janela_dias=dias,
                    )
                return DjenConsultaResultado(
                    fonte_ok=True, items=todos, paginas=paginas, janela_dias=dias
                )

            retries_vazia = 0
            for item in lote:
                chave = str(item.get("id") or item.get("hash") or "")
                if chave and chave in vistos:
                    continue
                if chave:
                    vistos.add(chave)
                todos.append(item)

            if total_fonte is not None and len(todos) >= total_fonte:
                return DjenConsultaResultado(
                    fonte_ok=True, items=todos, paginas=paginas, janela_dias=dias
                )
            if len(lote) < ITENS_POR_PAGINA and total_fonte is None:
                return DjenConsultaResultado(
                    fonte_ok=True, items=todos, paginas=paginas, janela_dias=dias
                )

            pagina += 1
            await asyncio.sleep(PAUSA_ENTRE_PAGINAS)

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


def _stmt_inserir_comunicacao(valores: dict):
    """INSERT idempotente: somente o vencedor da corrida cria efeitos derivados."""
    return (
        pg_insert(DjenComunicacao)
        .values(**valores)
        .on_conflict_do_nothing(
            index_elements=[DjenComunicacao.comunicacao_id_externo]
        )
        .returning(DjenComunicacao.id)
    )


async def _emails_usuarios(
    db: AsyncSession,
    user_ids: set[str],
) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.email).where(User.id.in_(user_ids))
        )
    ).all()
    return {str(user_id): email for user_id, email in rows if email}


async def _ingerir_rag_do_caso(db: AsyncSession, item: dict, caso: Case) -> str | None:
    """DJEN → RAG por caso (I4 da análise E2E de IA 2026-09-03).

    O ingestor por OAB monitorada (`ingestors/djen.py`) já grava a comunicação
    como `comunicacao_processual` restrita ao cliente/caso — mas só para as
    OABs de DJEN_OABS_MONITORADAS. A captura por advogado (esta função) não
    ingeria nada: a intimação ficava só na tela de Intimações. Aqui ela entra
    no RAG com `rag_status='pendente'` (a curadoria decide), reutilizando a
    MESMA `chave_origem` e o mesmo `montar_documento` do ingestor — os dois
    caminhos são idempotentes entre si (`upsert_documento` faz o dedup).

    Vetorização adiada (`embutir_vetores=False`): os chunks nascem sem vetor e
    o job horário `reembed_rag_orfaos` os completa. Best-effort: qualquer
    falha vira log (classe do erro) e a captura da intimação segue.
    """
    from app.core.config import get_settings

    if not get_settings().DJEN_CAPTURA_INGERIR_RAG:
        return None
    try:
        from app.services import ingestion_service
        from app.services.ingestors.djen import montar_documento

        doc = montar_documento(item)
        if not doc:
            return None
        doc["case_id"] = caso.id
        doc["client_id"] = caso.client_id
        doc["extra"]["rag_status"] = "pendente"
        doc["extra"]["tipo_fonte"] = "comunicacao_processual_oficial"
        doc["extra"]["origem_captura"] = "djen_service"
        async with db.begin_nested():   # savepoint: erro não derruba a captura
            return await ingestion_service.upsert_documento(
                db, embutir_vetores=False, **doc
            )
    except Exception as exc:  # noqa: BLE001 — RAG é acessório da captura
        logger.warning(
            "DJEN→RAG: ingestão da comunicação do caso %s pulada (%s)",
            caso.id, type(exc).__name__,
        )
        return None


async def _capturar_configurado(
    db: AsyncSession,
    adv: User,
    consulta: DjenConsultaResultado,
) -> DjenCapturaResultado:
    novas = 0
    duplicadas = 0
    ignoradas = 0
    emails: list[EmailDjenPendente] = []

    processos = {
        numero
        for item in consulta.items
        if (numero := _numero_processo_item(item))
    }
    casos_por_processo = await buscar_casos_ativos_por_processos(db, processos)
    responsaveis = {
        str(caso.advogado_responsavel_id)
        for caso in casos_por_processo.values()
        if caso.advogado_responsavel_id
        and str(caso.advogado_responsavel_id) != str(adv.id)
    }
    emails_por_usuario = await _emails_usuarios(db, responsaveis)

    from app.services.notification_service import criar_notificacao_interna

    for item in consulta.items:
        external_id = str(item.get("id") or item.get("hash") or "")
        if not external_id:
            ignoradas += 1
            continue

        texto = (item.get("texto") or "")[:2000]
        numero_processo = _numero_processo_item(item)
        caso = casos_por_processo.get(numero_processo) if numero_processo else None
        if caso:
            marcador = (
                "\n[vinculação automática ao caso pelo nº do processo "
                f"{numero_processo} — conferir]"
            )
            texto = texto[: 2000 - len(marcador)] + marcador

        tribunal = item.get("siglaTribunal") or item.get("sigla_tribunal")
        tipo_comunicacao = (
            item.get("tipoComunicacao")
            or item.get("tipo_comunicacao")
            or ""
        )[:60]
        numero_fonte = (
            item.get("numero_processo")
            or item.get("numeroProcesso")
            or numero_processo
            or None
        )
        comunicacao_id = str(uuid4())
        inserido = (
            await db.execute(
                _stmt_inserir_comunicacao(
                    {
                        "id": comunicacao_id,
                        "comunicacao_id_externo": external_id,
                        "advogado_id": adv.id,
                        "numero_processo": numero_fonte,
                        "tribunal": tribunal,
                        "tipo_comunicacao": tipo_comunicacao,
                        "data_disponibilizacao": _parse_data_disp(
                            item.get("data_disponibilizacao")
                            or item.get("dataDisponibilizacao")
                        ),
                        "texto_resumo": texto,
                        "case_id": caso.id if caso else None,
                    }
                )
            )
        ).scalar_one_or_none()
        if not inserido:
            duplicadas += 1
            continue

        if caso:
            # Intimação de processo vinculado a caso ativo também vira
            # conhecimento DO CASO no RAG (comunicacao_processual, pendente).
            await _ingerir_rag_do_caso(db, item, caso)
            db.add(
                CaseMovimento(
                    id=str(uuid4()),
                    case_id=caso.id,
                    tipo="intimacao",
                    descricao=(
                        f"📨 Intimação DJEN ({tribunal}): "
                        f"{tipo_comunicacao} — tratar na tela "
                        "Intimações [vinculação automática pelo nº do processo]"
                    ),
                )
            )

        destinatario_id = (
            caso.advogado_responsavel_id
            if caso and caso.advogado_responsavel_id
            else adv.id
        )
        titulo = "📨 Nova intimação no DJEN"
        mensagem = (
            f"{tribunal or 'Tribunal'} · proc. "
            f"{numero_fonte or '—'} · {tipo_comunicacao}"
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

        email_destino = (
            adv.email
            if str(destinatario_id) == str(adv.id)
            else emails_por_usuario.get(str(destinatario_id))
        )
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


def oab_para_captura(adv) -> tuple[str, str]:
    """Resolve a OAB usada na captura de intimações, com fallback do perfil.

    AUD27-P3-9: o `User` tem DOIS campos para o mesmo fato — `oab_number`
    (preenchido no perfil) e `djen_oab_numero`/`djen_oab_uf` (lidos pela
    captura) — sem nenhuma reconciliação. Um advogado que preencheu só o do
    perfil era pulado em silêncio pelo job das 06h30: o sistema tinha o dado e
    não capturava nada. Num sistema de prazos, isso é risco de perda.

    Ordem de resolução:
      1. `djen_oab_numero` + `djen_oab_uf` — explícito, sempre vence;
      2. `oab_number`, QUANDO carrega a UF ("252599/MG", "OAB/MG 252599",
         "252599 MG").

    A UF NUNCA é adivinhada. Número de OAB sem UF é ambíguo no país inteiro, e
    supor o estado do escritório monitoraria a inscrição de outro advogado —
    pior que não monitorar, porque pareceria estar funcionando. Sem UF
    determinável, devolve vazio e o chamador registra `oab_nao_configurada`,
    que aparece no diagnóstico.
    """
    numero = re.sub(r"\D", "", (getattr(adv, "djen_oab_numero", "") or ""))
    uf = ((getattr(adv, "djen_oab_uf", "") or "").strip().upper())[:2]
    if numero and len(uf) == 2 and uf.isalpha():
        return numero, uf

    perfil = (getattr(adv, "oab_number", "") or "").strip()
    if not perfil:
        return "", ""

    # UF em qualquer posição: "252599/MG", "OAB/MG 252599", "252599 MG".
    m_uf = re.search(r"\b([A-Za-z]{2})\b", perfil)
    m_num = re.search(r"\d{3,}", perfil)
    if not m_uf or not m_num:
        return "", ""
    uf_perfil = m_uf.group(1).upper()
    if uf_perfil in _NAO_UF:
        return "", ""
    return m_num.group(0), uf_perfil


async def capturar_para_advogado(
    db: AsyncSession,
    adv: User,
    *,
    dias: int = JANELA_RECONCILIACAO_DIAS,
) -> DjenCapturaResultado:
    """Captura uma inscrição em savepoint e registra métricas na task atual.

    O savepoint impede que a falha de um advogado reverta comunicações já
    processadas para advogados anteriores na mesma sessão do scheduler.
    Gate: DJEN_INGEST_ENABLED — o mesmo que protege o job diário
    (job_ingestao_djen). Sem o gate aqui, a captura manual (``capturar-agora``)
    tentaria consulta HTTP real contra a API externa mesmo com a feature
    desativada no ``.env``, mascarando a causa raiz do erro.
    """
    from app.core.config import get_settings as _gs

    if not _gs().DJEN_INGEST_ENABLED:
        return DjenCapturaResultado(
            configurada=True,
            fonte_ok=False,
            recebidas=0,
            novas=0,
            duplicadas=0,
            ignoradas=0,
            erro="feature_desabilitada",
            paginas=0,
            janela_dias=0,
        )
    numero, uf = oab_para_captura(adv)
    if not numero or not uf:
        return registrar_resultado_execucao(
            DjenCapturaResultado.sem_configuracao()
        )

    consulta = await consultar_oab(numero, uf, dias=dias)
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
