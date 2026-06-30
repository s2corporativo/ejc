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

    # ── 1. Parte contrária é cliente ativo por documento? ─────────────────────
    if parte_contraria_doc:
        doc_clean = parte_contraria_doc.replace(".", "").replace("-", "").replace("/", "")
        r = await db.execute(text("""
            SELECT id, COALESCE(nome, razao_social, 'N/D') AS nome_cliente,
                   COALESCE(cpf, cnpj) AS doc
            FROM clients
            WHERE (
                REPLACE(REPLACE(REPLACE(cpf, '.',''), '-',''), '/','') = :doc
                OR REPLACE(REPLACE(REPLACE(cnpj, '.',''), '-',''), '/','') = :doc
            )
            AND deleted_at IS NULL
        """), {"doc": doc_clean})
        for row in r.fetchall():
            matches.append({
                "tipo": "CLIENTE_ATIVO",
                "gravidade": "critico",
                "entidade": row.nome_cliente,
                "documento": row.doc,
                "detalhe": (
                    "A parte contrária consta como cliente do escritório. "
                    "Representação proibida — EOAB art. 34, XVII."
                ),
            })

    # ── 2. Parte contrária por nome nos clientes ──────────────────────────────
    if parte_contraria_nome and not matches:
        r = await db.execute(text("""
            SELECT id, COALESCE(nome, razao_social, 'N/D') AS nome_cliente,
                   COALESCE(cpf, cnpj) AS doc
            FROM clients
            WHERE (LOWER(nome) ILIKE :nm OR LOWER(razao_social) ILIKE :nm)
              AND deleted_at IS NULL
        """), {"nm": f"%{parte_contraria_nome.lower()}%"})
        for row in r.fetchall():
            matches.append({
                "tipo": "POSSIVEL_CLIENTE",
                "gravidade": "alto",
                "entidade": row.nome_cliente,
                "documento": row.doc,
                "detalhe": (
                    f"Nome '{row.nome_cliente}' encontrado nos clientes. "
                    "Confirme se é a mesma pessoa antes de prosseguir."
                ),
            })

    # ── 3. Parte contrária aparece em casos ativos (pelo nome)? ──────────────
    if parte_contraria_nome:
        r = await db.execute(text("""
            SELECT numero_interno, titulo, area, status
            FROM cases
            WHERE LOWER(parte_contraria) ILIKE :nm
              AND status NOT IN ('encerrado', 'arquivado')
              AND deleted_at IS NULL
              AND (:cid IS NULL OR id != :cid)
        """), {"nm": f"%{parte_contraria_nome.lower()}%", "cid": case_id})
        rows = r.fetchall()
        if len(rows) > 1:
            matches.append({
                "tipo": "MULTIPLOS_CASOS_MESMA_PARTE",
                "gravidade": "baixo",
                "entidade": parte_contraria_nome,
                "detalhe": (
                    f"A mesma parte contrária aparece em {len(rows)} casos ativos. "
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
        pass

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
