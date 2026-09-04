# ── app/services/diario_oficial_service.py ────────────────────────────────────
# Monitor de Diário Oficial — captura publicações pela API do DOU.
# Usa a consulta pública do in.gov.br sem autenticação.
#
# Regra operacional crítica: "nenhum resultado" NÃO pode ser confundido com
# "fonte indisponível". Falha de transporte/HTTP/JSON é exceção tipada e fica
# visível num heartbeat sanitizado; uma consulta válida com 0 publicações é
# sucesso normal.
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Índice do dia inteiro, uma requisição por seção, SEM paginação e SEM senha.
#
# A URL anterior (`/consulta/-/buscar/dou`) foi abandonada por dois defeitos
# medidos em 04/09/2026, ambos reproduzidos:
#   1. o portal derruba a conexão quando o User-Agent é o do httpx
#      (`RemoteProtocolError`); com UA de navegador responde 200;
#   2. mesmo com UA aceito, a resposta é HTML — `resp.json()` estoura. O
#      envelope `content.jsonArray` que o código exigia não existe mais.
# O job rodava todo dia às 06h, caía em DOUIndisponivelError e nunca capturava
# nada; o teste que o cobria injetava um contrato que a fonte nunca devolveu.
#
# O índice entrega o dia inteiro numa chamada (medido: DO1=297, DO2=752,
# DO3=2167 itens), com JSON embutido em `<script id="params">`. Filtrar as
# keywords localmente é mais barato e mais robusto do que depender do portlet
# de busca, que pagina por cursor via POST.
DOU_INDEX_URL = "https://www.in.gov.br/leiturajornal"

# UA de navegador: o portal recusa o UA padrão do httpx (defeito 1 acima).
_DOU_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# Seções: DO1 atos normativos, DO2 pessoal, DO3 contratos/licitações.
_DOU_SECOES_PADRAO = ("do1", "do2", "do3")

# Cache do índice POR EXECUÇÃO: `processar_alertas_dou` chama `buscar_dou` uma
# vez por keyword, e sem isto N keywords custariam N×3 downloads do dia inteiro.
# Premissa de worker único do EJC (mesma dos rate-limits em memória).
_INDICE_CACHE: dict[tuple[str, str], list[dict]] = {}


class DOUIndisponivelError(RuntimeError):
    """Falha técnica na consulta ao DOU; nunca representa "zero resultados"."""


_DOU_STATUS: dict[str, Any] = {
    "status": "nunca_executado",
    "ultima_execucao": None,
    "ultima_execucao_ok": None,
    "ultima_quantidade": None,
    "falhas_consecutivas": 0,
    # Execuções OK SEGUIDAS que não trouxeram nenhuma publicação. O heartbeat já
    # media resultado por execução; o que faltava era a TENDÊNCIA — "0
    # resultado(s)" todo dia lê-se como "ok", e é assim que um monitor
    # tecnicamente saudável convive com uma captura que nunca capturou nada
    # (a armadilha que o CLAUDE.md registra para o DJEN).
    "execucoes_sem_resultado": 0,
    "ultimo_erro_tipo": None,
}

# O job roda uma vez por dia (`scheduler.py`, CronTrigger hour=6). Uma semana
# inteira sem nenhuma publicação casando com NENHUMA keyword ativa é sinal de
# configuração errada, não de silêncio do Diário.
DOU_EXECUCOES_SEM_RESULTADO_ALERTA = 7


def _registrar_status_dou(*, ok: bool, quantidade: int | None = None,
                           erro: Exception | None = None) -> None:
    _DOU_STATUS["ultima_execucao"] = datetime.now(timezone.utc).isoformat()
    _DOU_STATUS["ultima_execucao_ok"] = ok
    if ok:
        capturadas = int(quantidade or 0)
        _DOU_STATUS["status"] = "ok"
        _DOU_STATUS["ultima_quantidade"] = capturadas
        _DOU_STATUS["falhas_consecutivas"] = 0
        # Falha NÃO conta como execução sem resultado: são defeitos diferentes,
        # e somar os dois esconderia o que cada um diz.
        _DOU_STATUS["execucoes_sem_resultado"] = (
            0 if capturadas
            else int(_DOU_STATUS.get("execucoes_sem_resultado") or 0) + 1
        )
        _DOU_STATUS["ultimo_erro_tipo"] = None
    else:
        _DOU_STATUS["status"] = "degradado"
        _DOU_STATUS["falhas_consecutivas"] = int(
            _DOU_STATUS.get("falhas_consecutivas") or 0
        ) + 1
        # Somente o TIPO da exceção é persistido em memória/diagnóstico. Corpo
        # HTTP, keyword e conteúdo de publicação não entram no heartbeat.
        _DOU_STATUS["ultimo_erro_tipo"] = type(erro).__name__ if erro else "Erro"


