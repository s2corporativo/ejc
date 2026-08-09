"""
event_subscribers.py — Subscribers do barramento de eventos (ativação da
arquitetura orientada a eventos do EJC).

Importado em main.py por efeito colateral: ao importar, os decorators @on
registram os handlers no event_bus. Cada subscriber é ISOLADO (o event_bus já
captura exceções e nunca derruba o request) e ADITIVO — não duplica fluxos
diretos já existentes (triagem, notificações de prazo, kanban, etc.).

Eventos hoje emitidos pelo sistema:
  caso.criado       (cases.criar)
  caso.atualizado   (cases.atualizar)
  caso.encerrado    (cases.encerrar_caso)
  movimento.criado  (cases.criar_movimento)
  documento.importado (cases.aplicar_extracao)
"""
from __future__ import annotations
import logging

from app.services.event_bus import on

logger = logging.getLogger("ejc.event_subscribers")

_TRADUZ_TIPOS = {"intimacao", "decisao", "peticao", "audiencia", "movimento"}
_TIPOS_PUBLICOS_CLIENTE = {"intimacao", "decisao", "audiencia", "movimento"}





# ── Leitura estratégica de documento → snapshot do caso ──────────────────────
# Chaves de `analise_estrategica.PROMPT_ANALISE` que interessam ao advogado,
# mapeadas para o payload documentado em models/case_intelligence.py. O que a
# IA não produziu simplesmente não entra no payload (lacuna admitida — nunca
# se inventa chave vazia para "parecer completo").

def _lista(valor) -> list:
    """Normaliza para lista de itens não vazios (a IA às vezes devolve str)."""
    if valor is None or valor == "":
        return []
    if isinstance(valor, list):
        return [v for v in valor if v not in (None, "", {}, [])]
    return [valor]


def _payload_leitura_documento(resultado: dict, doc_id: str) -> dict:
    """Traduz o parecer da IA para o payload de CaseIntelligenceSnapshot.

    Só chaves com conteúdo real entram. `fontes` registra a procedência
    (leitura do documento + RAG interno) para o advogado saber de onde a
    análise saiu antes de aprovar no HITL.
    """
    estrategia = resultado.get("estrategia")
    jurimetria = resultado.get("jurimetria") if isinstance(
        resultado.get("jurimetria"), dict) else {}
    brechas = resultado.get("brechas_preliminares") if isinstance(
        resultado.get("brechas_preliminares"), dict) else {}

    riscos = {
        "itens": _lista(resultado.get("riscos")),
        "pontos_fracos": _lista(resultado.get("pontos_fracos")),
        "chance_exito": jurimetria.get("chance_sucesso_percent"),
    }
    # Brecha só entra se tiver indício — dict com tudo null não é achado.
    brechas_uteis = {k: v for k, v in brechas.items()
                     if k != "observacao" and v not in (None, "", [], {})}

    # Contrato do payload (models/case_intelligence.py): teses.principal e
    # teses.secundarias são TÍTULOS (str). O objeto completo da tese
    # (fundamento legal, jurisprudência conferida, força) fica em
    # teses.detalhe — dentro da mesma chave documentada, sem perder informação
    # nem inventar chave de topo.
    teses_itens = _lista(resultado.get("teses_campeas"))
    titulos = [
        (t.get("titulo") if isinstance(t, dict) else t) for t in teses_itens
    ]
    titulos = [t for t in titulos if t]
    teses = {
        "principal": titulos[0] if titulos else None,
        "secundarias": titulos[1:],
        "detalhe": [t for t in teses_itens if isinstance(t, dict)],
    } if titulos else None

    payload = {
        "documento_id": doc_id,
        "fatos": resultado.get("sumario_fatos"),
        "teses": teses,
        "riscos": {k: v for k, v in riscos.items() if v not in (None, [], "")},
        "provas": _lista(resultado.get("provas_necessarias")),
        "pontos_fortes": _lista(resultado.get("pontos_fortes")),
        "estrategia": estrategia if isinstance(estrategia, dict) else None,
        "brechas": brechas_uteis or None,
        "proximos_passos": _lista(resultado.get("proximos_passos")),
        "alertas": _lista(resultado.get("alertas")),
        "fontes": ["leitura_documento"] + (
            ["rag_interno"] if resultado.get("_fontes_rag") else []
        ),
    }
    if resultado.get("_verificacao_citacoes") is not None:
        payload["verificacao_citacoes"] = resultado["_verificacao_citacoes"]
    return {k: v for k, v in payload.items() if v not in (None, [], {}, "")}


