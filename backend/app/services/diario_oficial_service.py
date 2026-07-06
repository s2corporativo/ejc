# ── app/services/diario_oficial_service.py ────────────────────────────────────
# Monitor de Diário Oficial — captura publicações pela API do LexML/DOU.
# Usa a API pública do DOU (imprensa.in.gov.br) sem autenticação.
# Sem LGPD: não envia dados de clientes, apenas palavras-chave genéricas.
from __future__ import annotations
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

DOU_SEARCH_URL = "https://www.in.gov.br/consulta/-/buscar/dou"


async def buscar_dou(keyword: str, data_pub: date | None = None) -> list[dict]:
    """
    Consulta o Diário Oficial da União pela API do in.gov.br.
    Retorna lista de publicações com: titulo, resumo, link, secao, data.
    Retorna [] em caso de falha ou sem resultado.
    """
    import httpx

    data_str = (data_pub or date.today() - timedelta(days=1)).strftime("%d-%m-%Y")
    params = {
        "q":            keyword,
        "exactDate":    data_str,
        "sortType":     "0",
        "_search":      "null",
        "view":         "simple",
        "numberOfPage": "1",
        "publishedFrom": data_str,
        "publishedTo":   data_str,
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(DOU_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning(f"[DOU] Falha ao consultar '{keyword}': {e}")
        return []

    # Normaliza resposta — defensivo: `content` pode vir null/lista na resposta.
    content = data.get("content") if isinstance(data, dict) else None
    json_array = content.get("jsonArray", []) if isinstance(content, dict) else []
    resultados = []
    for item in json_array:
        resultados.append({
            "titulo":          item.get("title", ""),
            "resumo":          item.get("excerpt", ""),
            "link":            f"https://www.in.gov.br{item.get('urlTitle', '')}",
            "secao":           str(item.get("artType", "")).replace("DOU - ", ""),
            "data_publicacao": data_pub or date.today() - timedelta(days=1),
            "edicao":          item.get("editionNumber", ""),
        })
    return resultados


async def processar_alertas_dou(db) -> int:
    """
    Verifica todas as keywords ativas, busca no DOU e persiste os alertas novos.

    Para cada alerta NOVO (dedup por link+keyword garante disparo único):
      • Vinculação automática (R10/Seção 12): se a keyword não tem caso fixo,
        extrai nº CNJ do título/resumo e casa com Case ativo (normalizando os
        dois lados — só dígitos). Vínculo automático é marcado no resumo para
        conferência humana.
      • Notificação ativa: interna (sino) ao advogado responsável do caso
        vinculado; sem caso/responsável, ao dono da keyword (created_by).
        E-mail só se EMAIL_ENABLED (enviar_email é no-op seguro).

    Retorna o total de alertas novos criados.
    """
    from uuid import uuid4
    from sqlalchemy import select
    from app.models.diario_oficial import DiarioOficialKeyword, DiarioOficialAlerta
    from app.models.case import Case
    from app.models.user import User
    from app.services.djen_service import (
        extrair_numero_cnj, buscar_caso_ativo_por_processo, normalizar_processo,
    )
    from app.services.notification_service import (
        criar_notificacao_interna, enviar_email,
    )

    ontem = date.today() - timedelta(days=1)

    keywords = (await db.execute(
        select(DiarioOficialKeyword).where(
            DiarioOficialKeyword.ativo.is_(True),
            DiarioOficialKeyword.fonte == "dou",
        )
    )).scalars().all()

    if not keywords:
        return 0

    novos = 0
    for kw in keywords:
        resultados = await buscar_dou(kw.keyword, ontem)
        for r in resultados:
            # Dedup: verifica se esse link já existe
            existe = (await db.execute(
                select(DiarioOficialAlerta).where(
                    DiarioOficialAlerta.link == r["link"],
                    DiarioOficialAlerta.keyword_id == kw.id,
                )
            )).scalar_one_or_none()
            if existe:
                continue

            # ── Vinculação automática publicação → caso ──────────────────────
            case_id = kw.case_id          # vínculo fixo da keyword tem prioridade
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
                        resumo = resumo[:2000 - len(marcador)] + marcador

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

            # ── Notificação ativa (só na criação) ────────────────────────────
            try:
                if case is None and case_id:
                    case = (await db.execute(select(Case).where(
                        Case.id == case_id
                    ))).scalar_one_or_none()
                destinatario_id = (
                    case.advogado_responsavel_id
                    if case and case.advogado_responsavel_id
                    else kw.created_by
                )
                if destinatario_id:
                    titulo_n = "📰 Nova publicação no Diário Oficial"
                    msg_n = (
                        f"Keyword '{kw.keyword}': {r['titulo'][:150]}"
                        + (" · vinculada automaticamente ao caso (conferir)"
                           if case and not kw.case_id else "")
                    )
                    await criar_notificacao_interna(
                        db, destinatario_id, titulo_n, msg_n,
                        tipo="diario_oficial", link="/diario-oficial",
                    )
                    email_dest = (await db.execute(select(User.email).where(
                        User.id == destinatario_id
                    ))).scalar_one_or_none()
                    if email_dest:
                        await enviar_email(
                            email_dest, f"[EJC] {titulo_n}",
                            f"<p>{msg_n}</p>"
                            f"<p><a href='{r['link']}'>Ver publicação</a></p>",
                        )
            except Exception as e:
                logger.warning(f"[DOU] Notificação falhou (não-fatal): {e}")

    if novos > 0:
        await db.commit()

    return novos
