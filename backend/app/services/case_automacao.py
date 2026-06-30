"""Automação na criação do caso — roda em BackgroundTask (não depende de IA).
   1) Posiciona o caso na 1ª coluna do fluxo Kanban do seu tipo.
   2) Instancia automaticamente um checklist a partir de um template da área (se houver).
"""
import logging
from uuid import uuid4
from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.case import Case
from app.models.checklist import (
    ChecklistTemplate, ChecklistTemplateItem, CaseChecklist, CaseChecklistItem,
)

logger = logging.getLogger("ejc")

# tipo de caso -> legal_area das colunas kanban
_TIPO_AREA = {"judicial": "default", "extrajudicial": "extrajudicial", "consultoria": "consultoria"}


async def automacao_caso(case_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            case = await db.get(Case, case_id)
            if not case or case.deleted_at is not None:
                return
            area = getattr(case.area, "value", None) or str(case.area or "")
            tipo = getattr(case, "case_type", None) or "judicial"

            # 1) Kanban inicial — primeira coluna do fluxo do tipo
            if not getattr(case, "kanban_column", None):
                legal_area = _TIPO_AREA.get(tipo, "default")
                col = (await db.execute(text("""
                    SELECT name FROM kanban_columns
                    WHERE legal_area = :la AND is_active = true
                    ORDER BY position LIMIT 1
                """), {"la": legal_area})).scalar()
                if col:
                    await db.execute(text("""
                        UPDATE cases SET kanban_column = :col, kanban_position = 0, updated_at = now()
                        WHERE id = :id
                    """), {"col": col, "id": case_id})

            # 2) Checklist automático — template da área (default preferido)
            ja_tem = (await db.execute(text(
                "SELECT 1 FROM case_checklists WHERE case_id = :id LIMIT 1"
            ), {"id": case_id})).scalar()
            if not ja_tem and area:
                tpl = (await db.execute(
                    select(ChecklistTemplate)
                    .where(
                        ChecklistTemplate.deleted_at.is_(None),
                        ChecklistTemplate.area_juridica.ilike(f"%{area}%"),
                    )
                    .order_by(ChecklistTemplate.is_default.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if tpl:
                    itens = (await db.execute(
                        select(ChecklistTemplateItem)
                        .where(ChecklistTemplateItem.template_id == tpl.id)
                        .order_by(ChecklistTemplateItem.ordem)
                    )).scalars().all()
                    ck = CaseChecklist(
                        id=str(uuid4()), case_id=case_id, template_id=tpl.id,
                        nome=tpl.nome, total_itens=len(itens),
                        created_by=case.advogado_responsavel_id,
                    )
                    db.add(ck)
                    await db.flush()
                    for it in itens:
                        db.add(CaseChecklistItem(
                            id=str(uuid4()), case_checklist_id=ck.id,
                            template_item_id=it.id, texto=it.texto, dica=it.dica,
                            categoria=it.categoria, obrigatorio=it.obrigatorio, ordem=it.ordem,
                        ))

            # área principal em caso_areas (multi-área)
            await db.execute(text("""
                INSERT INTO caso_areas (case_id, area, principal)
                VALUES (:cid, :a, true)
                ON CONFLICT (case_id, area) DO NOTHING
            """), {"cid": case_id, "a": area})

            # 3) Processo canonico — mantem `processes` em sincronia com o caso.
            #    processes e a fonte UNICA (1 Caso : N Processos); cases.numero_processo
            #    permanece como cache legado ate o repoint completo dos leitores.
            numproc = (getattr(case, "numero_processo", None) or "").strip()
            if numproc:
                ja_proc = (await db.execute(text(
                    "SELECT 1 FROM processes WHERE case_id = :cid AND deleted_at IS NULL LIMIT 1"
                ), {"cid": case_id})).scalar()
                if not ja_proc:
                    await db.execute(text(
                        "INSERT INTO processes (id, case_id, numero_cnj, instancia, tribunal, "
                        "comarca, vara, valor_causa, status, created_at, updated_at) "
                        "VALUES (:id, :cid, :ncnj, '1', :trib, :com, :vara, :vc, 'ativo', now(), now())"
                    ), {"id": str(uuid4()), "cid": case_id, "ncnj": numproc[:30],
                        "trib": getattr(case, "tribunal", None),
                        "com": getattr(case, "comarca", None),
                        "vara": getattr(case, "vara", None),
                        "vc": getattr(case, "valor_causa", None)})

            await db.commit()
            logger.info(f"[automacao_caso] caso {case_id} automatizado (kanban + checklist)")
    except Exception as e:
        logger.warning(f"[automacao_caso] falha no caso {case_id}: {e}")