def status_dou() -> dict[str, Any]:
    """Heartbeat operacional sem keyword, conteúdo, PII ou segredo."""
    return dict(_DOU_STATUS)


def _extrair_json_do_indice(html: str) -> list[dict]:
    """Extrai o `jsonArray` do `<script id="params">` da página do índice.

    O JSON vem embutido no HTML (não há endpoint JSON puro: `?format=xml`
    devolve HTML e `/api/dou/<slug>` responde 404). Ausência do script é
    QUEBRA DE CONTRATO, não zero publicações — o portal muda sem aviso, e foi
    exatamente assim que a versão anterior deste módulo parou de funcionar sem
    ninguém perceber.
    """
    import json
    import re

    m = re.search(
        r'<script[^>]*id="params"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not m:
        raise DOUIndisponivelError(
            "Índice do DOU sem <script id='params'> — contrato do portal mudou"
        )
    try:
        dados = json.loads(m.group(1).strip())
    except json.JSONDecodeError as exc:
        raise DOUIndisponivelError("Índice do DOU com JSON inválido") from exc

    if not isinstance(dados, dict):
        raise DOUIndisponivelError("Índice do DOU em formato inesperado")
    bruto = dados.get("jsonArray")
    if bruto is None:
        raise DOUIndisponivelError("Índice do DOU sem jsonArray")
    if not isinstance(bruto, list):
        raise DOUIndisponivelError("jsonArray do DOU em formato inesperado")
    return [i for i in bruto if isinstance(i, dict)]


async def _carregar_indice(data_str: str, secao: str) -> list[dict]:
    """Baixa (e memoiza) o índice de uma seção do dia."""
    import httpx

    chave = (data_str, secao)
    if chave in _INDICE_CACHE:
        return _INDICE_CACHE[chave]

    try:
        async with httpx.AsyncClient(
            timeout=45,
            follow_redirects=True,
            headers={"User-Agent": _DOU_USER_AGENT},
        ) as client:
            resp = await client.get(
                DOU_INDEX_URL, params={"data": data_str, "secao": secao}
            )
            resp.raise_for_status()
            html = resp.text
    except DOUIndisponivelError:
        raise
    except Exception as exc:
        logger.warning("[DOU] índice %s/%s indisponível: %s",
                       data_str, secao, type(exc).__name__)
        raise DOUIndisponivelError(
            f"Índice do DOU indisponível ({type(exc).__name__})"
        ) from None

    itens = _extrair_json_do_indice(html)
    _INDICE_CACHE[chave] = itens
    return itens


def limpar_cache_indice() -> None:
    """Zera o cache do índice — chamado no início de cada execução do job."""
    _INDICE_CACHE.clear()


def _casa_keyword(item: dict, keyword: str) -> bool:
    """Casamento local, sem acento e sem caixa, no título e no excerto.

    O índice traz `content` truncado em ~403 caracteres — é excerto, não
    inteiro teor. Por isso o casamento aqui é de TRIAGEM: indica o ato a
    conferir, não substitui a leitura da publicação.
    """
    import unicodedata

    def _norm(t: str) -> str:
        sem_acento = "".join(
            c for c in unicodedata.normalize("NFD", t or "")
            if unicodedata.category(c) != "Mn"
        )
        return sem_acento.casefold()

    alvo = _norm(keyword).strip()
    if not alvo:
        return False
    campos = " ".join(
        str(item.get(c) or "") for c in ("title", "titulo", "subTitulo", "content")
    )
    return alvo in _norm(campos)


async def buscar_dou(keyword: str, data_pub: date | None = None) -> list[dict]:
    """Consulta o DOU e retorna publicações normalizadas para a keyword.

    Retorna ``[]`` SOMENTE quando a consulta foi tecnicamente válida e nenhuma
    publicação casou. Falha de rede, HTTP, parse ou contrato levanta
    ``DOUIndisponivelError`` — a distinção que impede "fonte quebrada" de se
    disfarçar de "nada publicado hoje".
    """
    data_alvo = data_pub or date.today() - timedelta(days=1)
    data_str = data_alvo.strftime("%d-%m-%Y")

    resultados: list[dict] = []
    for secao in _DOU_SECOES_PADRAO:
        for item in await _carregar_indice(data_str, secao):
            if not _casa_keyword(item, keyword):
                continue
            url_title = str(item.get("urlTitle") or "").lstrip("/")
            resultados.append(
                {
                    "titulo": item.get("title") or item.get("titulo") or "",
                    "resumo": item.get("content", ""),
                    "link": (
                        f"https://www.in.gov.br/web/dou/-/{url_title}"
                        if url_title else DOU_INDEX_URL
                    ),
                    "secao": str(item.get("pubName") or secao).upper(),
                    "data_publicacao": data_alvo,
                    "edicao": item.get("editionNumber", ""),
                }
            )
    return resultados


async def processar_alertas_dou(db) -> int:
    """Busca keywords ativas, persiste alertas e mantém heartbeat operacional.

    Uma keyword com falha não transforma o lote inteiro em "zero publicações":
    a falha é registrada e as demais keywords continuam. Se qualquer consulta
    falhar, o heartbeat final fica ``degradado`` mesmo que outras tenham êxito.
    """
    from uuid import uuid4

    from sqlalchemy import select

    from app.models.case import Case
    from app.models.diario_oficial import DiarioOficialAlerta, DiarioOficialKeyword

    # Índice do dia é baixado uma vez por seção e reusado por todas as
    # keywords desta execução; zerar aqui evita servir índice de ontem.
    limpar_cache_indice()
    from app.models.user import User
    from app.services.djen_service import (
        buscar_caso_ativo_por_processo,
        extrair_numero_cnj,
        normalizar_processo,
    )
    from app.services.notification_service import (
        criar_notificacao_interna,
        enviar_email,
    )

    ontem = date.today() - timedelta(days=1)

    keywords = (
        await db.execute(
            select(DiarioOficialKeyword).where(
                DiarioOficialKeyword.ativo.is_(True),
                DiarioOficialKeyword.fonte == "dou",
            )
        )
    ).scalars().all()

    if not keywords:
        return 0

    novos = 0
    total_resultados = 0
    falhas: list[Exception] = []

    for kw in keywords:
        try:
            resultados = await buscar_dou(kw.keyword, ontem)
            total_resultados += len(resultados)
        except DOUIndisponivelError as exc:
            falhas.append(exc)
            # Não logar a keyword: pode ser nome de pessoa/cliente/processo.
            logger.error("[DOU] consulta de keyword falhou: %s", type(exc).__name__)
            continue

        for r in resultados:
            existe = (
                await db.execute(
                    select(DiarioOficialAlerta).where(
                        DiarioOficialAlerta.link == r["link"],
                        DiarioOficialAlerta.keyword_id == kw.id,
                    )
                )
            ).scalar_one_or_none()
            if existe:
                continue

            case_id = kw.case_id
            case = None
            resumo = r["resumo"][:2000]
            if not case_id:
                num_cnj = extrair_numero_cnj(f"{r['titulo']} {r['resumo']}")
                if num_cnj:
                    case = await buscar_caso_ativo_por_processo(db, num_cnj)
                    if case:
                        case_id = case.id
                        marcador = (
                            f"\n[vinculação automática ao caso pelo nº do "
                            f"processo {normalizar_processo(num_cnj)} — conferir]"
                        )
                        resumo = resumo[: 2000 - len(marcador)] + marcador

            alerta = DiarioOficialAlerta(
                id=str(uuid4()),
                fonte="dou",
                edicao=r["edicao"],
                data_publicacao=r["data_publicacao"],
                secao=r["secao"],
                titulo=r["titulo"][:500],
                resumo=resumo,
                link=r["link"],
                keyword_match=kw.keyword[:200],
                keyword_id=kw.id,
                case_id=case_id,
            )
            db.add(alerta)
            novos += 1

            try:
                if case is None and case_id:
                    case = (
                        await db.execute(select(Case).where(Case.id == case_id))
                    ).scalar_one_or_none()
                destinatario_id = (
                    case.advogado_responsavel_id
                    if case and case.advogado_responsavel_id
                    else kw.created_by
                )
                if destinatario_id:
                    titulo_n = "Nova publicação no Diário Oficial"
                    msg_n = (
                        f"Publicação encontrada para monitor cadastrado: "
                        f"{r['titulo'][:150]}"
                        + (
                            " · vinculada automaticamente ao caso (conferir)"
                            if case and not kw.case_id
                            else ""
                        )
                    )
                    await criar_notificacao_interna(
                        db,
                        destinatario_id,
                        titulo_n,
                        msg_n,
                        tipo="diario_oficial",
                        link="/diario-oficial",
                    )
                    email_dest = (
                        await db.execute(
                            select(User.email).where(User.id == destinatario_id)
                        )
                    ).scalar_one_or_none()
                    if email_dest:
                        await enviar_email(
                            email_dest,
                            f"[EJC] {titulo_n}",
                            f"<p>{msg_n}</p><p><a href='{r['link']}'>Ver publicação</a></p>",
                        )
            except Exception as exc:
                logger.warning(
                    "[DOU] notificação falhou (não-fatal): %s",
                    type(exc).__name__,
                )

    if novos > 0:
        await db.commit()

    if falhas:
        _registrar_status_dou(ok=False, erro=falhas[-1])
    else:
        _registrar_status_dou(ok=True, quantidade=total_resultados)

    return novos
