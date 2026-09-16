"""
citation_check.py — Verificador anti-alucinação de citações (#46).

Extrai súmulas e artigos citados num texto (peça/parecer gerado por IA) e
confirma CADA UM contra o RAG oficial. Verificação de artigo é determinística:
número + diploma + versão vigente precisam coincidir no mesmo KnowledgeDoc.

O campo legado `fonte` continua textual. A fachada `verificar_citacoes()` também
expõe evidência estrutural (doc_id, chave_origem, versão e vigência), para que o
selo positivo seja auditável sem depender de similaridade semântica.
"""
from __future__ import annotations

import re

from sqlalchemy import text


async def _existe_sumula(db, num: str, orgao: str) -> str | None:
    """Lookup exato por chave_origem (ingestão nova) + fallback por título."""
    from app.services.ai_service import _filtros_gate_rag

    orgao_norm = (orgao or "").strip().lower()
    keys = (
        [f"sumula:{orgao_norm}:{num}"]
        if orgao_norm
        else [f"sumula:{tribunal}:{num}" for tribunal in ("stf", "stj", "tst")]
    )
    row = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                "SELECT kd.titulo FROM knowledge_docs kd "
                "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE "
                "AND kd.chave_origem = ANY(:k) "
                + _filtros_gate_rag(False)
                + " LIMIT 1"
            ),
            {"k": keys},
        )
    ).first()
    if row:
        return row[0]

    params = {"t": f"Súmula {num} %"}
    cond = ""
    if orgao_norm:
        cond = " AND kd.tribunal = :org"
        params["org"] = orgao_norm.upper()
    row = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                "SELECT kd.titulo FROM knowledge_docs kd "
                "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE "
                "AND (kd.categoria LIKE 'sumula%' "
                "OR kd.chave_origem LIKE 'sumula:%') "
                "AND kd.titulo ILIKE :t"
                + cond
                + " "
                + _filtros_gate_rag(False)
                + " LIMIT 1"
            ),
            params,
        )
    ).first()
    return row[0] if row else None


_SLUG_POR_DIPLOMA = {
    "cf": "cf88",
    "cpc": "cpc",
    "cc": "cc",
    "clt": "clt",
    "cdc": "cdc",
    "cpp": "cpp",
    "cp": "cp",
    "ctn": "ctn",
}


_RE_LEI_CITADA = re.compile(
    r"lei\s*n?(?:[.\s]*[ºo°])?[.\s]*([\d.]+)(?:\s*/\s*(\d{2,4}))?",
    re.IGNORECASE,
)


def _dados_lei_citada(diploma: str) -> tuple[str, str | None] | None:
    match = _RE_LEI_CITADA.search(diploma)
    if not match:
        return None
    numero = re.sub(r"\D", "", match.group(1))
    ano = match.group(2)
    return (numero, ano) if numero else None


def _chave_catalogo_por_lei(numero: str, ano: str | None) -> str | None:
    """Resolve a lei para uma chave oficial exata do catálogo Planalto."""
    from app.services.ingestors.planalto import CATALOGO

    candidatas: list[str] = []
    for item in CATALOGO:
        match = re.search(
            r"\bLei\s+([\d.]+)/(\d{4})\b",
            item.get("titulo") or "",
            re.IGNORECASE,
        )
        if not match:
            continue
        numero_catalogo = re.sub(r"\D", "", match.group(1))
        ano_catalogo = match.group(2)
        if numero_catalogo != numero:
            continue
        if ano and not (
            ano_catalogo == ano or ano_catalogo.endswith(ano.zfill(2))
        ):
            continue
        candidatas.append(f"planalto:{item['slug']}")
    return candidatas[0] if len(candidatas) == 1 else None


