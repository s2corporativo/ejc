# ── app/routers/jornada_caso.py ───────────────────────────────────────────────
# Jornada do Caso — estado DETERMINÍSTICO das 9 etapas do fluxo do escritório:
#
#   GET /casos/{case_id}/jornada → JornadaCasoOut (contrato fixo p/ o frontend)
#
# Decisões:
#   • ZERO chamada de IA: cada status nasce de contagens/campos que já existem
#     no banco (Client, AILog, Document, DossieEstrategico, Tese/TeseCasoLink,
#     LegalDoc, Deadline) — barato, reprodutível e auditável;
#   • cada regra vive numa função PURA (_etapa_*) que recebe dados simples —
#     o handler só coleta os dados e monta a resposta (testável sem banco);
#   • segurança no padrão dos vizinhos (provas.py): ownership por caso via
#     core/ownership.verificar_acesso_caso + rate_limit em toda rota;
#   • LGPD: a resposta carrega apenas nomes de campos faltantes e contagens —
#     nunca CPF/CNPJ, contatos ou conteúdo de documentos.
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.ai_log import AILog, AITipoUso
from app.models.client import Client
from app.models.deadline import Deadline, DeadlineStatus
from app.models.document import Document
from app.models.dossie_estrategico import DossieEstrategico
from app.models.legal_doc import LegalDoc
from app.models.tese import TeseCasoLink
from app.models.user import User
from app.schemas.jornada_caso import EtapaJornada, JornadaCasoOut
from app.services.case_health import FECHADOS, calcular_score_caso

router = APIRouter(prefix="/casos/{case_id}/jornada", tags=["Jornada do Caso"])

# Ciclo de vida do LegalDoc (models/legal_doc.py + routers/legal_docs.py):
# rascunho pertence à etapa Produção; em_revisao/corrigida ao ciclo HITL da
# etapa Revisão; aprovada/final/protocolada já passaram pelo gate humano.
_PECA_PRONTA = {"aprovada", "final", "protocolada"}


def _val(x) -> Optional[str]:
    """Enum → valor string (tolerante a fakes que já passam str)."""
    if x is None:
        return None
    return x.value if hasattr(x, "value") else str(x)


# ── Regras puras (uma por etapa — testáveis sem banco) ────────────────────────

def _etapa_cliente(client, case_id: str) -> EtapaJornada:
    """Sem cliente=pendente; cliente com cadastro incompleto=em_andamento
    (pendências nomeiam apenas o CAMPO faltante — nunca o valor, LGPD);
    documento fiscal + contato presentes=concluida."""
    if client is None:
        return EtapaJornada(
            chave="cliente", titulo="Cliente", status="pendente",
            resumo="Nenhum cliente vinculado ao caso.",
            pendencias=["vincular cliente ao caso"], link_modulo="/clientes",
        )

    pendencias: list[str] = []
    # PF exige CPF, PJ exige CNPJ — cifrado (dual-write LGPD) também conta.
    tipo = _val(getattr(client, "tipo", None)) or "PF"
    if tipo == "PJ":
        if not (getattr(client, "cnpj", None) or getattr(client, "cnpj_enc", None)):
            pendencias.append("CNPJ não cadastrado")
    else:
        if not (getattr(client, "cpf", None) or getattr(client, "cpf_enc", None)):
            pendencias.append("CPF não cadastrado")
    if not (getattr(client, "email", None) or getattr(client, "telefone", None)
            or getattr(client, "whatsapp", None)):
        pendencias.append("contato (email/telefone/whatsapp) ausente")

    nome = getattr(client, "nome_exibicao", None) or "Cliente"
    if pendencias:
        return EtapaJornada(
            chave="cliente", titulo="Cliente", status="em_andamento",
            resumo=f"{nome}: cadastro incompleto.", pendencias=pendencias,
            link_modulo=f"/clientes/{client.id}",
        )
    return EtapaJornada(
        chave="cliente", titulo="Cliente", status="concluida",
        resumo=f"{nome}: cadastro completo.",
        link_modulo=f"/clientes/{client.id}",
    )


