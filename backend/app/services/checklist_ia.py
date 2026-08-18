"""checklist_ia.py — geração de checklist por ÁREA + LEGISLAÇÃO (RAG + IA, HITL).

Serviço único reutilizável:
  - endpoint manual: routers/checklists.py POST /caso/{id}/gerar-ia
  - gatilho automático: routers/conversao_caso.py (ao judicializar, gatilho=pre_processo)

LGPD: sanitiza PII antes do modelo. HITL/OAB: grava itens como RASCUNHO (pendentes,
para revisão humana) e NUNCA cria prazos. Fail-safe quando usado em background.
"""
from __future__ import annotations
import json
import re
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checklist import CaseChecklist, CaseChecklistItem, ChecklistItemCategoria
from app.services import ai_gateway
from app.services.sanitizer import sanitizar_pii

_CATS_VALIDAS = {c.value for c in ChecklistItemCategoria}

_SYS_CHECKLIST = (
    "Você é assistente jurídico de um escritório de advocacia brasileiro. Gere um CHECKLIST "
    "de providências para um caso, ancorado na ÁREA e na LEGISLAÇÃO pertinente do CONTEXTO. "
    "Foque em: documentos obrigatórios, requisitos da peça/rito, diligências, pressupostos "
    "processuais e prazos a observar. Use o CONTEXTO (códigos/súmulas) quando útil, mas NUNCA "
    "invente número de lei/súmula; se não tiver certeza, descreva de forma geral. NÃO inclua "
    "dados pessoais. Responda SOMENTE em JSON, sem texto fora dele: "
    '{"itens":[{"texto":"...","dica":"...","categoria":"documentos|diligencias|prazos|audiencia|financeiro|comunicacao|outros","obrigatorio":true}]}'
)


def _parse_itens(texto: str) -> list:
    """Extrai a lista 'itens' do JSON da IA, tolerante a cercas/ruído."""
    if not texto:
        return []
    t = re.sub(r"^```(?:json)?", "", texto.strip()).strip()
    t = re.sub(r"```$", "", t).strip()
    data = None
    try:
        data = json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                return []
    if data is None:
        return []
    itens = data.get("itens") if isinstance(data, dict) else data
    return itens if isinstance(itens, list) else []


async def gerar_checklist_ia(db: AsyncSession, case_id: str, gatilho: str = "geral",
                             user_id: str | None = None) -> dict | None:
    """Gera e persiste um CaseChecklist (rascunho) por legislação. Retorna dict com
    {id, ck, itens, total_itens, modelo} ou None se caso inexistente / IA sem itens.

    Bloco 5 (continuação): escopa o RAG ao client_id do próprio caso. Não
    reverifica ownership aqui — os 3 chamadores (endpoint direto + 2 background
    tasks) já garantem, antes de chegar aqui, que o case_id é legítimo para
    quem disparou a ação."""
    caso = (await db.execute(text("""
        SELECT id, area, fase, tese_principal, client_id
        FROM cases WHERE id = :cid AND deleted_at IS NULL
    """), {"cid": case_id})).mappings().first()
    if not caso:
        return None

    area = caso["area"] or "geral"
    fase = caso["fase"] or ""

    from app.services.ai_service import buscar_contexto_rag
    consulta = f"{area} {fase} requisitos petição documentos obrigatórios diligências pressupostos prazos"
    ctx = await buscar_contexto_rag(
        db, consulta, limite=6, scope_client_id=caso["client_id"],
        scope_case_id=case_id,
    )
    ctx_txt = "\n".join("- " + (str(c.get("conteudo") or "")[:300]) for c in (ctx or []))

    limpo, _ = sanitizar_pii(f"Área: {area}. Fase: {fase}. Gatilho: {gatilho}. "
                             f"Tese: {caso['tese_principal'] or ''}")
    user = (f"{limpo}\n\nCONTEXTO LEGAL (base do escritório):\n{ctx_txt or '(sem contexto específico)'}\n\n"
            f"Gere de 6 a 14 itens objetivos para o gatilho '{gatilho}'.")

    resp = await ai_gateway.chat(
        messages=[{"role": "system", "content": _SYS_CHECKLIST}, {"role": "user", "content": user}],
        task_type="resumo", temperature=0.3, max_tokens=2000,
    )
    itens_ia = _parse_itens(resp.texto)
    if not itens_ia:
        return None

    nome = (f"Checklist IA — {area}" + (f" · {gatilho}" if gatilho and gatilho != "geral" else ""))[:200]
    ck = CaseChecklist(id=str(uuid4()), case_id=case_id, template_id=None,
                       nome=nome, total_itens=0, created_by=user_id)
    db.add(ck)
    await db.flush()

    criados = []
    for idx, it in enumerate(itens_ia[:20]):
        texto_it = str(it.get("texto") or "").strip()[:500]
        if not texto_it:
            continue
        cat_raw = str(it.get("categoria", "outros")).lower().strip()
        cat = cat_raw if cat_raw in _CATS_VALIDAS else "outros"
        ci = CaseChecklistItem(
            id=str(uuid4()), case_checklist_id=ck.id, texto=texto_it,
            dica=(str(it.get("dica") or "").strip()[:1000] or None),
            categoria=ChecklistItemCategoria(cat),
            obrigatorio=bool(it.get("obrigatorio", True)), ordem=idx + 1,
        )
        db.add(ci)
        criados.append(ci)

    if not criados:
        return None
    ck.total_itens = len(criados)
    await db.commit()
    return {"id": ck.id, "ck": ck, "itens": criados,
            "total_itens": len(criados), "modelo": f"{resp.provedor}/{resp.modelo}"}