async def _gravar_snapshot_documento(
    db, *, case_id: str, doc_id: str, resultado, ai_log_id: str,
) -> None:
    """Grava o parecer da leitura do documento como snapshot do caso.

    Fail-safe por dois motivos somados: `gravar_snapshot_seguro` já absorve a
    falha de gravação, e este chamador roda em BackgroundTask — quebrar aqui
    não pode afetar o upload, que já respondeu 200 ao advogado.

    Snapshot nasce `congelado=False` (HITL: aprovar é ato humano) e
    `criado_por=None` (origem automática), como manda o service.
    """
    if not isinstance(resultado, dict) or resultado.get("erro"):
        return
    payload = _payload_leitura_documento(resultado, doc_id)
    # Sem nenhum conteúdo jurídico além do id do documento, não há parecer a
    # versionar — evita poluir o histórico do caso com snapshot vazio.
    if len(payload) <= 2:
        return
    try:
        from app.services import case_intelligence_service as cis
        await cis.gravar_snapshot_seguro(
            db,
            case_id=case_id,
            origem="documento",
            payload=cis.compactar_payload(payload),
            resumo=(resultado.get("sumario_fatos") or
                    "Leitura estratégica de documento anexado")[:500],
            ai_log_ids=[ai_log_id],
            criado_por=None,
        )
    except Exception as exc:  # pragma: no cover - defesa dupla
        logger.warning("Snapshot da leitura documental não gravado: %s", exc)


def _patch_documents_background_analysis() -> None:
    """Substitui o hook legado de análise documental por versão sem corte."""
    try:
        from app.routers import documents as documents_router
    except Exception as exc:  # pragma: no cover
        logger.warning("Patch do hook documental indisponível: %s", exc)
        return

    async def _analisar_doc_bg_sem_corte(case_id: str, ocr_text: str, doc_id: str, user_id: str) -> None:
        try:
            from app.services.analise_estrategica import analisar_caso
            from app.core.database import AsyncSessionLocal
            from app.models.ai_log import (
                AILog, AITipoUso, AIStatusHITL, classificar_risco_ia,
            )
            from sqlalchemy import text as _sql
            from uuid import uuid4 as _uuid4
            import json as _json

            async with AsyncSessionLocal() as db:
                row = await db.execute(
                    _sql("SELECT titulo, area, numero_processo, client_id FROM cases WHERE id = :id"),
                    {"id": case_id},
                )
                caso = row.fetchone()

                resultado = await analisar_caso(
                    titulo=(caso.titulo if caso else "") or "",
                    area=(caso.area if caso else "") or "",
                    numero_processo=(caso.numero_processo if caso else "") or "",
                    texto_documento=ocr_text,
                    scope_client_id=(caso.client_id if caso else None),
                    case_id=case_id,
                    db=db,
                )

                fontes = None
                if isinstance(resultado, dict) and resultado.get("_fontes_rag"):
                    fontes = _json.dumps(resultado["_fontes_rag"], ensure_ascii=False)[:2000]
                log_id = str(_uuid4())
                log = AILog(
                    id=log_id,
                    user_id=user_id,
                    case_id=case_id,
                    tipo_uso=AITipoUso.analise_caso,
                    modelo="auto-analise-doc",
                    prompt_sanitizado=f"[auto] analise estrategica do documento {doc_id}",
                    resposta=_json.dumps(resultado, ensure_ascii=False)[:8000],
                    fontes_rag=fontes,
                    # O hook original (routers/documents.py) classifica o risco;
                    # esta cópia patcheada não classificava — e é ELA que roda
                    # em produção, então todo AILog de análise documental
                    # nascia sem risco_ia. Restaurado para não divergir do irmão.
                    risco_ia=classificar_risco_ia("analise_juridica"),
                    status_hitl=AIStatusHITL.gerado,
                )
                db.add(log)
                await db.commit()

                # A leitura estratégica do documento vira SNAPSHOT DO CASO.
                # Antes, o parecer existia só dentro de AILog.resposta (cortado
                # em 8.000 caracteres, sem nenhuma tela que o lesse): a IA lia
                # o documento como advogado e ninguém via o resultado. Agora
                # segue o mesmo caminho de triagem/intake/motor_peca e aparece
                # em GET /cases/{case_id}/inteligencia.
                await _gravar_snapshot_documento(
                    db, case_id=case_id, doc_id=doc_id,
                    resultado=resultado, ai_log_id=log_id,
                )
        except Exception as exc:
            logger.warning("Hook analise doc sem corte falhou: %s", exc)

    documents_router._analisar_doc_bg = _analisar_doc_bg_sem_corte
    logger.info("Hook de análise documental ajustado para OCR completo")