def _etapa_triagem(total_analises: int, case_id: str) -> EtapaJornada:
    """Triagem = existe AILog de análise do caso (AITipoUso.analise_caso — o
    tipo gravado por routers/intake.py e ai.py). Binária: nenhum=pendente,
    existe=concluida (não há estado intermediário persistido)."""
    if total_analises <= 0:
        return EtapaJornada(
            chave="triagem", titulo="Triagem e análise inicial", status="pendente",
            resumo="Nenhuma análise de triagem registrada.",
            pendencias=["executar a análise inicial do caso"],
            link_modulo=f"/casos/{case_id}",
        )
    return EtapaJornada(
        chave="triagem", titulo="Triagem e análise inicial", status="concluida",
        resumo=f"{total_analises} análise(s) de triagem registrada(s).",
        link_modulo=f"/casos/{case_id}",
    )


def _etapa_documentos(total_docs: int, docs_processados: int,
                      case_id: str) -> EtapaJornada:
    """GED: 0 docs=pendente; docs sem intake completo=em_andamento; todos
    processados=concluida. Proxy de 'processado' = ocr_text preenchido — o
    pipeline de intake (documento_service.extrair_e_analisar) NÃO persiste
    resultado por documento; o texto extraído no upload é o único rastro."""
    link = f"/documentos?caso={case_id}"
    if total_docs <= 0:
        return EtapaJornada(
            chave="documentos", titulo="Documentos (GED)", status="pendente",
            resumo="Nenhum documento anexado ao caso.",
            pendencias=["anexar documentos do caso"], link_modulo=link,
        )
    faltam = max(0, total_docs - docs_processados)
    if faltam > 0:
        return EtapaJornada(
            chave="documentos", titulo="Documentos (GED)", status="em_andamento",
            resumo=f"{total_docs} documento(s); {faltam} sem texto extraído.",
            pendencias=[f"{faltam} documento(s) sem leitura/intake processado"],
            link_modulo=link,
        )
    return EtapaJornada(
        chave="documentos", titulo="Documentos (GED)", status="concluida",
        resumo=f"{total_docs} documento(s), todos com leitura processada.",
        link_modulo=link,
    )


def _etapa_inteligencia(status_dossies: list[str], case_id: str) -> EtapaJornada:
    """Heurística: existência de DossieEstrategico do caso (registro persistido
    — nunca gera IA aqui). Nenhum=pendente; só rascunho=em_andamento; algum
    aprovado=concluida (aprovação é o gate humano do dossiê)."""
    link = f"/casos/{case_id}/sala-de-guerra"
    ativos = [s for s in status_dossies if s != "arquivado"]
    if not ativos:
        return EtapaJornada(
            chave="inteligencia", titulo="Inteligência (dossiê)", status="pendente",
            resumo="Nenhum dossiê estratégico gerado.",
            pendencias=["gerar o dossiê estratégico do caso"], link_modulo=link,
        )
    if "aprovado" in ativos:
        return EtapaJornada(
            chave="inteligencia", titulo="Inteligência (dossiê)", status="concluida",
            resumo=f"{len(ativos)} dossiê(s), com versão aprovada.",
            link_modulo=link,
        )
    return EtapaJornada(
        chave="inteligencia", titulo="Inteligência (dossiê)", status="em_andamento",
        resumo=f"{len(ativos)} dossiê(s) em rascunho, aguardando aprovação.",
        pendencias=["aprovar o dossiê estratégico"], link_modulo=link,
    )


