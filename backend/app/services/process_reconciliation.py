"""Reconciliação determinística de processos para a Entrada Única.

Objetivos:
- bloquear duplicidade quando um CNJ já existe no EJC;
- sugerir correspondência com caso pré-processual existente;
- classificar a entrada como já cadastrada, provável correspondência,
  novo processo ou informações insuficientes;
- nunca promover/vincular automaticamente um caso sem revisão humana.

Não usa IA e não grava dados.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import pode_ver_caso_resumido
from app.models.case import Case
from app.models.case_parte import CaseParte
from app.models.process import Process
from app.services.validators_service import (
    normalizar_cnj as _normalizar_cnj_canonico,
    validar_cnj,
)

_CNJ_RE = re.compile(
    r"(?<!\d)(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d{20})(?!\d)"
)


def normalizar_cnj(valor: str | None) -> str | None:
    digitos = _normalizar_cnj_canonico(valor or "")
    return digitos if len(digitos) == 20 else None


def formatar_cnj(digitos: str) -> str:
    return (
        f"{digitos[:7]}-{digitos[7:9]}.{digitos[9:13]}."
        f"{digitos[13]}.{digitos[14:16]}.{digitos[16:20]}"
    )


def extrair_cnjs(texto: str | None) -> list[str]:
    """Extrai CNJs canônicos, preservando ordem e removendo repetições."""
    vistos: set[str] = set()
    saida: list[str] = []
    for achado in _CNJ_RE.findall(texto or ""):
        norm = normalizar_cnj(achado)
        if norm and validar_cnj(achado) and norm not in vistos:
            vistos.add(norm)
            saida.append(formatar_cnj(norm))
    return saida


def _texto_norm(valor: str | None) -> str:
    bruto = unicodedata.normalize("NFKD", valor or "")
    sem_acento = "".join(c for c in bruto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def _like_literal(valor: str) -> str:
    """Escapa curingas de LIKE; a consulta continua parametrizada pelo ORM."""
    return valor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _similaridade(a: str | None, b: str | None) -> int:
    """Pontuação conservadora 0..40; não é decisão jurídica."""
    na, nb = _texto_norm(a), _texto_norm(b)
    if not na or not nb:
        return 0
    if na == nb:
        return 40
    if len(na) >= 6 and len(nb) >= 6 and (na in nb or nb in na):
        return 32
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return 0
    jaccard = len(ta & tb) / len(ta | tb)
    if jaccard >= 0.75:
        return 28
    if jaccard >= 0.50:
        return 20
    return 0


def _cnj_digits_sql(col):
    expr = col
    for char in (".", "-", "/", " "):
        expr = func.replace(expr, char, "")
    return expr


async def buscar_casos_por_cnj(
    db: AsyncSession,
    user: Any,
    numero_cnj: str,
) -> list[dict[str, Any]]:
    """Busca CNJ em cases e processes, com dedup e proteção de carteira."""
    norm = normalizar_cnj(numero_cnj)
    if not norm:
        return []

    case_ids: set[str] = set()
    rows_case = (
        await db.execute(
            select(Case).where(
                Case.deleted_at.is_(None),
                _cnj_digits_sql(Case.numero_processo) == norm,
            ).limit(10)
        )
    ).scalars().all()
    for caso in rows_case:
        case_ids.add(caso.id)

    rows_proc = (
        await db.execute(
            select(Process.case_id).where(
                Process.deleted_at.is_(None),
                _cnj_digits_sql(Process.numero_cnj) == norm,
            ).limit(10)
        )
    ).scalars().all()
    case_ids.update(str(i) for i in rows_proc if i)

    if not case_ids:
        return []

    casos = (
        await db.execute(
            select(Case).where(Case.id.in_(case_ids), Case.deleted_at.is_(None))
        )
    ).scalars().all()

    visiveis: list[dict[str, Any]] = []
    protegido = False
    for caso in casos:
        if pode_ver_caso_resumido(user, caso):
            visiveis.append(
                {
                    "case_id": caso.id,
                    "numero_interno": caso.numero_interno,
                    "titulo": caso.titulo,
                    "status": getattr(caso.status, "value", str(caso.status)),
                    "fase": getattr(caso.fase, "value", str(caso.fase)),
                    "has_judicial_process": bool(caso.has_judicial_process),
                    "protegido": False,
                    "score": 100,
                    "motivos": ["CNJ idêntico já cadastrado"],
                }
            )
        else:
            protegido = True

    if protegido:
        visiveis.append(
            {
                "case_id": None,
                "numero_interno": None,
                "titulo": "Processo já existente em carteira protegida",
                "status": None,
                "fase": None,
                "has_judicial_process": None,
                "protegido": True,
                "score": 100,
                "motivos": ["CNJ idêntico em registro protegido"],
            }
        )
    return visiveis


async def _candidatos_por_partes(
    db: AsyncSession,
    user: Any,
    *,
    cliente_id: str | None,
    cliente_nome: str | None,
    parte_contraria: str | None,
    assunto: str | None,
    tem_cnj: bool,
) -> list[dict[str, Any]]:
    condicoes = []
    if cliente_id:
        condicoes.append(Case.client_id == cliente_id)

    nome_limpo = (cliente_nome or "").strip()
    case_ids_por_nome: set[str] = set()
    if len(nome_limpo) >= 5:
        nome_busca = _like_literal(nome_limpo[:120])
        ids_nome = (
            await db.execute(
                select(CaseParte.case_id)
                .where(
                    CaseParte.ativo.is_(True),
                    CaseParte.nome.ilike(f"%{nome_busca}%", escape="\\"),
                )
                .limit(50)
            )
        ).scalars().all()
        case_ids_por_nome = {str(i) for i in ids_nome if i}
        if case_ids_por_nome:
            condicoes.append(Case.id.in_(case_ids_por_nome))

    contraria = (parte_contraria or "").strip()
    if len(contraria) >= 4:
        contraria_busca = _like_literal(contraria[:120])
        condicoes.append(
            Case.parte_contraria.ilike(f"%{contraria_busca}%", escape="\\")
        )

    if not condicoes:
        return []

    casos = (
        await db.execute(
            select(Case)
            .where(Case.deleted_at.is_(None), or_(*condicoes))
            .order_by(Case.updated_at.desc())
            .limit(30)
        )
    ).scalars().all()

    candidatos: list[dict[str, Any]] = []
    houve_protegido = False
    for caso in casos:
        if not pode_ver_caso_resumido(user, caso):
            houve_protegido = True
            continue

        score = 0
        motivos: list[str] = []
        if cliente_id and caso.client_id == cliente_id:
            score += 45
            motivos.append("mesmo cliente")

        sim_contraria = _similaridade(parte_contraria, caso.parte_contraria)
        if sim_contraria:
            score += sim_contraria
            motivos.append("parte contrária semelhante")

        if caso.id in case_ids_por_nome:
            score += 40
            motivos.append("mesma parte/cliente no caso")
        elif cliente_nome and _texto_norm(cliente_nome) in _texto_norm(caso.titulo):
            score += 20
            motivos.append("cliente aparece no título do caso")

        if assunto:
            tokens_assunto = {
                t for t in _texto_norm(assunto).split() if len(t) >= 5
            }
            texto_caso = _texto_norm(
                " ".join(
                    [
                        caso.titulo or "",
                        caso.descricao_fatos or "",
                        caso.parte_contraria or "",
                    ]
                )
            )
            if tokens_assunto and any(t in texto_caso for t in tokens_assunto):
                score += 10
                motivos.append("assunto compatível")

        eh_pre = (
            getattr(caso.fase, "value", str(caso.fase)) == "pre_processual"
            or not bool(caso.has_judicial_process)
        )
        if tem_cnj and eh_pre:
            score += 15
            motivos.append("caso pré-processual pode ter sido ajuizado")

        if score >= 75:
            candidatos.append(
                {
                    "case_id": caso.id,
                    "numero_interno": caso.numero_interno,
                    "titulo": caso.titulo,
                    "status": getattr(caso.status, "value", str(caso.status)),
                    "fase": getattr(caso.fase, "value", str(caso.fase)),
                    "has_judicial_process": bool(caso.has_judicial_process),
                    "protegido": False,
                    "score": min(score, 99),
                    "motivos": motivos,
                    "pode_converter_pre_processual": bool(tem_cnj and eh_pre),
                }
            )

    candidatos.sort(key=lambda x: (-int(x["score"]), str(x["numero_interno"] or "")))
    candidatos = candidatos[:5]
    if houve_protegido and not candidatos:
        candidatos.append(
            {
                "case_id": None,
                "numero_interno": None,
                "titulo": "Possível correspondência em carteira protegida",
                "status": None,
                "fase": None,
                "has_judicial_process": None,
                "protegido": True,
                "score": 75,
                "motivos": ["correspondência protegida exige revisão da gestão"],
                "pode_converter_pre_processual": False,
            }
        )
    return candidatos


async def reconciliar_entrada(
    db: AsyncSession | None,
    user: Any,
    *,
    texto: str | None,
    cliente_id: str | None,
    cliente_nome: str | None,
    parte_contraria: str | None,
    assunto: str | None,
) -> dict[str, Any]:
    """Classifica a entrada sem criar nem alterar registros."""
    cnjs = extrair_cnjs(texto)
    principal = cnjs[0] if len(cnjs) == 1 else None

    base = {
        "status": "informacoes_insuficientes",
        "cnjs_detectados": cnjs,
        "numero_cnj_principal": principal,
        "correspondencias": [],
        "bloquear_criacao": False,
        "requer_confirmacao_humana": True,
        "acao_sugerida": "revisar_dados",
        "mensagem": "Informe ou confirme o número CNJ para uma reconciliação conclusiva.",
    }
    if db is None:
        return base

    correspondencias_exatas: list[dict[str, Any]] = []
    for cnj in cnjs:
        correspondencias_exatas.extend(await buscar_casos_por_cnj(db, user, cnj))
    if correspondencias_exatas:
        return {
            **base,
            "status": "ja_cadastrado",
            "correspondencias": correspondencias_exatas,
            "bloquear_criacao": True,
            "acao_sugerida": "abrir_caso_existente",
            "mensagem": "O CNJ informado já está vinculado a um caso do EJC.",
        }

    candidatos = await _candidatos_por_partes(
        db,
        user,
        cliente_id=cliente_id,
        cliente_nome=cliente_nome,
        parte_contraria=parte_contraria,
        assunto=assunto,
        tem_cnj=bool(cnjs),
    )
    if candidatos:
        conversivel = any(
            bool(c.get("pode_converter_pre_processual")) for c in candidatos
        )
        return {
            **base,
            "status": "provavel_correspondencia",
            "correspondencias": candidatos,
            "bloquear_criacao": False,
            "acao_sugerida": (
                "revisar_e_vincular_pre_processual"
                if conversivel
                else "revisar_correspondencia"
            ),
            "mensagem": (
                "Há caso existente com forte correspondência. Revise antes de criar "
                "um novo registro."
            ),
        }

    if cnjs:
        return {
            **base,
            "status": "novo_processo",
            "acao_sugerida": "criar_novo_processo",
            "mensagem": "Nenhum caso correspondente foi localizado para o CNJ informado.",
        }
    return base
