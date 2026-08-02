# ── app/services/entrada_service.py ──────────────────────────────────────────
# Entrada Única (Bloco 3 — docs/DESENHO_BLOCO3_TELAS.md, seções 4 e 6).
#
# Este service ORQUESTRA o que já existe — nenhuma chamada de IA nova, nenhum
# prompt novo além da fusão mínima:
#   arquivos → pipeline da Entrada Universal (persistir → hash → OCR →
#              classificar → análise pelo núcleo, fail-soft);
#   texto    → Entrevista Inteligente (services/triagem_entrevista_service);
#   cliente  → índice HMAC cego (conflito_service._clientes_por_documentos,
#              que usa pii_crypto.hash_documento) + nome como CANDIDATO;
#   conflito → primitivas de conflito_service com os guards de carteira de
#              client_ownership (mesmo padrão de legal_chat_service.
#              preview_conversao — protegido colapsa, nunca vaza).
#
# IA indisponível NUNCA derruba a análise: o determinístico é preservado e a
# resposta sai com degradado=true + avisos[]. Toda saída de IA é RASCUNHO com
# requer_confirmacao_humana e AILog (HITL) — herdado dos pipelines de origem.
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ownership import (
    obter_cliente_autorizado,
    pode_ver_caso_resumido,
    pode_ver_cliente,
)
from app.core.config import get_settings
from app.core.ownership import is_gestao
from app.core.security import ROLE_LEVEL
from app.models.audit_log import criar_audit_log
from app.models.case import Case, CaseArea, CaseMovimento, CaseStatus
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.document import DocConfidencialidade, Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.models.user import User
from app.services.case_numeracao import proximo_numero_interno
from app.services.conflito_service import (
    _casos_por_parte_contraria,
    _clientes_por_documentos,
    _clientes_por_nome,
)
from app.services.status_transicao import avancar_status_por_evento

logger = logging.getLogger("ejc.entrada_unica")

#: Guarda G1 (mesma doutrina de cases.py/converter_em_caso): caso nunca nasce
#: sem "o que fazer agora".
PROXIMA_ACAO_DEFAULT = (
    "Revisar a proposta da Entrada Única e definir a próxima providência"
)

AVISO_HITL = (
    "Proposta gerada por análise automática — RASCUNHO. Área, prazo e fatos "
    "sugeridos por IA exigem confirmação humana (OAB Prov. 205/2021)."
)