def _etapa_estrategia(tem_tese_principal: bool, teses_vinculadas: int,
                      case_id: str) -> EtapaJornada:
    """Heurística determinística: Case.tese_principal preenchida = decisão
    estratégica tomada (concluida); só teses vinculadas (TeseCasoLink, N:N com
    o Banco de Teses) = estratégia em construção (em_andamento); nada=pendente."""
    link = f"/casos/{case_id}/sala-de-guerra"
    if tem_tese_principal:
        extra = f" · {teses_vinculadas} tese(s) do banco vinculada(s)" if teses_vinculadas else ""
        return EtapaJornada(
            chave="estrategia", titulo="Estratégia e teses", status="concluida",
            resumo=f"Tese principal definida{extra}.", link_modulo=link,
        )
    if teses_vinculadas > 0:
        return EtapaJornada(
            chave="estrategia", titulo="Estratégia e teses", status="em_andamento",
            resumo=f"{teses_vinculadas} tese(s) vinculada(s), sem tese principal definida.",
            pendencias=["definir a tese principal do caso"], link_modulo=link,
        )
    return EtapaJornada(
        chave="estrategia", titulo="Estratégia e teses", status="pendente",
        resumo="Nenhuma estratégia registrada.",
        pendencias=["definir tese principal ou vincular teses do banco"],
        link_modulo=link,
    )


def _etapa_producao(contagem_por_status: dict[str, int],
                    case_id: str) -> EtapaJornada:
    """Peças (LegalDoc) por status: 0=pendente; alguma em trabalho
    (rascunho/em_revisao/corrigida)=em_andamento; todas prontas=concluida.
    Resumo traz a contagem por status (só números — sem conteúdo)."""
    link = f"/pecas?caso={case_id}"
    total = sum(contagem_por_status.values())
    if total <= 0:
        return EtapaJornada(
            chave="producao", titulo="Produção de peças", status="pendente",
            resumo="Nenhuma peça produzida.",
            pendencias=["produzir a primeira peça do caso"], link_modulo=link,
        )
    detalhe = " · ".join(f"{k}: {v}" for k, v in sorted(contagem_por_status.items()))
    # Produção mede a REDAÇÃO (rascunhos); o ciclo revisar/aprovar é medido
    # pela etapa seguinte — sem isso as duas etapas espelhavam o mesmo status
    # e nunca exibiam "Produção concluída, Revisão em andamento".
    em_redacao = contagem_por_status.get("rascunho", 0)
    if em_redacao > 0:
        return EtapaJornada(
            chave="producao", titulo="Produção de peças", status="em_andamento",
            resumo=f"{total} peça(s) ({detalhe}).",
            pendencias=[f"{em_redacao} peça(s) ainda em elaboração"],
            link_modulo=link,
        )
    return EtapaJornada(
        chave="producao", titulo="Produção de peças", status="concluida",
        resumo=f"{total} peça(s) ({detalhe}).", link_modulo=link,
    )


def _etapa_revisao(contagem_por_status: dict[str, int],
                   case_id: str) -> EtapaJornada:
    """Revisão HITL das peças: sem peça=pendente; alguma aguardando o ciclo
    revisar/corrigir/aprovar (routers/legal_docs.py)=em_andamento; todas em
    status pós-aprovação (aprovada/final/protocolada)=concluida."""
    link = f"/pecas?caso={case_id}"
    total = sum(contagem_por_status.values())
    if total <= 0:
        return EtapaJornada(
            chave="revisao", titulo="Revisão e aprovação", status="pendente",
            resumo="Sem peças para revisar.",
            pendencias=["produzir peças antes da revisão"], link_modulo=link,
        )
    # Revisão mede o CICLO HITL (em_revisao/corrigida → aprovação): peça em
    # rascunho ainda não entrou aqui — pertence à etapa de Produção.
    em_ciclo = sum(contagem_por_status.get(k, 0) for k in ("em_revisao", "corrigida"))
    aprovadas = sum(v for k, v in contagem_por_status.items() if k in _PECA_PRONTA)
    if em_ciclo > 0:
        return EtapaJornada(
            chave="revisao", titulo="Revisão e aprovação", status="em_andamento",
            resumo=f"{em_ciclo} peça(s) no ciclo de revisão; {aprovadas} aprovada(s).",
            pendencias=[f"revisar e aprovar {em_ciclo} peça(s)"], link_modulo=link,
        )
    if aprovadas <= 0:
        return EtapaJornada(
            chave="revisao", titulo="Revisão e aprovação", status="pendente",
            resumo="Nenhuma peça submetida à revisão ainda.",
            pendencias=["enviar as peças produzidas para revisão"], link_modulo=link,
        )
    return EtapaJornada(
        chave="revisao", titulo="Revisão e aprovação", status="concluida",
        resumo=f"{aprovadas} peça(s) revisada(s) e aprovada(s).", link_modulo=link,
    )


