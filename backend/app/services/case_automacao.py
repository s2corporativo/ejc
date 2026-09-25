"""Automação na criação do caso — roda em BackgroundTask (não depende de IA).
   1) Posiciona o caso na 1ª coluna do fluxo Kanban do seu tipo.
   2) Instancia automaticamente um checklist a partir de um template da área (se houver).
"""
import logging
from uuid import uuid4
from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.case import Case
from app.models.client import Client
from app.models.user import User
from app.models.checklist import (
    ChecklistTemplate, ChecklistTemplateItem, CaseChecklist, CaseChecklistItem,
)
from app.services.case_integrity_service import sincronizar_processo_principal_do_caso
from app.services.processo_service import ProcessConflict

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
                    try:
                        await sincronizar_processo_principal_do_caso(
                            db,
                            case_id=case_id,
                            numero_processo=numproc,
                            tribunal=getattr(case, "tribunal", None),
                            comarca=getattr(case, "comarca", None),
                            vara=getattr(case, "vara", None),
                            valor_causa=getattr(case, "valor_causa", None),
                            tipo="judicial",
                        )
                    except ProcessConflict as exc:
                        # Background é fail-soft: um conflito de CNJ não pode
                        # desfazer Kanban/checklist. A inconsistência ficará
                        # visível no Radar para reconciliação humana.
                        logger.warning(
                            "[automacao_caso] sincronização processual recusada "
                            "(tipo=%s)",
                            type(exc).__name__,
                        )

            await db.commit()
            logger.info(f"[automacao_caso] caso {case_id} automatizado (kanban + checklist)")
    except Exception as e:
        logger.warning(f"[automacao_caso] falha no caso {case_id}: {e}")


async def gerar_documentos_iniciais_auto(case_id: str, user_id: str | None = None) -> None:
    """Gatilho AUTOMÁTICO do kit documental inicial na ABERTURA do caso.

    Mesmo molde de ``automacao_caso``: roda em BackgroundTask, abre a própria
    ``AsyncSessionLocal`` e é FAIL-SAFE (try/except que NUNCA derruba a criação
    do caso). REUSA a idempotência pronta de ``geracao_documental.gerar_kit_inicial``
    — se os rascunhos do kit já existem para o caso, nada é duplicado
    (ja_existia=True); regeneração só é explícita (forcar_novo).

    Política central: procuração com PODERES GERAIS
    (``tipo_poderes="ad_judicia_et_extra"``), o modelo oficial do escritório.
    Tudo nasce RASCUNHO/ai_generated=True → gate HITL (revisão humana
    obrigatória). NÃO cria o registro formal ``Procuracao``: a minuta é apenas
    LegalDoc; a outorga formal continua exclusiva de routers/procuracoes.py.
    O contrato sai preenchido quando há proposta de honorários aprovada; sem
    proposta, com placeholders de revisão (comportamento atual preservado).
    """
    try:
        # Import tardio: evita custo/ciclo no boot do router e mantém o gatilho
        # tão degradável quanto o restante das integrações opt-in.
        from app.services import geracao_documental

        async with AsyncSessionLocal() as db:
            case = await db.get(Case, case_id)
            if not case or case.deleted_at is not None:
                return
            cli = await db.get(Client, case.client_id) if case.client_id else None
            if not cli:
                logger.warning(
                    f"[gerar_documentos_iniciais_auto] caso {case_id} sem cliente — kit ignorado"
                )
                return
            # "Autor" do kit (created_by + papel na auditoria): quem criou o caso
            # ou, na falta, o advogado responsável. Precisa ser um User real.
            cu = await db.get(User, user_id) if user_id else None
            if cu is None and case.advogado_responsavel_id:
                cu = await db.get(User, case.advogado_responsavel_id)
            if cu is None:
                logger.warning(
                    f"[gerar_documentos_iniciais_auto] caso {case_id} sem usuario para autoria — kit ignorado"
                )
                return

            res = await geracao_documental.gerar_kit_inicial(
                db, case, cli, cu, tipo_poderes="ad_judicia_et_extra",
            )
            logger.info(
                f"[gerar_documentos_iniciais_auto] caso {case_id}: "
                f"kit {'reaproveitado' if res.get('ja_existia') else 'gerado'} "
                f"(ja_existia={res.get('ja_existia')})"
            )
    except Exception as e:
        logger.warning(f"[gerar_documentos_iniciais_auto] falha no caso {case_id}: {e}")