def _restringir_ao_diploma(diploma: str | None, params: dict) -> str | None:
    """Prende a busca ao diploma citado e falha fechado em ambiguidade."""
    normalizado = (diploma or "").strip().lower()
    if normalizado in _SLUG_POR_DIPLOMA:
        params["chave"] = f"planalto:{_SLUG_POR_DIPLOMA[normalizado]}"
        return "AND kd.chave_origem = :chave "

    if normalizado.startswith("lei"):
        dados = _dados_lei_citada(normalizado)
        if not dados:
            return None
        chave = _chave_catalogo_por_lei(*dados)
        if not chave:
            return None
        params["chave"] = chave
        return "AND kd.chave_origem = :chave "
    return None


def _regex_artigo(num: str) -> str:
    """Boundary exato: casa `Art. 300.`, mas não `Art. 3000` nem `300-A`."""
    numero = re.sub(r"\D", "", num)
    if not numero:
        return r"a^"
    return (
        rf"(^|[^[:alnum:]_])art(igo)?[.]?[[:space:]]*{numero}"
        r"[º°ªa]?([[:space:].,;:()—]|$)"
    )


def _fonte_da_linha(row, *, vigente_esperada: bool) -> dict | None:
    """Normaliza linha real (6 colunas) e fakes legados (título, versão)."""
    if not row:
        return None
    if len(row) >= 6:
        return {
            "doc_id": row[0],
            "titulo": row[1],
            "chave_origem": row[2],
            "versao": row[3],
            "vigente": bool(row[4]),
            "fonte_url": row[5],
        }
    if len(row) == 2:
        return {
            "doc_id": None,
            "titulo": row[0],
            "chave_origem": None,
            "versao": row[1],
            "vigente": vigente_esperada,
            "fonte_url": None,
        }
    return None


async def _fonte_artigo(
    db,
    num: str,
    diploma: str | None,
    *,
    vigente: bool,
) -> dict | None:
    """Retorna evidência estrutural do artigo dentro do diploma exato.

    Em consulta de direito atual, registros marcados como revogados ou suspensos
    não podem satisfazer a citação mesmo que o flag técnico `vigente` esteja incoerente.
    """
    from app.services.ai_service import _filtros_gate_rag

    params: dict = {"artigo_re": _regex_artigo(num)}
    cond = _restringir_ao_diploma(diploma, params)
    if cond is None:
        return None
    vigencia_sql = "TRUE" if vigente else "FALSE"
    status_clause = (
        "AND COALESCE(kd.extra->>'legal_status', '') NOT IN ('revogada', 'suspensa') "
        if vigente
        else ""
    )
    row = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                "SELECT kd.id, kd.titulo, kd.chave_origem, kd.versao, "
                "kd.vigente, kd.fonte FROM knowledge_chunks kc "
                "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
                f"WHERE kd.deleted_at IS NULL AND kd.vigente = {vigencia_sql} "
                + status_clause
                + "AND kd.categoria LIKE 'legislacao%' "
                + cond
                + "AND kc.conteudo ~* :artigo_re "
                + _filtros_gate_rag(False)
                + " ORDER BY kd.versao DESC LIMIT 1"
            ),
            params,
        )
    ).first()
    fonte = _fonte_da_linha(row, vigente_esperada=vigente)
    if (
        fonte
        and fonte["chave_origem"] is not None
        and fonte["chave_origem"] != params.get("chave")
    ):
        return None
    return fonte


async def _fonte_artigo_vigencia_pendente(
    db,
    num: str,
    diploma: str | None,
) -> dict | None:
    """Localiza o artigo em versão ATUAL que falha só no gate de vigência.

    Este lookup é diagnóstico: mantém aprovação, bloqueios, revogação e corpus
    fictício, ignorando apenas a exigência de proveniência positiva de vigência.
    O retorno NUNCA autoriza status ``verificada``; serve para não chamar de
    "superada" uma redação atual que está apenas aguardando curadoria jurídica.
    """
    from app.services.ai_service import _filtros_gate_rag

    params: dict = {"artigo_re": _regex_artigo(num)}
    cond = _restringir_ao_diploma(diploma, params)
    if cond is None:
        return None
    row = (
        await db.execute(
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                "SELECT kd.id, kd.titulo, kd.chave_origem, kd.versao, "
                "kd.vigente, kd.fonte FROM knowledge_chunks kc "
                "JOIN knowledge_docs kd ON kd.id = kc.doc_id "
                "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE "
                "AND kd.categoria LIKE 'legislacao%' "
                + cond
                + "AND kc.conteudo ~* :artigo_re "
                + _filtros_gate_rag(False, ignorar_gate_vigencia=True)
                + " ORDER BY kd.versao DESC LIMIT 1"
            ),
            params,
        )
    ).first()
    fonte = _fonte_da_linha(row, vigente_esperada=True)
    if (
        fonte
        and fonte["chave_origem"] is not None
        and fonte["chave_origem"] != params.get("chave")
    ):
        return None
    return fonte