def _etapa_protocolo(numero_processo: Optional[str], fase: Optional[str],
                     case_id: str) -> EtapaJornada:
    """Protocolado = nº do processo registrado OU fase já saiu de
    pre_processual (casos administrativos/judiciais em curso). Caso contrário,
    pendente — a pendência é a ação concreta."""
    link = f"/casos/{case_id}"
    if numero_processo or (fase and fase != "pre_processual"):
        resumo = (f"Processo {numero_processo} registrado." if numero_processo
                  else f"Caso em fase '{fase}' (além da pré-processual).")
        return EtapaJornada(
            chave="protocolo", titulo="Protocolo", status="concluida",
            resumo=resumo, link_modulo=link,
        )
    return EtapaJornada(
        chave="protocolo", titulo="Protocolo", status="pendente",
        resumo="Caso ainda pré-processual, sem número de processo.",
        pendencias=["protocolar e registrar nº do processo"], link_modulo=link,
    )


def _etapa_gestao(caso_fechado: bool, prazos_abertos: int,
                  saude: Optional[dict], case_id: str) -> EtapaJornada:
    """Gestão contínua: caso fechado=concluida; fase ativa com prazos
    monitorados=em_andamento; sem nenhum prazo cadastrado=pendente. As
    pendências reusam os FATORES do case_health (calcular_score_caso) — só a
    parte determinística/barata: detalhes de dedução já calculados, sem IA."""
    link = f"/prazos?caso={case_id}"
    fatores = [f.get("detalhe", f.get("fator", "")) for f in (saude or {}).get("fatores", [])]
    score = (saude or {}).get("score")
    sufixo_saude = f" Saúde do caso: {score}/100." if score is not None else ""

    if caso_fechado:
        # Concluída não carrega pendências: alertas de saúde sob o badge
        # "Concluída" viravam ruído visual na UI (achado de revisão).
        return EtapaJornada(
            chave="gestao", titulo="Gestão e prazos", status="concluida",
            resumo=f"Caso encerrado/arquivado — gestão finalizada.{sufixo_saude}",
            link_modulo=link,
        )
    if prazos_abertos > 0:
        return EtapaJornada(
            chave="gestao", titulo="Gestão e prazos", status="em_andamento",
            resumo=f"{prazos_abertos} prazo(s) em aberto monitorado(s).{sufixo_saude}",
            pendencias=fatores, link_modulo=link,
        )
    return EtapaJornada(
        chave="gestao", titulo="Gestão e prazos", status="pendente",
        resumo=f"Nenhum prazo em aberto cadastrado.{sufixo_saude}",
        pendencias=["cadastrar prazos e rotina de acompanhamento do caso"] + fatores,
        link_modulo=link,
    )