def _role(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


# ── Identificação de cliente (índice cego → certeza; nome → candidato) ───────

async def identificar_cliente(
    db: AsyncSession, user: User, *,
    cpf: str | None = None, cnpj: str | None = None, nome: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Retorna (cliente_proposto, duplicados_clientes, avisos).

    CPF/CNPJ extraído casa via índice HMAC cego (pii_crypto.hash_documento,
    dentro de _clientes_por_documentos) — busca EXATA, nunca em claro. Sem
    documento, o nome vira apenas CANDIDATO (ILIKE), jamais certeza. Carteira
    alheia nunca vaza: correspondência protegida vira aviso/entrada colapsada
    (mesmo padrão de preview_conversao)."""
    avisos: list[str] = []
    duplicados: list[dict[str, Any]] = []

    # 1) Documento exato (índice cego) — identificação de confiança alta.
    for c in await _clientes_por_documentos(db, [cpf, cnpj]):
        if await pode_ver_cliente(db, user, c):
            return (
                {
                    "client_id": c.id, "nome": c.nome_exibicao,
                    "ja_cadastrado": True,
                    "origem": "CPF/CNPJ extraído dos documentos (índice cego)",
                    "confianca": "alta",
                },
                duplicados, avisos,
            )
        avisos.append(
            "CPF/CNPJ extraído corresponde a cliente em carteira protegida — "
            "solicite revisão à gestão antes de prosseguir."
        )

    # 2) Nome: candidatos possivelmente duplicados (nunca seleção automática).
    houve_protegido = False
    if nome:
        for c in await _clientes_por_nome(db, nome):
            if await pode_ver_cliente(db, user, c):
                duplicados.append(
                    {"id": c.id, "nome": c.nome_exibicao, "protegido": False}
                )
            else:
                houve_protegido = True
    if houve_protegido:
        duplicados.append({
            "id": None,
            "nome": "Cliente protegido na base do escritório",
            "protegido": True,
        })

    nome_limpo = (nome or "").strip() or None
    cliente = {
        "client_id": None,
        "nome": nome_limpo,
        "ja_cadastrado": False,
        "origem": (
            "nome extraído da análise (candidato — confirme)"
            if nome_limpo else None
        ),
        "confianca": "baixa" if nome_limpo else None,
    }
    return cliente, duplicados, avisos


# ── Conflito de interesses (EOAB arts. 34-35), carteira-protegido ────────────

async def analisar_conflito(
    db: AsyncSession, user: User, *,
    nome_cliente: str | None = None, parte_contraria: str | None = None,
) -> list[dict[str, Any]]:
    """Alertas de conflito com os MESMOS núcleos de matching de
    conflito_service e os MESMOS guards de carteira de preview_conversao —
    correspondência não visível colapsa em alerta protegido, sem id."""
    alertas: list[dict[str, Any]] = []

    # A parte contrária informada é cliente do escritório (grave).
    for c in await _clientes_por_nome(db, parte_contraria, limit=5):
        if await pode_ver_cliente(db, user, c):
            alertas.append({
                "tipo": "CONFLITO_parte_contraria_eh_cliente",
                "client_id": c.id, "nome": c.nome_exibicao,
                "mensagem": (
                    "A parte contrária consta como cliente do escritório — "
                    "conflito potencial grave (EOAB arts. 34-35)."
                ),
                "protegido": False,
            })
        else:
            alertas.append({
                "tipo": "conflito_cliente_protegido", "client_id": None,
                "nome": "Correspondência protegida na base do escritório",
                "mensagem": (
                    "Correspondência em carteira protegida. Solicite revisão "
                    "de conflito à gestão antes de prosseguir."
                ),
                "protegido": True,
            })

    # O cliente candidato figura como PARTE CONTRÁRIA em caso do escritório.
    for caso in await _casos_por_parte_contraria(db, nome_cliente, limit=5):
        if pode_ver_caso_resumido(user, caso):
            alertas.append({
                "tipo": "CONFLITO_cliente_e_parte_contraria",
                "case_id": caso.id, "nome": caso.parte_contraria,
                "mensagem": (
                    "O cliente informado figura como PARTE CONTRÁRIA em caso "
                    "do escritório — conflito potencial grave (EOAB art. 17/34)."
                ),
                "protegido": False,
            })
        else:
            alertas.append({
                "tipo": "conflito_caso_protegido", "case_id": None,
                "nome": "Correspondência protegida na base do escritório",
                "mensagem": (
                    "Correspondência em caso protegido. Solicite revisão de "
                    "conflito à gestão antes de prosseguir."
                ),
                "protegido": True,
            })

    # Dedup sem depender de ids protegidos (mesma chave do preview da Sala).
    unicos: list[dict[str, Any]] = []
    vistos: set[tuple[str, str, str]] = set()
    for a in alertas:
        k = (str(a.get("tipo") or ""), str(a.get("nome") or ""),
             str(a.get("mensagem") or ""))
        if k not in vistos:
            vistos.add(k)
            unicos.append(a)
    return unicos


async def casos_ativos_do_cliente(
    db: AsyncSession, user: User, client_id: str,
) -> list[dict[str, Any]]:
    """Casos ATIVOS do cliente — sinal de caso possivelmente duplicado (mesmo
    bloco de preview_conversao; protegidos colapsam numa única entrada)."""
    rows = (await db.execute(
        select(Case).where(
            Case.client_id == client_id,
            Case.deleted_at.is_(None),
            Case.status.notin_([CaseStatus.encerrado, CaseStatus.arquivado]),
        ).limit(10)
    )).scalars().all()
    ativos: list[dict[str, Any]] = []
    houve_protegido = False
    for caso in rows:
        if pode_ver_caso_resumido(user, caso):
            ativos.append({
                "id": caso.id, "titulo": caso.titulo,
                "numero_interno": caso.numero_interno, "protegido": False,
            })
        else:
            houve_protegido = True
    if houve_protegido:
        ativos.append({
            "id": None, "titulo": "Caso protegido",
            "numero_interno": None, "protegido": True,
        })
    return ativos


# ── POST /entrada/analisar — orquestração ────────────────────────────────────

async def analisar_entrada(
    db: AsyncSession, cu: User, *,
    batch: DocumentIntakeBatch,
    files: list[Any],
    texto: str | None,
) -> dict[str, Any]:
    """Roda o encadeamento da seção 4 do desenho e devolve a proposta
    (contrato { rascunho_id, cliente, area, titulo, fatos, ... }).

    Não faz o commit final — o router persiste a proposta em
    batch.resultado["entrada_unica"] e comita. Os ORIGINAIS dos arquivos são
    preservados/commitados pelo próprio pipeline da Entrada Universal antes de
    qualquer OCR/IA (nada se perde em falha posterior)."""
    settings = get_settings()
    avisos: list[str] = []
    degradado = False

    # 1) Arquivos → pipeline compartilhado da Entrada Universal.
    processados: list[dict[str, Any]] = []
    total_bytes = 0
    if files:
        from app.routers.entrada_universal import ingerir_arquivos_lote
        processados, total_bytes = await ingerir_arquivos_lote(
            db, cu, batch=batch, files=files,
            conf=DocConfidencialidade.normal,
        )

    # 2) Análise dos documentos pelo núcleo (fail-soft — nunca derruba).
    from app.services.entrada_universal_service import (
        montar_dossie, resumo_documentos,
    )
    analise_docs: dict[str, Any] = {}
    if processados:
        dossie = montar_dossie(processados, texto or None)
        if len(dossie.strip()) >= 40:
            from app.routers.entrada_universal import _analisar_ia
            analise_docs = await _analisar_ia(
                db, cu, modalidade=None, case_id=None, dossie=dossie,
                deterministico={"documentos": resumo_documentos(processados)},
            )
            if "log_id" not in analise_docs:
                degradado = True
                avisos.append(
                    "A interpretação dos documentos por IA ficou indisponível; "
                    "a classificação determinística foi preservada."
                )
        else:
            avisos.append(
                "Documentos sem texto extraível suficiente para interpretação "
                "por IA — classifique manualmente na conferência."
            )

    # 3) Relato → Entrevista Inteligente (fail-soft — nunca derruba).
    analise_texto: dict[str, Any] | None = None
    if texto and len(texto.strip()) >= 40:
        if not settings.AI_ENABLED:
            degradado = True
            avisos.append(
                "A análise por IA está indisponível (desabilitada na "
                "configuração). O relato foi preservado — preencha o que faltar."
            )
        else:
            from app.services.triagem_entrevista_service import (
                TriagemIndisponivelError, analisar_relato,
            )
            try:
                analise_texto = await analisar_relato(db, cu, texto)
            except TriagemIndisponivelError:
                degradado = True
                avisos.append(
                    "A análise do relato por IA está indisponível agora. O "
                    "relato foi preservado — preencha o que faltar."
                )

    # 4) Fusão mínima + identificação de cliente + conflito + duplicados.
    dados_pessoais = analise_docs.get("dados_pessoais") or {}
    partes = analise_docs.get("partes") or {}
    resumo_exec = analise_docs.get("resumo_executivo") or {}
    painel = (analise_texto or {}).get("analise") or {}

    def _s(v: Any, teto: int = 500) -> str | None:
        return str(v).strip()[:teto] if isinstance(v, (str, int, float)) and str(v).strip() else None

    nome_extraido = _s(dados_pessoais.get("nome"), 255)
    cliente, duplicados_clientes, avisos_cli = await identificar_cliente(
        db, cu,
        cpf=_s(dados_pessoais.get("cpf"), 32),
        cnpj=_s(dados_pessoais.get("cnpj"), 32),
        nome=nome_extraido,
    )
    avisos.extend(avisos_cli)

    parte_contraria = _s(partes.get("reu"), 255)

    area_txt = painel.get("area_direito") or {}
    if _s(area_txt.get("valor"), 50):
        area = {"valor": _s(area_txt.get("valor"), 50),
                "confianca": area_txt.get("confianca")}
    else:
        area = {"valor": _s(analise_docs.get("area"), 50), "confianca": None}

    # Fatos: o relato do advogado é a fonte primária (determinística); o
    # resumo executivo dos documentos entra como fallback (rascunho de IA).
    fatos = (texto or "").strip() or _s(resumo_exec.get("fatos"), 10_000)

    acao = _s((painel.get("possivel_acao") or {}).get("valor"), 200)
    titulo_base = acao or _s(analise_docs.get("tipo_documento_principal"), 200)
    nome_cliente = cliente.get("nome")
    if titulo_base and nome_cliente:
        titulo = f"{titulo_base} — {nome_cliente}"[:255]
    else:
        titulo = (titulo_base or nome_cliente or "Novo caso")[:255]

    proxima_acao = (
        _s(resumo_exec.get("providencia_principal"), 500)
        or (f"Avaliar cabimento de: {acao}" if acao else None)
        or PROXIMA_ACAO_DEFAULT
    )

    prazo_docs = analise_docs.get("prazo") or {}
    prazo = None
    if _s(prazo_docs.get("data_expressa"), 40) or _s(prazo_docs.get("termo_inicial"), 200):
        prazo = {
            "descricao": _s(prazo_docs.get("termo_inicial"), 500)
            or "Prazo identificado na análise dos documentos",
            "data": _s(prazo_docs.get("data_expressa"), 40),
            "origem": "análise dos documentos (IA — rascunho)",
            "requer_confirmacao_humana": True,
        }

    conflito_alertas = await analisar_conflito(
        db, cu, nome_cliente=nome_cliente, parte_contraria=parte_contraria,
    )

    documentos = [
        {
            "document_id": p["document_id"],
            "nome": p["filename"],
            "classificacao": (p.get("classification") or {}).get("nome")
            or (p.get("classification") or {}).get("tipo"),
            "confianca": (p.get("classification") or {}).get("confianca"),
        }
        for p in processados
    ]

    return {
        "rascunho_id": batch.id,
        "cliente": cliente,
        "area": {**area, "requer_confirmacao_humana": True},
        "titulo": titulo,
        "fatos": fatos,
        "parte_contraria": parte_contraria,
        "documentos": documentos,
        "prazo": prazo,
        "proxima_acao": proxima_acao,
        "conflito": {"alertas": conflito_alertas},
        "duplicados": {"clientes": duplicados_clientes},
        "degradado": degradado,
        "avisos": avisos,
        "total_bytes": total_bytes,
        "ai_log_ids": [
            v for v in (
                analise_docs.get("log_id"),
                (analise_texto or {}).get("ai_log_id"),
            ) if v
        ],
        "revisao_obrigatoria": True,
        "aviso": AVISO_HITL,
    }


# ── POST /entrada/{rascunho_id}/criar-caso — UMA transação ───────────────────

async def criar_caso_do_rascunho(
    db: AsyncSession, user: User, rascunho_id: str, payload,
) -> dict[str, Any]:
    """Cria Cliente (se novo) → Caso (aberto, G1) → vincula documentos →
    Prazo → CaseMovimento → AuditLog, tudo NA MESMA transação (commit é do
    router — falha em qualquer passo desfaz o conjunto).

    Gates de servidor (paridade com legal_chat_service.converter_em_caso):
    conflito/duplicado detectado sem reconhecimento → 409; responsável precisa
    ser advogado ativo → 422; client_id de carteira alheia → 404 uniforme.
    Idempotência: lock pessimista do batch; batch já convertido devolve
    {case_id, ja_convertido: true} sem criar nada."""
    # Lock pessimista + recheck (mesmo padrão de converter_em_caso): dois
    # cliques no botão não criam dois casos — o segundo espera o lock e cai
    # na idempotência.
    res = await db.execute(
        select(DocumentIntakeBatch)
        .where(DocumentIntakeBatch.id == rascunho_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    batch = res.scalar_one_or_none()
    if batch is None:
        raise HTTPException(404, "Rascunho de entrada não encontrado")
    if not is_gestao(user) and batch.created_by != user.id:
        raise HTTPException(403, "Sem permissão para este rascunho")
    if not (batch.resultado or {}).get("entrada_unica"):
        raise HTTPException(409, "O lote informado não é um rascunho da Entrada Única")
    if batch.case_id:
        return {"case_id": batch.case_id, "ja_convertido": True}

    if payload.area not in {a.value for a in CaseArea}:
        raise HTTPException(422, "Área do caso inválida")

    # Responsável: usuário ativo com piso de advogado (422 — nunca
    # IntegrityError/atribuição a terceiro arbitrário).
    responsavel = await db.get(User, payload.advogado_responsavel_id)
    if (
        responsavel is None
        or not getattr(responsavel, "is_active", True)
        or ROLE_LEVEL.get(_role(responsavel), 0) < ROLE_LEVEL["advogado"]
    ):
        raise HTTPException(
            422, "Responsável inválido: informe um advogado ativo do escritório"
        )

    # Cliente: existente (gate canônico de carteira → 404 uniforme) ou novo.
    client: Client | None = None
    if payload.cliente.client_id:
        client = await obter_cliente_autorizado(db, user, payload.cliente.client_id)
        nome_cliente = client.nome_exibicao
    else:
        nome_cliente = payload.cliente.novo_nome

    # Gate de conflito de interesses (EOAB): achado sem reconhecimento → 409.
    alertas = await analisar_conflito(
        db, user, nome_cliente=nome_cliente,
        parte_contraria=payload.parte_contraria,
    )
    if alertas and not payload.conflict_confirmed:
        raise HTTPException(409, {
            "mensagem": ("Há alertas de conflito de interesses; revise os "
                         "achados e confirme antes de criar o caso."),
            "alertas_conflito": alertas,
        })

    # Gate de duplicidade: cliente novo com homônimo OU cliente existente com
    # caso ativo → 409 sem duplicate_confirmed (paridade converter_em_caso).
    if payload.cliente.novo_nome and not payload.duplicate_confirmed:
        duplicados = []
        houve_protegido = False
        for c in await _clientes_por_nome(db, payload.cliente.novo_nome):
            if await pode_ver_cliente(db, user, c):
                duplicados.append({"id": c.id, "nome": c.nome_exibicao, "protegido": False})
            else:
                houve_protegido = True
        if houve_protegido:
            duplicados.append({
                "id": None, "nome": "Cliente protegido na base do escritório",
                "protegido": True,
            })
        if duplicados:
            raise HTTPException(409, {
                "mensagem": ("Há cliente possivelmente duplicado; selecione o "
                             "existente ou confirme a criação."),
                "clientes_possivelmente_duplicados": duplicados,
            })
    if payload.cliente.client_id and not payload.duplicate_confirmed:
        ativos = await casos_ativos_do_cliente(db, user, payload.cliente.client_id)
        if ativos:
            raise HTTPException(409, {
                "mensagem": ("O cliente possui caso ativo; confirme que não se "
                             "trata de caso duplicado antes de criar outro."),
                "casos_ativos_do_cliente": ativos,
            })

    # documentos_ids ⊆ documentos do próprio batch — impede vincular documento
    # alheio por id arbitrário (422).
    documentos_ids = list(dict.fromkeys(payload.documentos_ids or []))
    if documentos_ids:
        permitidos = set((await db.execute(
            select(DocumentIntakeItem.document_id)
            .where(DocumentIntakeItem.batch_id == batch.id)
        )).scalars().all())
        estranhos = [i for i in documentos_ids if i not in permitidos]
        if estranhos:
            raise HTTPException(
                422, "documentos_ids contém documento que não pertence a este rascunho"
            )

    # ── Criação transacional (commit único pelo chamador) ────────────────────
    if client is None:
        client = Client(
            id=str(uuid4()),
            nome=payload.cliente.novo_nome,
            responsavel_id=payload.advogado_responsavel_id,
        )
        db.add(client)
        await db.flush()

    numero = await proximo_numero_interno(db)
    case = Case(
        id=str(uuid4()),
        numero_interno=numero,
        titulo=payload.titulo,
        area=CaseArea(payload.area),
        status=CaseStatus.aberto,
        descricao_fatos=payload.fatos,
        parte_contraria=payload.parte_contraria,
        client_id=client.id,
        advogado_responsavel_id=payload.advogado_responsavel_id,
        # G1: caso nunca nasce sem "o que fazer agora".
        proxima_acao=payload.proxima_acao or PROXIMA_ACAO_DEFAULT,
    )
    db.add(case)
    await db.flush()

    # Documento anexado é documento vinculado — NA MESMA transação do caso
    # (a classe de defeito "gravação não transacional" do CLAUDE.md).
    documentos_vinculados = 0
    if documentos_ids:
        docs = (await db.execute(
            select(Document).where(
                Document.id.in_(documentos_ids),
                Document.deleted_at.is_(None),
            )
        )).scalars().all()
        if len(docs) != len(documentos_ids):
            raise HTTPException(422, "documentos_ids contém documento inexistente ou excluído")
        for doc in docs:
            if doc.case_id and doc.case_id != case.id:
                raise HTTPException(
                    422, "documentos_ids contém documento já vinculado a outro caso"
                )
            doc.case_id = case.id
            doc.client_id = client.id
        documentos_vinculados = len(docs)

    deadline_id: str | None = None
    if payload.prazo is not None:
        prazo = Deadline(
            id=str(uuid4()),
            titulo=payload.prazo.titulo,
            descricao=payload.prazo.descricao,
            data_prazo=payload.prazo.data,
            case_id=case.id,
            responsavel_id=payload.prazo.responsavel_id or payload.advogado_responsavel_id,
            origem="entrada_unica",
        )
        db.add(prazo)
        deadline_id = prazo.id

    db.add(CaseMovimento(
        id=str(uuid4()), case_id=case.id, tipo="nota",
        descricao=(
            f"Caso criado pela Entrada Única (rascunho {batch.id}) — proposta "
            "da análise revisada e confirmada pelo advogado."
        ),
        created_by=user.id,
    ))

    # Transição automática (Bloco 3): documentos vinculados na criação ⇒
    # em_instrucao — MESMA transação (falha aqui aborta o conjunto; não se
    # engole IntegrityError dentro da transação).
    if documentos_vinculados:
        await avancar_status_por_evento(
            db, case, "documento_vinculado", user_id=user.id
        )

    await criar_audit_log(
        db, user.id, _role(user), "ENTRADA_UNICA_CRIAR_CASO", "cases", case.id,
        detalhes=(
            f"rascunho {batch.id}; documentos {documentos_vinculados}; "
            f"prazo {deadline_id or '-'}; numero {numero}"
        ),
    )

    # Idempotência: o rascunho aponta para o caso criado.
    batch.case_id = case.id
    batch.client_id = client.id

    return {
        "case_id": case.id,
        "numero_interno": numero,
        "client_id": client.id,
        "documentos_vinculados": documentos_vinculados,
        "deadline_id": deadline_id,
        "status": case.status.value if isinstance(case.status, CaseStatus) else str(case.status),
        "ja_convertido": False,
    }