def _install_ai_core_hardening() -> None:
    """Ativa gates críticos; falha no patch impede boot inseguro."""
    try:
        from app.services.ai_core_hardening_patch import instalar
        instalar()
    except Exception as exc:
        logger.critical(
            "Hardening crítico do núcleo de IA/RAG não pôde ser instalado: %s",
            exc,
            exc_info=True,
        )
        raise RuntimeError("Hardening crítico do núcleo de IA/RAG indisponível") from exc


def _install_datajud_cognitive_feed() -> None:
    """Ativa DataJud → RAG nativo sem tornar o conector requisito de boot."""
    try:
        from app.services.datajud_cognitive_patch import instalar
        instalar()
    except Exception as exc:
        logger.error("Feed cognitivo DataJud indisponível: %s", exc, exc_info=True)


# ── Onda 3 §4.1: os routers de precedentes, advogado_estilo e rag_governance
# NÃO são mais anexados aqui por side effect — são registrados explicitamente
# em app/main.py. Este módulo mantém apenas subscribers de evento e patches de
# COMPORTAMENTO (não de rota).
# ── Onda 3 §4.1: os routers de precedentes, advogado_estilo e rag_governance
# NÃO são mais anexados aqui por side effect — são registrados explicitamente
# em app/main.py. Este módulo mantém apenas subscribers de evento e patches de
# COMPORTAMENTO (não de rota).
_patch_documents_background_analysis()
_install_ai_core_hardening()
_install_datajud_cognitive_feed()


@on("movimento.criado")
async def _traduzir_andamento(db, entidade_id, payload):
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TRADUZ_TIPOS:
        return
    from app.services.movimento_ia import traduzir_movimento
    await traduzir_movimento(db, entidade_id)


@on("movimento.criado")
async def _notificar_cliente_movimento(db, entidade_id, payload):
    """Avisa o cliente com mensagem genérica, sem teor ou estratégia."""
    tipo = (payload or {}).get("tipo", "")
    if tipo not in _TIPOS_PUBLICOS_CLIENTE:
        return

    from sqlalchemy import select
    from app.models.case import Case
    from app.models.user import User, UserRole
    from app.services.notification_service import criar_notificacao_interna

    caso = await db.get(Case, entidade_id)
    if caso is None or not caso.client_id:
        return

    res = await db.execute(
        select(User).where(
            User.client_id == caso.client_id,
            User.role == UserRole.cliente_externo,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    usuarios_cliente = res.scalars().all()
    if not usuarios_cliente:
        return

    ref = f" (caso {caso.numero_interno})" if caso.numero_interno else ""
    for user in usuarios_cliente:
        await criar_notificacao_interna(
            db,
            user_id=user.id,
            titulo="Atualização no seu processo",
            mensagem=f"Há uma nova atualização no seu processo{ref}.",
            tipo="processo",
        )


@on("caso.encerrado")
async def _log_encerramento(db, entidade_id, payload):
    logger.info(
        f"[evento] caso.encerrado {entidade_id} "
        f"resultado={(payload or {}).get('resultado')}"
    )


@on("documento.importado")
async def _log_importacao(db, entidade_id, payload):
    logger.info(
        f"[evento] documento.importado → caso {entidade_id} "
        f"(partes={(payload or {}).get('partes', 0)}, areas={(payload or {}).get('areas', 0)})"
    )
