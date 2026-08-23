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

DOU_SEARCH_URL = "https://www.in.gov.br/consulta/-/buscar/dou"


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


async def buscar_dou(keyword: str, data_pub: date | None = None) -> list[dict]:
    """Consulta o DOU e retorna publicações normalizadas.

    Retorna ``[]`` SOMENTE quando a consulta foi tecnicamente válida e não há
    publicações. Falha de rede, HTTP, parse ou contrato levanta
    ``DOUIndisponivelError``.
    """
    import httpx

    data_alvo = data_pub or date.today() - timedelta(days=1)
    data_str = data_alvo.strftime("%d-%m-%Y")
    params = {
        "q": keyword,
        "exactDate": data_str,
        "sortType": "0",
        "_search": "null",
        "view": "simple",
        "numberOfPage": "1",
        "publishedFrom": data_str,
        "publishedTo": data_str,
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(DOU_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning(
            "[DOU] fonte indisponível: %s",
            type(exc).__name__,
        )
        raise DOUIndisponivelError(
            f"Consulta ao DOU indisponível ({type(exc).__name__})"
        ) from None

    if not isinstance(data, dict):
        raise DOUIndisponivelError("Consulta ao DOU retornou formato inesperado")

    # Fail-closed: ausência do envelope `content` é quebra de contrato, não
    # evidência de zero publicações. Zero resultado válido é `jsonArray=[]`.
    content = data.get("content")
    if not isinstance(content, dict):
        raise DOUIndisponivelError("Consulta ao DOU retornou content inválido")

    bruto = content.get("jsonArray")
    if bruto is None:
        raise DOUIndisponivelError(
            "Consulta ao DOU não retornou jsonArray no contrato esperado"
        )
    if not isinstance(bruto, list):
        raise DOUIndisponivelError(
            "Consulta ao DOU retornou jsonArray em formato inesperado"
        )
    json_array = [item for item in bruto if isinstance(item, dict)]

    resultados = []
    for item in json_array:
        resultados.append(
            {
                "titulo": item.get("title", ""),
                "resumo": item.get("excerpt", ""),
                "link": f"https://www.in.gov.br{item.get('urlTitle', '')}",
                "secao": str(item.get("artType", "")).replace("DOU - ", ""),
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
