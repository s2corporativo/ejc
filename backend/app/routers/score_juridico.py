# ── app/routers/score_juridico.py ────────────────────────────────────────────
from __future__ import annotations
import json
import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.ownership import verificar_acesso_caso
from app.models.user import User
from app.models.audit_log import criar_audit_log
from app.services import ai_gateway

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/score-juridico", tags=["Score Jurídico"])

_ADV = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}


def _req_adv(cu: User = Depends(get_current_user)) -> User:
    # Cálculo de score dispara IA + grava no caso: só equipe jurídica.
    if cu.role.value not in _ADV:
        raise HTTPException(status_code=403, detail="Acesso restrito à equipe jurídica")
    return cu

DIMS = {
    "pedido": 15, "causa_de_pedir": 15, "fundamentacao": 20, "provas": 20,
    "jurisprudencia": 15, "documentos_obrigatorios": 10, "conformidade_formal": 5,
}


@router.get("")
async def listar_scores(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    await verificar_acesso_caso(db, cu, case_id)  # IDOR (auditoria 2026-06-30)
    r = await db.execute(
        text("""
            SELECT id, tipo, pedido, causa_de_pedir, fundamentacao, provas,
                   jurisprudencia, documentos_obrigatorios, conformidade_formal,
                   total, detalhes, recomendacoes, versao, created_at
            FROM score_juridico WHERE case_id = :cid ORDER BY created_at DESC LIMIT 10
        """),
        {"cid": case_id},
    )
    return [dict(row) for row in r.mappings().all()]


@router.post("/calcular", status_code=201)
async def calcular_score(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_adv),
):
    await verificar_acesso_caso(db, cu, case_id)
    # Buscar dados do caso
    case_r = await db.execute(
        text("""
            SELECT c.titulo, c.area, c.status, c.valor_causa,
                   COUNT(DISTINCT d.id) AS docs,
                   COUNT(DISTINCT dl.id) AS prazos
            FROM cases c
            LEFT JOIN documents d ON d.case_id = c.id
            LEFT JOIN deadlines dl ON dl.case_id = c.id
            WHERE c.id = :cid GROUP BY c.id
        """),
        {"cid": case_id},
    )
    case_data = case_r.mappings().first()
    if not case_data:
        from fastapi import HTTPException
        raise HTTPException(404, "Caso não encontrado")

    # Chamar LLM — via AI Gateway (barreira única de PII/LGPD + logs HITL).
    try:
        system_prompt = (
            "Você é um avaliador jurídico do escritório. Avalie o caso e responda "
            "SOMENTE em JSON com as 7 dimensões e pontuações:\n"
            '{"pedido":<0-15>,"causa_de_pedir":<0-15>,"fundamentacao":<0-20>,'
            '"provas":<0-20>,"jurisprudencia":<0-15>,"documentos_obrigatorios":<0-10>,'
            '"conformidade_formal":<0-5>,"detalhes":{},"recomendacoes":[]}'
        )
        user_prompt = (
            f"Caso: {case_data['titulo']} | Área: {case_data['area']} | "
            f"Status: {case_data['status']} | Docs: {case_data['docs']} | "
            f"Prazos: {case_data['prazos']}"
        )
        resp = await ai_gateway.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            task_type="analise_juridica",
            temperature=0.15,
            max_tokens=1024,
        )
        match = re.search(r"\{.*\}", resp.texto, re.DOTALL)
        scores = json.loads(match.group()) if match else {}
    except Exception:
        # Fail-safe: nunca 500 e nunca inventa nota — mas registra para não
        # mascarar a falha (antes o except amplo escondia até import quebrado).
        logger.warning("Score jurídico por IA indisponível; usando fallback zerado", exc_info=True)
        scores = {k: 0 for k in DIMS}
        scores.update({"detalhes": {}, "recomendacoes": ["Score calculado manualmente"]})

    total = sum(scores.get(k, 0) for k in DIMS)

    ins = await db.execute(
        text("""
            INSERT INTO score_juridico
                (case_id, avaliador_id, tipo,
                 pedido, causa_de_pedir, fundamentacao, provas,
                 jurisprudencia, documentos_obrigatorios, conformidade_formal,
                 total, detalhes, recomendacoes)
            VALUES (:cid, :uid, 'ia', :ped, :causa, :fund, :prov,
                    :jur, :docs, :form, :total, :det, :rec)
            RETURNING id
        """),
        {
            "cid": case_id, "uid": cu.id,
            "ped": scores.get("pedido", 0), "causa": scores.get("causa_de_pedir", 0),
            "fund": scores.get("fundamentacao", 0), "prov": scores.get("provas", 0),
            "jur": scores.get("jurisprudencia", 0),
            "docs": scores.get("documentos_obrigatorios", 0),
            "form": scores.get("conformidade_formal", 0),
            "total": total,
            "det": json.dumps(scores.get("detalhes", {})),
            "rec": json.dumps(scores.get("recomendacoes", [])),
        },
    )
    row = ins.mappings().first()
    await criar_audit_log(
        db, cu.id, cu.role.value, "CREATE", "score_juridico", row["id"],
        dados_depois={"total": total, "tipo": "ia"},
    )
    await db.commit()
    return {**scores, "total": total, "id": row["id"],
            "aviso": "Resultado gerado por IA — revisão humana obrigatória"}