async def _sumula_superada(db, num: str, orgao: str) -> dict | None:
    from app.services.ai_service import _filtros_gate_rag

    orgao_norm = (orgao or "").strip().lower()
    keys = (
        [f"sumula:{orgao_norm}:{num}"]
        if orgao_norm
        else [f"sumula:{tribunal}:{num}" for tribunal in ("stf", "stj", "tst")]
    )
    row = (
        await db.execute(
            # SQL literal com bind params; a regra marca todo text(), sem olhar
            # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(
                "SELECT kd.titulo, kd.versao FROM knowledge_docs kd "
                "WHERE kd.deleted_at IS NULL AND kd.vigente = FALSE "
                "AND kd.chave_origem = ANY(:k) "
                + _filtros_gate_rag(False)
                + " ORDER BY kd.versao DESC LIMIT 1"
            ),
            {"k": keys},
        )
    ).first()
    return {"titulo": row[0], "versao": row[1]} if row else None


async def _artigo_superado(
    db,
    num: str,
    diploma: str | None = None,
) -> dict | None:
    return await _fonte_artigo(db, num, diploma, vigente=False)


async def _existe_artigo(
    db,
    num: str,
    diploma: str | None = None,
) -> str | None:
    """Lookup retrocompatível: devolve título, usando evidência estrutural exata."""
    fonte = await _fonte_artigo(db, num, diploma, vigente=True)
    return fonte["titulo"] if fonte else None


def _campos_fonte(fonte: dict | None) -> dict:
    return {
        "fonte_doc_id": fonte.get("doc_id") if fonte else None,
        "fonte_titulo": fonte.get("titulo") if fonte else None,
        "fonte_chave_origem": fonte.get("chave_origem") if fonte else None,
        "fonte_versao": fonte.get("versao") if fonte else None,
        "fonte_vigente": fonte.get("vigente") if fonte else None,
        "fonte_url": fonte.get("fonte_url") if fonte else None,
    }


async def verificar_citacoes(
    db,
    texto: str,
    *,
    consultar_datajud: bool = False,
) -> dict:
    """Fachada canônica com shape legado + evidência técnica para artigos."""
    from app.services.verificador_jurisprudencia import (
        analisar_texto,
        verificar_jurisprudencia,
    )

    relatorio = await verificar_jurisprudencia(
        db,
        texto,
        consultar_datajud=consultar_datajud,
    )
    artigos = iter(
        achado for achado in analisar_texto(texto) if achado["tipo"] == "artigo"
    )
    for citacao in relatorio.get("citacoes", []):
        if citacao.get("tipo") != "artigo":
            continue
        achado = next(artigos, None)
        fonte = None
        if achado and citacao.get("status") == "verificada":
            fonte = await _fonte_artigo(
                db,
                achado["numero"],
                achado.get("diploma"),
                vigente=True,
            )
        elif achado and citacao.get("vigencia_pendente"):
            fonte = await _fonte_artigo_vigencia_pendente(
                db,
                achado["numero"],
                achado.get("diploma"),
            )
        elif achado and citacao.get("status") == "possivelmente_desatualizada":
            fonte = await _fonte_artigo(
                db,
                achado["numero"],
                achado.get("diploma"),
                vigente=False,
            )
        citacao.update(_campos_fonte(fonte))
    return relatorio
