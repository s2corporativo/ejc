# ── app/services/conflito_interesses.py ──────────────────────────────────────
# Verificação de conflito de interesses antes de abrir caso.
# OAB EOAB Lei 8.906/94 arts. 34-35; Código de Ética OAB arts. 15-18.
# Cruza parte contrária com clientes ativos e histórico de casos.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import logging
from typing import Optional
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger("ejc.conflito")


async def verificar_conflito(
    db: AsyncSession,
    parte_contraria_nome: Optional[str] = None,
    parte_contraria_doc: Optional[str] = None,
    user_id: Optional[str] = None,
    case_id: Optional[str] = None,
) -> dict:
    """
    Verifica conflito de interesses antes de abrir ou atualizar um caso.

    Retorna resultado: sem_conflito | possivel_conflito | conflito_identificado | verificacao_incompleta
    """
    if not parte_contraria_doc and not parte_contraria_nome:
        return {
            "resultado": "verificacao_incompleta",
            "matches": [],
            "recomendacao": (
                "Informe ao menos o nome ou CPF/CNPJ da parte contrária "
                "para a verificação de conflito de interesses."
            ),
            "base_legal": "EOAB Lei 8.906/94 arts. 34-35; Código de Ética OAB arts. 15-18",
        }

    matches: list[dict] = []

    # Núcleo de matching COMPARTILHADO com detectar_conflito (mesmas regras,
    # hash-aware): cliente por documento (texto puro + cpf_hash/cnpj_hash),
    # cliente por nome e parte contrária em casos. Aqui só formatamos o schema
    # próprio deste endpoint ({resultado, matches, recomendacao, ...}).
    from app.services.conflito_service import (
        _clientes_por_documentos,
        _clientes_por_nome,
        _casos_por_parte_contraria,
    )

    def _doc(c) -> Optional[str]:
        return c.documento_plain

    def _nome(c) -> str:
        return c.nome or c.razao_social or "N/D"

    # ── 1. Parte contrária é cliente ativo por documento? ─────────────────────
    if parte_contraria_doc:
        for c in await _clientes_por_documentos(db, [parte_contraria_doc]):
            matches.append({
                "tipo": "CLIENTE_ATIVO",
                "gravidade": "critico",
                "entidade": _nome(c),
                "documento": _doc(c),
                "detalhe": (
                    "A parte contrária consta como cliente do escritório. "
                    "Representação proibida — EOAB art. 34, XVII."
                ),
            })

    # ── 2. Parte contrária por nome nos clientes ──────────────────────────────
    if parte_contraria_nome and not matches:
        for c in await _clientes_por_nome(db, parte_contraria_nome):
            matches.append({
                "tipo": "POSSIVEL_CLIENTE",
                "gravidade": "alto",
                "entidade": _nome(c),
                "documento": _doc(c),
                "detalhe": (
                    f"Nome '{_nome(c)}' encontrado nos clientes. "
                    "Confirme se é a mesma pessoa antes de prosseguir."
                ),
            })

    # ── 3. Parte contrária aparece em casos ativos (pelo nome)? ──────────────
    if parte_contraria_nome:
        casos = await _casos_por_parte_contraria(
            db, parte_contraria_nome, somente_ativos=True, ignorar_case_id=case_id
        )
        if len(casos) > 1:
            matches.append({
                "tipo": "MULTIPLOS_CASOS_MESMA_PARTE",
                "gravidade": "baixo",
                "entidade": parte_contraria_nome,
                "detalhe": (
                    f"A mesma parte contrária aparece em {len(casos)} casos ativos. "
                    "Verificar possível vinculação de interesses."
                ),
            })

    # ── 4. Classificar resultado ──────────────────────────────────────────────
    criticos = [m for m in matches if m["gravidade"] == "critico"]
    altos    = [m for m in matches if m["gravidade"] == "alto"]
    medios   = [m for m in matches if m["gravidade"] == "medio"]

    if criticos:
        resultado    = "conflito_identificado"
        recomendacao = (
            "CONFLITO IDENTIFICADO. A parte contrária consta como cliente do escritório. "
            "Representação proibida por lei (EOAB art. 34, XVII). "
            "Não abrir o caso sem aprovação expressa da sócio-coordenação."
        )
    elif altos or medios:
        resultado    = "possivel_conflito"
        recomendacao = (
            "POSSÍVEL CONFLITO. A parte contrária tem correspondência nos registros. "
            "Verificar manualmente antes de prosseguir. "
            "Obter aprovação do sócio coordenador — Código de Ética art. 15."
        )
    else:
        resultado    = "sem_conflito"
        recomendacao = (
            "Sem conflitos identificados nos registros do escritório. "
            "Verificação realizada por nome e CPF/CNPJ. "
            "Manter vigilância durante o caso conforme OAB."
        )

    # ── 5. Registrar no audit_log ─────────────────────────────────────────────
    try:
        await db.execute(text("""
            INSERT INTO audit_logs (id, user_id, acao, entidade, registro_id, detalhes, created_at)
            VALUES (:id, :uid, 'CONFLICT_CHECK', 'cases', :cid, :det, NOW())
        """), {
            "id":  str(uuid4()),
            "uid": user_id,
            "cid": case_id,
            "det": (
                f"Verificação conflito: {parte_contraria_nome or 'N/D'} / "
                f"{parte_contraria_doc or 'N/D'} → {resultado}"
            ),
        })
        await db.commit()
    except Exception:
        # NÃO engolir em silêncio: a trilha de auditoria da verificação de
        # conflito é exigência de compliance (OAB). Registra a falha e desfaz
        # a transação suja para não deixar a sessão inutilizável — a checagem
        # em si (resultado abaixo) continua válida e é devolvida.
        logger.warning(
            "Falha ao gravar audit_log da verificação de conflito "
            "(case_id=%s): a trilha desta verificação não foi persistida.",
            case_id, exc_info=True,
        )
        await db.rollback()

    return {
        "resultado":             resultado,
        "parte_contraria_nome":  parte_contraria_nome,
        "parte_contraria_doc":   parte_contraria_doc,
        "total_matches":         len(matches),
        "matches":               matches,
        "recomendacao":          recomendacao,
        "base_legal":            "EOAB Lei 8.906/94 arts. 34-35; Código de Ética OAB arts. 15-18",
        "_aviso": (
            "Verificação automática baseada nos registros do EJC. "
            "Não substitui a análise do advogado responsável."
        ),
    }