def montar_etapas(*, case_id: str, client, total_analises: int, total_docs: int,
                  docs_processados: int, status_dossies: list[str],
                  tem_tese_principal: bool, teses_vinculadas: int,
                  pecas_por_status: dict[str, int], numero_processo: Optional[str],
                  fase: Optional[str], caso_fechado: bool, prazos_abertos: int,
                  saude: Optional[dict]) -> list[EtapaJornada]:
    """Monta as 9 etapas SEMPRE na ordem canônica do contrato — função pura
    (o handler só injeta os dados coletados)."""
    return [
        _etapa_cliente(client, case_id),
        _etapa_triagem(total_analises, case_id),
        _etapa_documentos(total_docs, docs_processados, case_id),
        _etapa_inteligencia(status_dossies, case_id),
        _etapa_estrategia(tem_tese_principal, teses_vinculadas, case_id),
        _etapa_producao(pecas_por_status, case_id),
        _etapa_revisao(pecas_por_status, case_id),
        _etapa_protocolo(numero_processo, fase, case_id),
        _etapa_gestao(caso_fechado, prazos_abertos, saude, case_id),
    ]


# ── Rota ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=JornadaCasoOut,
            dependencies=[Depends(rate_limit("jornada-caso", 60))])
async def jornada_do_caso(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Estado determinístico da jornada do caso nas 9 etapas do fluxo do
    escritório. Somente leitura; nenhuma chamada de IA."""
    case = await verificar_acesso_caso(db, cu, case_id)

    client = (await db.execute(
        select(Client).where(Client.id == case.client_id,
                             Client.deleted_at.is_(None))
    )).scalar_one_or_none()

    total_analises = (await db.execute(
        select(func.count()).select_from(AILog).where(
            AILog.case_id == case_id,
            AILog.tipo_uso == AITipoUso.analise_caso)
    )).scalar() or 0

    total_docs = (await db.execute(
        select(func.count()).select_from(Document).where(
            Document.case_id == case_id, Document.deleted_at.is_(None))
    )).scalar() or 0
    docs_processados = (await db.execute(
        select(func.count()).select_from(Document).where(
            Document.case_id == case_id, Document.deleted_at.is_(None),
            Document.ocr_text.isnot(None))
    )).scalar() or 0

    status_dossies = [
        _val(s) for s in (await db.execute(
            select(DossieEstrategico.status).where(
                DossieEstrategico.case_id == case_id)
        )).scalars().all()
    ]

    teses_vinculadas = (await db.execute(
        select(func.count()).select_from(TeseCasoLink).where(
            TeseCasoLink.case_id == case_id)
    )).scalar() or 0

    pecas_por_status: dict[str, int] = {}
    for status, qtd in (await db.execute(
        select(LegalDoc.status, func.count()).where(
            LegalDoc.case_id == case_id, LegalDoc.deleted_at.is_(None))
        .group_by(LegalDoc.status)
    )).all():
        pecas_por_status[_val(status) or "?"] = qtd

    prazos_abertos = (await db.execute(
        select(func.count()).select_from(Deadline).where(
            Deadline.case_id == case_id, Deadline.deleted_at.is_(None),
            Deadline.status == DeadlineStatus.pendente)
    )).scalar() or 0

    # Reuso do case_health (fonte única do score): apenas contagens no banco,
    # sem IA — devolve score + fatores que alimentam as pendências de gestão.
    saude = await calcular_score_caso(db, case)

    etapas = montar_etapas(
        case_id=case_id, client=client, total_analises=total_analises,
        total_docs=total_docs, docs_processados=docs_processados,
        status_dossies=status_dossies,
        tem_tese_principal=bool((case.tese_principal or "").strip()),
        teses_vinculadas=teses_vinculadas, pecas_por_status=pecas_por_status,
        numero_processo=case.numero_processo, fase=_val(case.fase),
        caso_fechado=case.status in FECHADOS, prazos_abertos=prazos_abertos,
        saude=saude,
    )

    return JornadaCasoOut(
        case_id=case.id, titulo=case.titulo, fase=_val(case.fase),
        numero_processo=case.numero_processo, cliente_id=case.client_id,
        etapas=etapas,
    )
