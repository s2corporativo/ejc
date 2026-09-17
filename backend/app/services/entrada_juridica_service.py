"""Dossiê Jurídico canônico da Entrada Única.

A Entrada Única mantém a interface simples e ORQUESTRA capacidades já existentes:
caso/partes/documentos -> análise estratégica grounded -> teses do banco ->
honorários determinísticos -> crítica adversarial opcional -> snapshot HITL.

Nenhuma conclusão é promovida automaticamente para o caso oficial. O resultado
nasce como RASCUNHO, exige aprovação humana do snapshot e só então deve seguir
para o Motor de Peça, que preserva seus próprios gates de checklist/prazo.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.ownership import is_gestao, verificar_acesso_caso
from app.models.audit_log import criar_audit_log
from app.models.case import CaseMovimento
from app.models.case_parte import CaseParte
from app.models.client import Client
from app.models.document import Document
from app.models.raio_x import RaioXAnalise
from app.services import case_intelligence_service as cis
from app.services import fee_proposal_service
from app.services.analise_estrategica import analisar_caso
from app.services.document_access_policy import confidencialidades_visiveis
from app.services.motor_peca_service import texto_base_do_caso

AVISO_DOSSIE = (
    "Dossiê jurídico gerado para apoio interno. É RASCUNHO e exige revisão e "
    "aprovação humana do advogado responsável antes de produzir efeitos."
)


def _enum_value(value: Any) -> str | None:
    raw = getattr(value, "value", value)
    return str(raw) if raw not in (None, "") else None


def _texto(value: Any, limite: int = 2_000) -> str | None:
    if value in (None, "", [], {}):
        return None
    return str(value).strip()[:limite] or None


def _lista(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalizar(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _tokens(value: Any) -> set[str]:
    stop = {
        "para", "com", "sem", "uma", "que", "dos", "das", "por", "em", "de",
        "do", "da", "ao", "aos", "as", "os", "no", "na", "nos", "nas", "ser",
        "foi", "sao", "seu", "sua", "como", "mais", "caso", "direito",
    }
    return {t for t in _normalizar(value).split() if len(t) >= 4 and t not in stop}


def identificar_conteudo(texto: str | None, documentos: list[dict] | None = None) -> dict:
    """Classificação preliminar determinística, auditável e sem efeito jurídico."""
    bruto = " ".join(
        [texto or ""]
        + [f"{d.get('titulo', '')} {d.get('tipo', '')}" for d in (documentos or [])]
    ).lower()
    tipos: list[str] = []

    if re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", bruto) or any(
        k in bruto for k in ("autos", "processo nº", "processo n°", "processo judicial")
    ):
        tipos.append("caso_existente")
    else:
        tipos.append("caso_novo")

    marcadores = (
        ("intimacao", ("intimação", "intimacao", "intimado", "intimada")),
        ("decisao", ("decisão", "decisao", "sentença", "sentenca", "acórdão", "acordao")),
        ("contrato", ("contrato", "instrumento particular", "cláusula", "clausula")),
        ("pedido_de_peca", ("redija", "elabore a peça", "elabore uma petição", "gerar peça", "petição inicial")),
        ("pesquisa", ("pesquise", "pesquisa jurídica", "jurisprudência", "jurisprudencia", "precedente")),
        ("duvida_juridica", ("dúvida", "duvida", "é possível", "e possivel", "posso ", "cabe ")),
    )
    for tipo, palavras in marcadores:
        if any(p in bruto for p in palavras):
            tipos.append(tipo)

    if documentos:
        tipos.append("documento")

    return {
        "tipos": list(dict.fromkeys(tipos)),
        "origem": "classificacao_deterministica_preliminar",
        "requer_confirmacao_humana": True,
    }


def _correlacionar_fato_prova_tese(
    provas: list[dict], teses: list[dict],
) -> list[dict[str, Any]]:
    """Matriz indicativa: prova vem da análise e tese é só correlação lexical.

    A relação tese<->fato NÃO é tratada como conclusão jurídica. O marcador
    `confirmado=False` força revisão humana.
    """
    matriz: list[dict[str, Any]] = []
    for prova in provas:
        if not isinstance(prova, dict):
            continue
        fato = _texto(prova.get("fato_probando"), 1_000)
        titulo_prova = _texto(prova.get("titulo"), 500)
        if not fato and not titulo_prova:
            continue
        ft = _tokens(fato or titulo_prova)
        candidatos: list[tuple[float, str]] = []
        for tese in teses:
            if not isinstance(tese, dict):
                continue
            titulo = _texto(tese.get("titulo"), 400)
            contexto = " ".join(
                x for x in (
                    titulo,
                    _texto(tese.get("aplicabilidade"), 1_000),
                    _texto(tese.get("fundamento_legal"), 500),
                ) if x
            )
            tt = _tokens(contexto)
            if not ft or not tt:
                continue
            score = len(ft & tt) / max(1, len(ft | tt))
            if score >= 0.06 and titulo:
                candidatos.append((score, titulo))
        candidatos.sort(reverse=True)
        matriz.append({
            "fato": fato,
            "prova": titulo_prova,
            "tipo_prova": _texto(prova.get("tipo"), 80),
            "prova_ja_disponivel": bool(prova.get("ja_disponivel")),
            "quem_produz": _texto(prova.get("quem_produz"), 100),
            "urgencia": _texto(prova.get("urgencia"), 40),
            "teses_relacionadas": [titulo for _, titulo in candidatos[:3]],
            "metodo_correlacao_tese": "lexical_preliminar" if candidatos else None,
            "confirmado": False,
            "observacao": (
                "Correlação indicativa; autenticidade, admissibilidade, força da prova e "
                "vínculo com a tese devem ser confirmados pelo advogado."
            ),
        })
    return matriz


def _estimativa_sucesso(analise: dict) -> dict:
    jur = analise.get("jurimetria") if isinstance(analise, dict) else None
    jur = jur if isinstance(jur, dict) else {}
    base = _texto(jur.get("base_estimativa"), 1_500)
    raw = jur.get("chance_sucesso_percent")
    try:
        percentual = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        percentual = None
    if percentual is None or not (0 <= percentual <= 100) or not base:
        return {
            "percentual": None,
            "status": "sem_base_verificavel",
            "base_estimativa": base,
            "observacao": (
                "Não há base concreta suficiente para exibir percentual de êxito. "
                "O EJC não fabrica probabilidade."
            ),
        }
    return {
        "percentual": round(percentual, 1),
        "status": "estimativa_interna_com_base",
        "base_estimativa": base,
        "observacao": _texto(jur.get("observacao"), 1_000)
        or "Estimativa interna, não é promessa de resultado e exige validação humana.",
        "tempo_estimado_meses": jur.get("tempo_estimado_meses"),
        "faixa_valor_min": jur.get("faixa_valor_min"),
        "faixa_valor_max": jur.get("faixa_valor_max"),
    }


def _perguntas_lacunas(analise: dict, case, provas: list[dict]) -> list[dict[str, str]]:
    perguntas: list[dict[str, str]] = []
    for prova in provas:
        if not isinstance(prova, dict) or prova.get("ja_disponivel"):
            continue
        titulo = _texto(prova.get("titulo"), 300) or "prova indicada na análise"
        fato = _texto(prova.get("fato_probando"), 500)
        perguntas.append({
            "tipo": "prova_faltante",
            "pergunta": f"Existe ou é possível obter {titulo}?",
            "motivo": f"Necessária para esclarecer/provar: {fato}" if fato else "Prova indicada como faltante na análise.",
        })
    if not case.numero_processo and _enum_value(case.case_type) == "judicial":
        perguntas.append({
            "tipo": "identificacao_processual",
            "pergunta": "Já existe processo judicial? Se sim, informe o número CNJ.",
            "motivo": "O caso ainda não possui número de processo registrado.",
        })
    if not case.parte_contraria:
        perguntas.append({
            "tipo": "parte",
            "pergunta": "Quem é a parte contrária e qual é sua qualificação conhecida?",
            "motivo": "A parte contrária ainda não está confirmada no caso.",
        })
    brechas = analise.get("brechas_preliminares") if isinstance(analise, dict) else {}
    brechas = brechas if isinstance(brechas, dict) else {}
    if not brechas.get("prescricao"):
        perguntas.append({
            "tipo": "prescricao",
            "pergunta": "Quais são as datas do fato, da ciência e de eventual interrupção/suspensão do prazo?",
            "motivo": "São necessárias para validar prescrição/decadência com segurança.",
        })
    return perguntas[:12]


def _sanitizar_arvore(value: Any, nomes: list[str]) -> Any:
    """Payload do snapshot não guarda nomes das partes em claro."""
    if isinstance(value, dict):
        return {k: _sanitizar_arvore(v, nomes) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitizar_arvore(v, nomes) for v in value]
    if isinstance(value, str):
        from app.services.sanitizer import sanitizar_pii
        limpo, _ = sanitizar_pii(value, nomes)
        return limpo
    return value


def _contradicoes_do_relatorio(relatorio: Any) -> list[dict[str, Any]]:
    """Extrai apenas contradições já estruturadas pelo Raio-X.

    Não tenta inferir contradições de texto livre aqui. O Raio-X usa o detector
    determinístico `detectar_contradicoes_documentais`, que preserva origem e
    marca todo achado como não confirmado.
    """
    if not isinstance(relatorio, dict):
        return []
    itens = relatorio.get("contradicoes")
    if not isinstance(itens, list):
        return []
    return [item for item in itens if isinstance(item, dict)][:30]


async def _contradicoes_raio_x(db, user, case_id: str) -> list[dict[str, Any]]:
    """Reusa o último Raio-X visível ligado ao caso, sem ampliar o escopo RBAC."""
    stmt = (
        select(RaioXAnalise)
        .where(
            RaioXAnalise.deleted_at.is_(None),
            or_(
                RaioXAnalise.convertido_case_id == case_id,
                RaioXAnalise.origem_contextual_case_id == case_id,
            ),
        )
        .order_by(RaioXAnalise.created_at.desc())
        .limit(10)
    )
    if not is_gestao(user):
        stmt = stmt.where(RaioXAnalise.created_by == user.id)
    rows = list((await db.execute(stmt)).scalars().all())
    for analise in rows:
        contradicoes = _contradicoes_do_relatorio(analise.relatorio)
        if contradicoes:
            return contradicoes
    return []


async def gerar_dossie_juridico(db, user, case_id: str) -> dict[str, Any]:
    """Gera o dossiê completo, versiona o plano e devolve ações seguras."""
    case = await verificar_acesso_caso(db, user, case_id)
    area = _enum_value(case.area) or ""

    cliente = await db.get(Client, case.client_id)
    nome_cliente = cliente.nome_exibicao if cliente else None

    partes_rows = list((await db.execute(
        select(CaseParte).where(CaseParte.case_id == case.id, CaseParte.ativo.is_(True))
        .order_by(CaseParte.tipo, CaseParte.nome)
    )).scalars().all())
    partes = [
        {
            "id": p.id,
            "nome": p.nome,
            "tipo": p.tipo,
            "papel_processual": p.papel_processual,
            "qualificacao": p.qualificacao,
        }
        for p in partes_rows
    ]

    docs_rows = list((await db.execute(
        select(Document).where(
            Document.case_id == case.id,
            Document.deleted_at.is_(None),
            Document.confidencialidade.in_(confidencialidades_visiveis(user)),
        ).order_by(Document.created_at.asc())
    )).scalars().all())
    documentos = [
        {"id": d.id, "titulo": d.titulo, "tipo": d.tipo, "versao": d.versao}
        for d in docs_rows
    ]

    movimentos = list((await db.execute(
        select(CaseMovimento).where(CaseMovimento.case_id == case.id)
        .order_by(CaseMovimento.data_evento.asc())
        .limit(100)
    )).scalars().all())
    cronologia = [
        {
            "data": m.data_evento.isoformat() if m.data_evento else None,
            "tipo": m.tipo,
            "evento": m.descricao,
            "origem": "timeline_do_caso",
        }
        for m in movimentos
    ]

    texto_base = await texto_base_do_caso(db, case, None)
    partes_ctx = "; ".join(
        f"{p['tipo']}: {p['nome']}" for p in partes if p.get("nome")
    )
    analise = await analisar_caso(
        titulo=case.titulo or "",
        objeto=case.proxima_acao or "",
        fatos=case.descricao_fatos or "",
        texto_documento=texto_base or "",
        partes_existentes=partes_ctx,
        numero_processo=case.numero_processo or "",
        area=area,
        nomes_proteger=[x for x in [nome_cliente, case.parte_contraria, *[p["nome"] for p in partes]] if x],
        scope_client_id=case.client_id,
        case_id=case.id,
        db=db,
        user_id=user.id,
    )
    if not isinstance(analise, dict):
        analise = {"erro": "Análise estratégica indisponível"}

    # Teses canônicas do banco: nunca são inventadas pela IA.
    from app.routers import intake as intake_router
    teses_banco = await intake_router._buscar_teses(db, area)

    # Honorários sugeridos: motor DETERMINÍSTICO, tabela OAB/MG vigente.
    honorarios = await fee_proposal_service.sugerir_proposta(db, case, area)

    # Pedidos possíveis reaproveitam a triagem existente; falha não derruba o dossiê.
    pedidos_possiveis: list[str] = []
    triagem_ai_log_id: str | None = None
    if len((case.descricao_fatos or texto_base or "").strip()) >= 40:
        try:
            from app.services.triagem_entrevista_service import analisar_relato
            triagem = await analisar_relato(
                db, user, (case.descricao_fatos or texto_base)[:15_000], case_id=case.id
            )
            painel = triagem.get("analise") or {}
            pedidos_possiveis = _lista(painel.get("pedidos_possiveis"))
            triagem_ai_log_id = triagem.get("ai_log_id")
        except Exception:
            pedidos_possiveis = []

    provas = _lista(analise.get("provas_necessarias"))
    teses_ia = _lista(analise.get("teses_campeas"))
    matriz = _correlacionar_fato_prova_tese(provas, teses_ia)
    estimativa = _estimativa_sucesso(analise)
    perguntas = _perguntas_lacunas(analise, case, provas)
    contradicoes_documentais = await _contradicoes_raio_x(db, user, case.id)

    brechas = analise.get("brechas_preliminares")
    brechas = brechas if isinstance(brechas, dict) else {}
    adversarial: dict[str, Any] | None = None
    if get_settings().DUAS_IAS_ENABLED and not analise.get("erro"):
        try:
            from app.services.ai.adversarial import criticar_peca
            critica = await criticar_peca(
                db,
                texto_peca=json.dumps(analise, ensure_ascii=False, default=str),
                contexto_caso=(case.descricao_fatos or case.titulo or "")[:6_000],
                task_type_origem="analise_entrada_unica",
                case_id=case.id,
            )
            adversarial = {
                "disponivel": critica.disponivel,
                "nota_robustez": critica.nota_robustez,
                "relatorio": critica.relatorio,
                "alertas": critica.alertas,
                "aviso": critica.aviso,
            }
        except Exception:
            adversarial = {"disponivel": False, "relatorio": None, "alertas": []}

    estrategia = analise.get("estrategia") if isinstance(analise.get("estrategia"), dict) else {}
    plano = {
        "estrategia": estrategia,
        "tese_principal": teses_ia[0] if teses_ia else None,
        "teses_subsidiarias": teses_ia[1:] if len(teses_ia) > 1 else [],
        "pedidos_possiveis": pedidos_possiveis,
        "provas_necessarias": provas,
        "riscos": _lista(analise.get("riscos")),
        "proximos_passos": _lista(analise.get("proximos_passos")),
        "argumentos_adversos_provaveis": _lista(brechas.get("falhas_da_parte_contraria")),
        "alternativas": {
            "agressiva": estrategia.get("cenario_agressivo"),
            "moderada": estrategia.get("cenario_moderado"),
            "defensiva": estrategia.get("cenario_defensivo"),
        },
        "decisao_humana_pendente": True,
    }

    conteudo = identificar_conteudo(
        " ".join(x for x in [case.titulo, case.descricao_fatos, case.numero_processo] if x),
        documentos,
    )
    # Uma análise disparada de um caso já criado é, operacionalmente, caso existente.
    conteudo["tipos"] = ["caso_existente", *[x for x in conteudo["tipos"] if x not in {"caso_novo", "caso_existente"}]]

    resposta = {
        "status": "rascunho",
        "aviso": AVISO_DOSSIE,
        "case_id": case.id,
        "conteudo_identificado": conteudo,
        "identificacao": {
            "cliente": {"id": case.client_id, "nome": nome_cliente},
            "partes": partes,
            "ramo": analise.get("ramo") or area,
            "subramo": analise.get("subramo"),
            "area_canonica": area,
            "numero_processo": case.numero_processo,
            "tribunal": case.tribunal,
            "comarca": case.comarca,
            "vara": case.vara,
            "fase": _enum_value(case.fase),
        },
        "fatos": {
            "sumario": analise.get("sumario_fatos") or case.descricao_fatos,
            "pontos_fortes": _lista(analise.get("pontos_fortes")),
            "pontos_fracos": _lista(analise.get("pontos_fracos")),
            "cronologia": cronologia,
            "origem": "caso_documentos_e_analise_estrategica",
        },
        "provas": {
            "documentos_existentes": documentos,
            "necessarias": provas,
            "matriz_fato_prova_tese": matriz,
        },
        "lacunas": {"perguntas": perguntas},
        "contradicoes_e_adversarial": {
            "contradicoes_documentais": contradicoes_documentais,
            "fonte_contradicoes": (
                "raio_x_estruturado" if contradicoes_documentais else None
            ),
            "falhas_da_parte_contraria": _lista(brechas.get("falhas_da_parte_contraria")),
            "pontos_fracos": _lista(analise.get("pontos_fracos")),
            "critica_adversarial": adversarial,
            "observacao": (
                "Contradições documentais vêm apenas do detector estruturado do Raio-X "
                "visível ao usuário e permanecem não confirmadas; a crítica adversarial "
                "é hipótese para revisão, não fato."
            ),
        },
        "analise_juridica": {
            "teses_do_banco": teses_banco,
            "teses_analisadas": teses_ia,
            "riscos": _lista(analise.get("riscos")),
            "brechas_preliminares": brechas,
            "fontes_rag": _lista(analise.get("_fontes_rag")),
            "verificacao_citacoes": analise.get("_verificacao_citacoes"),
            "alertas": _lista(analise.get("alertas")),
            "erro": analise.get("erro"),
        },
        "honorarios_sugeridos": honorarios,
        "estimativa_sucesso": estimativa,
        "plano_juridico": plano,
        "revisao_obrigatoria": True,
    }

    nomes = [x for x in [nome_cliente, case.parte_contraria, *[p["nome"] for p in partes]] if x]
    fontes_snapshot = [
        "entrada_unica",
        "analise_estrategica",
        "banco_teses",
        "tabela_oab",
    ]
    if contradicoes_documentais:
        fontes_snapshot.append("raio_x_estruturado")
    snapshot_payload = _sanitizar_arvore(
        {
            "area": area,
            "fatos": resposta["fatos"],
            "teses": {
                "principal": plano["tese_principal"],
                "secundarias": plano["teses_subsidiarias"],
            },
            "riscos": plano["riscos"],
            "provas": resposta["provas"],
            "contradicoes": contradicoes_documentais,
            "honorarios": honorarios,
            "estimativa_sucesso": estimativa,
            "plano_juridico": plano,
            "fontes": fontes_snapshot,
        },
        nomes,
    )
    snapshot_payload = cis.compactar_payload(
        snapshot_payload,
        descartaveis=("provas", "honorarios"),
    )

    role = getattr(user.role, "value", user.role)
    await criar_audit_log(
        db,
        user.id,
        str(role),
        "AI_USE",
        "entrada_unica_dossie",
        case.id,
        detalhes="Dossiê jurídico canônico gerado; pendente de aprovação humana",
    )
    snap = await cis.criar_snapshot(
        db,
        case_id=case.id,
        origem="entrada_unica",
        payload=snapshot_payload,
        resumo=f"Entrada Única — plano jurídico em revisão ({area or 'área não definida'})",
        ai_log_ids=[x for x in [triagem_ai_log_id] if x],
        criado_por=user.id,
    )

    resposta["snapshot"] = {
        "id": snap.id,
        "versao": snap.versao,
        "congelado": False,
        "aprovar_endpoint": f"/cases/{case.id}/inteligencia/{snap.id}/aprovar",
    }
    resposta["acoes"] = {
        "aprovar_plano": f"/cases/{case.id}/inteligencia/{snap.id}/aprovar",
        "orquestrador": f"/cases/{case.id}/orquestrador",
        "preparar_peca": f"/cases/{case.id}/motor-peca/analisar",
        "gerar_peca": f"/cases/{case.id}/motor-peca/gerar",
        "gerar_peca_disponivel": False,
        "motivo": "Aprove o plano jurídico e satisfaça os gates do Motor de Peça antes da redação.",
    }
    return resposta
