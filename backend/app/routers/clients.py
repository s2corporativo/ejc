# ── app/routers/clients.py ───────────────────────────────────────────────────
# CRM de clientes + VERIFICAÇÃO DE CONFLITO DE INTERESSES (OAB obrigatório)
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func as sqlfunc
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel  # noqa: E402 (module-level p/ _ResolverClienteReq)

from app.core.client_ownership import (
    ids_clientes_visiveis,
    pode_ver_cliente as _pode_ver_cliente_canonico,
    visao_total_clientes,
)
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.models.client import Client, ClientStatus
from app.models.case import Case, CaseStatus
from app.models.audit_log import criar_audit_log
from app.schemas.client import (
    ClientCreate, ClientUpdate, ClientResponse, ConflitoCheckRequest,
)
from app.schemas.common import MsgResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clients", tags=["Clientes / CRM"])

# Gestão de clientes conforme a matriz de permissões (inclui secretaria; exclui
# estagiario/advogado_auxiliar/financeiro de escrita). Leitura segue autenticada.
_CLIENTES = {"superadmin", "admin", "socio", "advogado", "secretaria"}


def _req_clientes(cu: User = Depends(get_current_user)) -> User:
    if cu.role.value not in _CLIENTES:
        raise HTTPException(status_code=403, detail="Sem permissão para gerenciar clientes")
    return cu


def _req_clientes_leitura(cu: User = Depends(get_current_user)) -> User:
    """Leitura integral do CRM limitada aos perfis definidos na matriz _CLIENTES."""
    if cu.role.value not in _CLIENTES:
        raise HTTPException(status_code=403, detail="Sem permissão para consultar clientes")
    return cu


def _filtro_visibilidade_cliente(q, cu: User):
    """Segregação de titularidade de clientes (sigilo interno — LGPD/EOAB).

    Delega ao gate canônico (app.core.client_ownership) — achado da auditoria:
    esta função reimplementava em ORM a mesma regra que já existe em
    client_ownership.ids_clientes_visiveis/visao_total_clientes, e as cópias
    já haviam divergido (secretaria com visão total aqui, mas não nos
    sub-recursos de cliente). Mantida como wrapper, com o mesmo nome, para não
    tocar nos call sites.

      - Gestão (socio/admin/superadmin) e a recepção (secretaria) veem TODA a
        base — necessidade operacional do CRM/funil.
      - advogado/advogado_auxiliar veem apenas clientes vinculados a si:
          • cujo responsavel_id é o próprio usuário; OU
          • que possuem ao menos um caso NÃO excluído em que ele é advogado
            responsável ou auxiliar.

    NÃO deve ser aplicado ao endpoint /checar-conflito (nem a detectar_conflito),
    que por dever ético (EOAB arts. 34-35) precisa cruzar a base inteira.
    """
    if visao_total_clientes(cu):
        return q
    return q.where(Client.id.in_(ids_clientes_visiveis(cu)))


async def _pode_ver_cliente(cu: User, client: Client, db: AsyncSession) -> bool:
    """Titularidade (sigilo interno) para UM cliente já carregado.

    Delega ao gate canônico (app.core.client_ownership.pode_ver_cliente) —
    mesmo racional de _filtro_visibilidade_cliente acima. Versão row-level,
    aplicada às rotas de detalhe (GET /{id}, /ia-analise) e ao find-or-create
    (/resolver), que operam sobre um único registro e não passam pelo filtro
    da query da listagem.

    NÃO deve ser usado nos endpoints de conflito de interesses, que por dever
    ético (EOAB arts. 34-35) precisam cruzar a base inteira.
    """
    return await _pode_ver_cliente_canonico(db, cu, client)


class _ResolverClienteReq(BaseModel):
    nome: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None


@router.post("/resolver")
async def resolver_cliente(
    req: _ResolverClienteReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    """Find-or-create de cliente por CPF/CNPJ (idempotente) — usado pela
    importacao inteligente de documentos. Dedup evita violar UNIQUE(cpf/cnpj).
    Cliente criado fica marcado para revisao (OAB)."""
    import re as _re
    from app.models.client import ClientTipo, ClientStatus, ClientOrigem
    from app.services.pii_crypto import encrypt as _pii_encrypt, hash_documento as _pii_hash
    cpf = (_re.sub(r"\D", "", req.cpf) if req.cpf else "")[:11] or None
    cnpj = (_re.sub(r"\D", "", req.cnpj) if req.cnpj else "")[:14] or None
    nome = (req.nome or "").strip()[:255]

    # Dedup por ÍNDICE CEGO (cutover C6/LGPD): não há mais coluna cpf/cnpj em
    # texto puro para comparar — casa pelo hash HMAC do documento normalizado.
    existente = None
    if cpf:
        existente = (await db.execute(
            select(Client).where(Client.cpf_hash == _pii_hash(cpf),
                                 Client.deleted_at.is_(None))
        )).scalar_one_or_none()
    if not existente and cnpj:
        existente = (await db.execute(
            select(Client).where(Client.cnpj_hash == _pii_hash(cnpj),
                                 Client.deleted_at.is_(None))
        )).scalar_one_or_none()
    if existente:
        # Sigilo interno (LGPD/EOAB): não vazar id/nome de cliente de OUTRA
        # carteira. Sem esta checagem, um advogado reconstrói a base alheia
        # enumerando CPF/CNPJ (CPF/CNPJ → id + nome). Responde como "não
        # encontrado" (mesmo shape do 404 dos demais endpoints) e não cria
        # duplicata. Não incide sobre conflito de interesses (endpoint próprio).
        if not await _pode_ver_cliente(cu, existente, db):
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        return {"id": existente.id, "nome": existente.nome_exibicao, "criado": False}

    if not (nome or cpf or cnpj):
        raise HTTPException(status_code=422, detail="Sem dados para identificar o cliente")

    tipo = ClientTipo.PJ if cnpj else ClientTipo.PF
    novo = Client(
        id=str(uuid4()),
        tipo=tipo,
        nome=nome if tipo == ClientTipo.PF else None,
        razao_social=nome if tipo == ClientTipo.PJ else None,
        # Cutover C6/LGPD: grava SOMENTE cifrado + hash (sem texto puro). cpf/cnpj
        # aqui já chegam normalizados (regex \D acima).
        cpf_enc=_pii_encrypt(cpf) if tipo == ClientTipo.PF else None,
        cnpj_enc=_pii_encrypt(cnpj) if tipo == ClientTipo.PJ else None,
        cpf_hash=_pii_hash(cpf) if tipo == ClientTipo.PF else None,
        cnpj_hash=_pii_hash(cnpj) if tipo == ClientTipo.PJ else None,
        status=ClientStatus.ativo,
        origem=ClientOrigem.escritorio,
        responsavel_id=cu.id,
        observacoes="Criado automaticamente pela importacao inteligente — revisar dados (OAB).",
    )
    db.add(novo)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE_AUTO", "clients", novo.id,
                          detalhes=f"import inteligente: {nome or cpf or cnpj}")
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="CPF/CNPJ já cadastrado")
    return {"id": novo.id, "nome": novo.nome_exibicao, "criado": True}


# Rate limit + máscara de documento: mesma mitigação de /checar-conflito
# (PR #528) — este endpoint TAMBÉM cruza a base inteira por dever ético e
# devolvia CPF/CNPJ em claro sem throttle (achado da auditoria: permitia
# reconstruir a carteira alheia com documento completo, em massa).
@router.post("/verificar-conflito",
             dependencies=[Depends(rate_limit("verificar-conflito", 10))])
async def verificar_conflito(
    req: ConflitoCheckRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    """
    Verificação OBRIGATÓRIA antes de cadastrar cliente/caso (EOAB arts. 34-35).
    Busca: nome/CPF/CNPJ como cliente existente E como parte contrária.
    """
    # Lógica extraída para conflito_service (reutilizada no cadastro).
    from app.services.conflito_service import detectar_conflito
    from app.services.pii_crypto import mascarar_documento

    resultado = await detectar_conflito(
        db, nome=req.nome, cpf=req.cpf, cnpj=req.cnpj,
        parte_contraria=req.parte_contraria,
    )
    # PII: mascara o documento nos achados — mesmo racional de /checar-conflito
    # (clients.py). Quem precisa do documento completo abre a ficha do cliente,
    # onde o gate de titularidade se aplica normalmente.
    achados = [
        {**a, "documento": mascarar_documento(a["documento"])}
        if "documento" in a else a
        for a in resultado["achados"]
    ]
    classificacao = resultado["classificacao"]
    conflito_grave = resultado["bloqueio"]

    # Audit obrigatório (proteção OAB)
    await criar_audit_log(
        db, cu.id, cu.role.value, "CONFLITO_CHECK", "clients",
        detalhes=f"{classificacao}: {len(achados)} achado(s)",
    )
    await db.commit()

    return {
        "classificacao": classificacao,
        "achados": achados,
        "bloqueio": conflito_grave,
        "orientacao": (
            "⛔ Conflito identificado — caso só pode prosseguir com aprovação de sócio"
            if conflito_grave else
            "⚠️ Verifique os achados antes de prosseguir"
            if achados else
            "✅ Nenhum conflito encontrado"
        ),
    }


# Casos considerados "ativos" (representação em curso) para fins de conflito.
# Derivado do CaseStatus vigente — não hardcoded — para não envelhecer quando
# o enum mudar (achado da auditoria: a versão anterior listava status extintos
# pela migration 126 e o alerta ético nunca atingia nível "crítico").
# encerrado/arquivado NÃO contam como conflito crítico.
_STATUS_ATIVOS = {s.value for s in CaseStatus} - {
    CaseStatus.encerrado.value, CaseStatus.arquivado.value,
}


# Rate limit também mitiga enumeração de CPF/CNPJ via tentativas em massa.
@router.post("/checar-conflito",
             dependencies=[Depends(rate_limit("checar-conflito", 10))])
async def checar_conflito(
    req: ConflitoCheckRequest,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    """
    Checagem de conflito de interesses em tempo real no intake (EOAB arts. 34-35).

    Cruza CPF/CNPJ (busca via índice cego HMAC) e nome contra:
      • clientes existentes (clients.cpf_hash / cnpj_hash);
      • partes de casos (case_partes) e parte contrária livre (cases).

    Resposta enxuta p/ intake: {conflito, nivel, matches}. Fail-safe — nunca
    levanta exceção de regra de negócio. Crítico = mesma pessoa como parte em
    caso ATIVO / parte contrária que já é nosso cliente.

    PII: o NOME sai completo — é o dever ético (o advogado precisa saber com
    quem é o conflito, e sem o nome o alerta é inacionável). O CPF/CNPJ sai
    apenas MASCARADO (`documento_mascarado`). Este endpoint (e /verificar-
    conflito, mesmo racional) cruza a base inteira ignorando a segregação de
    carteira, então devolver documento em claro entregaria PII de cliente de
    outro advogado a quem não tem titularidade. Quem precisa do documento
    completo abre a ficha do cliente —
    lá o gate de titularidade se aplica normalmente.
    """
    from app.services.conflito_service import _padrao_like, detectar_conflito
    from app.services.pii_crypto import mascarar_documento, normalizar_documento
    from app.models.case_parte import CaseParte

    matches: list[dict] = []
    nivel = "nenhum"

    def _elevar(novo: str):
        nonlocal nivel
        ordem = {"nenhum": 0, "atencao": 1, "critico": 2}
        if ordem[novo] > ordem[nivel]:
            nivel = novo

    # ── 1. Reutiliza detectar_conflito (clients por hash + parte contrária) ──
    resultado = await detectar_conflito(
        db, nome=req.nome, cpf=req.cpf, cnpj=req.cnpj,
        parte_contraria=req.parte_contraria,
    )
    for a in resultado["achados"]:
        tipo = a["tipo"]
        if tipo == "cliente_existente":
            matches.append({
                "tipo": "cliente_existente",
                "papel": "cliente",
                "client_id": a.get("id"),
                "nome": a.get("nome"),
                "documento_mascarado": mascarar_documento(a.get("documento")),
                "descricao": f"Já cadastrado como cliente ({a.get('nome') or 'N/D'}).",
            })
            _elevar("atencao")
        elif tipo == "parte_contraria_em_caso":
            matches.append({
                "tipo": "parte_contraria_em_caso",
                "case_id": a.get("case_id"),
                "papel": "parte_contraria",
                "nome": a.get("parte"),
                "descricao": (
                    f"Consta como parte contrária no caso "
                    f"\"{a.get('titulo') or a.get('case_id')}\"."
                ),
            })
            _elevar("atencao")
        elif "CONFLITO" in tipo:  # parte contrária informada já é nosso cliente
            matches.append({
                "tipo": "parte_contraria_eh_cliente",
                "papel": "parte_contraria",
                "client_id": a.get("id"),
                "nome": a.get("nome"),
                "documento_mascarado": mascarar_documento(a.get("documento")),
                "descricao": (
                    f"A parte contrária informada já é cliente do escritório "
                    f"({a.get('nome') or 'N/D'}) — representação vedada (EOAB art. 34, XVII)."
                ),
            })
            _elevar("critico")

    # ── 2. case_partes: pessoa já é parte em algum caso? (status-aware) ──────
    # cpf_cnpj em case_partes é texto (pode vir formatado) → compara normalizado.
    cpf_norm = normalizar_documento(req.cpf)
    cnpj_norm = normalizar_documento(req.cnpj)
    doc_norm = cpf_norm or cnpj_norm

    conds = []
    if doc_norm:
        norm_expr = sqlfunc.replace(
            sqlfunc.replace(
                sqlfunc.replace(
                    sqlfunc.replace(CaseParte.cpf_cnpj, ".", ""),
                    "-", ""),
                "/", ""),
            " ", "")
        conds.append(norm_expr == doc_norm)
    if req.nome and len(req.nome.strip()) >= 4:
        # Wildcards do input escapados (mesmo helper de conflito_service e
        # raio_x_service) — sem isto, "____" casa qualquer nome com 4+
        # caracteres e contorna o piso de 4 chars (achado da auditoria).
        conds.append(CaseParte.nome.ilike(_padrao_like(req.nome.strip()), escape="\\"))

    if conds:
        q = (
            select(CaseParte, Case.status, Case.titulo)
            .join(Case, Case.id == CaseParte.case_id)
            .where(or_(*conds), Case.deleted_at.is_(None))
            .limit(20)
        )
        for parte, status, titulo in (await db.execute(q)).all():
            status_val = status.value if hasattr(status, "value") else str(status)
            ativo = status_val in _STATUS_ATIVOS
            papel = parte.papel_processual or parte.tipo or "parte"
            if ativo:
                matches.append({
                    "tipo": "parte_em_caso_ativo",
                    "case_id": parte.case_id,
                    "papel": papel,
                    "nome": parte.nome,
                    "documento_mascarado": mascarar_documento(parte.cpf_cnpj),
                    "descricao": (
                        f"{parte.nome} já figura como '{papel}' no caso ATIVO "
                        f"\"{titulo}\" (conflito potencial — EOAB arts. 34-35)."
                    ),
                })
                _elevar("critico")
            else:
                matches.append({
                    "tipo": "parte_em_caso_encerrado",
                    "case_id": parte.case_id,
                    "papel": papel,
                    "nome": parte.nome,
                    "documento_mascarado": mascarar_documento(parte.cpf_cnpj),
                    "descricao": (
                        f"{parte.nome} figurou como '{papel}' no caso já "
                        f"encerrado/arquivado \"{titulo}\"."
                    ),
                })
                _elevar("atencao")

    # ── 3. Audit obrigatório (proteção OAB) — fail-safe ─────────────────────
    try:
        await criar_audit_log(
            db, cu.id, cu.role.value, "CONFLITO_CHECK", "clients",
            detalhes=f"intake checar-conflito: nivel={nivel}, {len(matches)} match(es)",
        )
        await db.commit()
    except Exception:
        await db.rollback()

    return {
        "conflito": nivel != "nenhum",
        "nivel": nivel,
        "matches": matches,
    }


@router.get("/")
async def listar(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None, status_f: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes_leitura),
):
    q = select(Client).where(Client.deleted_at.is_(None))
    # Segregação de titularidade (sigilo interno): advogado/adv_auxiliar só veem
    # a própria carteira. Aplicado ANTES da busca — assim o filtro por documento
    # (CPF/CNPJ) também fica restrito e não permite descobrir cliente alheio.
    q = _filtro_visibilidade_cliente(q, cu)
    if search:
        # Busca parcial (ILIKE) só por nome/razão social. Cutover C6/LGPD: a
        # busca parcial por CPF/CNPJ foi REMOVIDA — sem plaintext no banco, o
        # ILIKE por documento é impossível por natureza (cifra real ≠ substring).
        # Documento agora casa APENAS por igualdade exata via índice cego (HMAC):
        # o termo precisa ser um CPF (11) ou CNPJ (14) completo. O hash é
        # normalizado (só dígitos), então "123.456.789-09" e "12345678909"
        # convergem — preservando o dedup do Novo Caso.
        condicoes = [
            Client.nome.ilike(f"%{search}%"),
            Client.razao_social.ilike(f"%{search}%"),
        ]
        from app.services.pii_crypto import normalizar_documento, hash_documento
        dig = normalizar_documento(search)
        if dig and len(dig) == 11:
            condicoes.append(Client.cpf_hash == hash_documento(dig))
        elif dig and len(dig) == 14:
            condicoes.append(Client.cnpj_hash == hash_documento(dig))
        q = q.where(or_(*condicoes))
    if status_f:
        # Valor fora do enum estourava DataError→500 no bind (achado da
        # auditoria; vocabulário de status é fonte recorrente de armadilha
        # neste sistema). 422 explícito, mesmo padrão dos schemas do módulo.
        if status_f not in {s.value for s in ClientStatus}:
            raise HTTPException(
                status_code=422,
                detail=f"status inválido; use um de: "
                       f"{sorted(s.value for s in ClientStatus)}",
            )
        q = q.where(Client.status == status_f)
    q = q.order_by(Client.created_at.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery())
    )).scalar()
    rows = (await db.execute(
        q.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "data": [ClientResponse.model_validate(c) for c in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("/", response_model=ClientResponse, status_code=201)
async def criar(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    # Validação básica PF/PJ
    if payload.tipo == "PF" and not payload.nome:
        raise HTTPException(status_code=422, detail="PF requer nome")
    if payload.tipo == "PJ" and not payload.razao_social:
        raise HTTPException(status_code=422, detail="PJ requer razão social")

    # Validação matemática (dígito verificador) — evita cadastros com erro
    from app.services.validators_service import validar_cpf as _vcpf, validar_cnpj as _vcnpj
    if payload.cpf and not _vcpf(payload.cpf):
        raise HTTPException(status_code=422, detail="CPF inválido (dígito verificador)")
    if payload.cnpj and not _vcnpj(payload.cnpj):
        raise HTTPException(status_code=422, detail="CNPJ inválido (dígito verificador)")

    # Detecção de conflito (EOAB arts. 34-35) — NÃO bloqueia o cadastro
    # (resultado = alerta; decisão humana obrigatória), mas registra em
    # audit_logs para rastreabilidade ética.
    from app.services.conflito_service import detectar_conflito
    conflito = await detectar_conflito(
        db, nome=payload.nome or payload.razao_social,
        cpf=payload.cpf, cnpj=payload.cnpj,
    )

    # Cutover C6/LGPD: cpf/cnpj deixaram de ser colunas do model. Extrai os
    # valores do payload e persiste SOMENTE cifrado (cpf_enc/cnpj_enc) + índice
    # cego (cpf_hash/cnpj_hash) — nunca em texto puro.
    dados = payload.model_dump()
    cpf_in = dados.pop("cpf", None)
    cnpj_in = dados.pop("cnpj", None)
    c = Client(
        id=str(uuid4()), responsavel_id=cu.id,
        **dados,
    )
    # CRM: lead entra no funil sempre com etapa preenchida — o board agrupa
    # por etapa_funil e o GET /clients/?status=lead precisa devolvê-la.
    if c.status == ClientStatus.lead.value and not c.etapa_funil:
        c.etapa_funil = "lead"
    from app.services.pii_crypto import normalizar_documento, encrypt as _pii_encrypt, hash_documento as _pii_hash
    cpf_norm = normalizar_documento(cpf_in)
    cnpj_norm = normalizar_documento(cnpj_in)
    c.cpf_enc = _pii_encrypt(cpf_norm)
    c.cnpj_enc = _pii_encrypt(cnpj_norm)
    c.cpf_hash = _pii_hash(cpf_norm)
    c.cnpj_hash = _pii_hash(cnpj_norm)
    db.add(c)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "clients", c.id)
    if conflito["classificacao"] != "SEM_CONFLITO":
        await criar_audit_log(
            db, cu.id, cu.role.value, "CONFLITO_CHECK", "clients", c.id,
            detalhes=(
                f"{conflito['classificacao']} no cadastro: "
                f"{len(conflito['achados'])} achado(s)"
            ),
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="CPF/CNPJ já cadastrado")
    except ValueError as e:
        # ValueError é controlado pelo código (mensagem limpa de validação).
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")
    except DataError:
        # DataError do driver carrega o statement SQL e nomes de coluna — NÃO ecoar
        # (disclosure de esquema). Loga server-side e devolve mensagem genérica.
        await db.rollback()
        logger.warning("DataError ao gravar cliente (valor fora do tipo/tamanho da coluna)", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="Dados inválidos — verifique o formato/tamanho dos campos (datas, textos longos, etc.).",
        )
    await db.refresh(c)
    return c


@router.get("/{client_id}", response_model=ClientResponse)
async def detalhe(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes_leitura),
):
    c = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    # Sigilo interno (LGPD/EOAB): advogado/adv_auxiliar só acessa a própria
    # carteira. 404 (não vaza existência) — espelha _filtro_visibilidade_cliente
    # da listagem, evitando reconstrução da base alheia por id direto.
    if not await _pode_ver_cliente(cu, c, db):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return c

@router.post("/{client_id}/ia-analise")
async def ia_analise_cliente(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    """
    ABA 6 – IA do Cliente: Análise completa do histórico (Seção 2.113).
    """
    from app.core.ai_brain import ai_gateway
    from app.models.case import Case
    from app.models.fee import Fee

    c = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    # Sigilo interno (LGPD/EOAB): a IA agrega histórico completo (casos +
    # financeiro) do cliente — só a própria carteira. 404 (não vaza existência).
    if not await _pode_ver_cliente(cu, c, db):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    casos = (await db.execute(select(Case).where(Case.client_id == client_id))).scalars().all()
    financeiro = (await db.execute(select(Fee).where(Fee.client_id == client_id))).scalars().all()

    contexto = f"Cliente: {c.nome_exibicao}\nTipo: {c.tipo}\n"
    contexto += f"Casos: {len(casos)}\n"
    contexto += f"Histórico Financeiro: {len(financeiro)} registros.\n"

    # LGPD: sanitiza PII (nome do cliente, CPF/CNPJ etc.) antes de enviar à IA —
    # mesmo padrão dos demais endpoints de IA (cases.py assistente-estrategico).
    from app.services.sanitizer import sanitizar_pii
    contexto, pii_ctx = sanitizar_pii(contexto, [c.nome_exibicao] if c.nome_exibicao else None)

    demanda = "Faça uma análise estratégica completa do perfil deste cliente, identificando riscos, oportunidades e padrão de litígios."

    res = await ai_gateway.processar_demanda(demanda, contexto, tipo="juridico_profundo")

    # Auditoria obrigatória (LGPD/OAB): rastro em ai_logs para toda chamada de IA.
    # Este endpoint passava pelo shim legado sem gravar AILog (furo #4a). ADITIVO:
    # não altera a resposta. Análise é de PERFIL DO CLIENTE, não de um caso →
    # tipo_uso=outro (analise_caso é "sugestão de teses" no dashboard de
    # governança) e case_id=None (AILog.case_id é nullable). Loga só em sucesso;
    # erro de gravação PROPAGA (registrar_ai_log), consistente com os já auditados.
    if res.get("status") == "sucesso":
        from app.services.ai_guard import registrar_ai_log
        from app.models.ai_log import AITipoUso
        await registrar_ai_log(
            db, user_id=cu.id, tipo_uso=AITipoUso.outro, case_id=None,
            prompt_sanitizado=f"{contexto}\n\n[DEMANDA]\n{demanda}",
            pii_removida=bool(pii_ctx),
            resposta=res.get("resposta"),
            modelo=res.get("modelo_utilizado"),
        )
    return res


@router.patch("/{client_id}", response_model=ClientResponse)
async def atualizar(
    client_id: str, payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_clientes),
):
    c = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    # Sigilo interno (LGPD/EOAB): a ESCRITA precisa do mesmo gate de carteira que
    # a leitura (detalhe/ia_analise) — sem ele, advogado/adv_auxiliar editaria
    # (inclusive regravaria CPF/CNPJ cifrado) cliente que sequer pode LER. 404
    # (não vaza existência). Fecha write-IDOR residual do commit 1c7285d.
    if not await _pode_ver_cliente(cu, c, db):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    mudancas = payload.model_dump(exclude_unset=True)

    # Cutover C6/LGPD: cpf/cnpj não são mais colunas do model. Extrai antes do
    # setattr genérico e regrava SOMENTE cifrado + hash do campo alterado.
    cpf_alterado = "cpf" in mudancas
    cnpj_alterado = "cnpj" in mudancas
    cpf_in = mudancas.pop("cpf", None)
    cnpj_in = mudancas.pop("cnpj", None)

    # Se CPF/CNPJ mudou: revalida dígito verificador antes de cifrar.
    if cpf_alterado or cnpj_alterado:
        from app.services.validators_service import validar_cpf as _vcpf, validar_cnpj as _vcnpj
        if cpf_in and not _vcpf(cpf_in):
            raise HTTPException(status_code=422, detail="CPF inválido (dígito verificador)")
        if cnpj_in and not _vcnpj(cnpj_in):
            raise HTTPException(status_code=422, detail="CNPJ inválido (dígito verificador)")

    for k, v in mudancas.items():
        setattr(c, k, v)

    if cpf_alterado or cnpj_alterado:
        from app.services.pii_crypto import normalizar_documento, encrypt as _pii_encrypt, hash_documento as _pii_hash
        if cpf_alterado:
            cpf_norm = normalizar_documento(cpf_in)
            c.cpf_enc = _pii_encrypt(cpf_norm)
            c.cpf_hash = _pii_hash(cpf_norm)
        if cnpj_alterado:
            cnpj_norm = normalizar_documento(cnpj_in)
            c.cnpj_enc = _pii_encrypt(cnpj_norm)
            c.cnpj_hash = _pii_hash(cnpj_norm)

    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", "clients", client_id)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="CPF/CNPJ já cadastrado")
    except ValueError as e:
        # ValueError é controlado pelo código (mensagem limpa de validação).
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {e}")
    except DataError:
        # DataError do driver carrega o statement SQL e nomes de coluna — NÃO ecoar
        # (disclosure de esquema). Loga server-side e devolve mensagem genérica.
        await db.rollback()
        logger.warning("DataError ao gravar cliente (valor fora do tipo/tamanho da coluna)", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail="Dados inválidos — verifique o formato/tamanho dos campos (datas, textos longos, etc.).",
        )
    await db.refresh(c)
    return c


@router.delete("/{client_id}", response_model=MsgResponse)
async def remover(
    client_id: str,
    forcar: bool = Query(
        False, description="Confirma exclusão mesmo com caso em representação ativa"),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["admin", "socio"])),
):
    c = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Mesmo bloqueio da anonimização LGPD (art. 17): cliente em representação
    # ativa não deve ser removido sem decisão explícita — o escritório tem
    # dever profissional de identificar o cliente enquanto atua por ele.
    # forcar=true prossegue e fica registrado na auditoria (achado da
    # auditoria: a exclusão não verificava dependências, diferente da
    # anonimização que já faz essa checagem).
    from app.services.client_anonimizacao import verificar_bloqueios
    bloqueios = await verificar_bloqueios(db, client_id)
    if bloqueios and not forcar:
        raise HTTPException(status_code=409, detail={
            "mensagem": "Exclusão bloqueada — resolva as pendências ou "
                        "confirme com forcar=true (decisão registrada em auditoria).",
            "bloqueios": bloqueios,
        })

    c.deleted_at = datetime.now(timezone.utc)

    # Desativa login do Portal vinculado — sem isto, o cliente "removido"
    # continuava acessando casos/documentos/financeiro via /portal (achado da
    # auditoria: diferente da anonimização LGPD, que já desativa o portal).
    usuarios_portal = (await db.execute(
        select(User).where(User.client_id == client_id, User.is_active.is_(True))
    )).scalars().all()
    for u in usuarios_portal:
        u.is_active = False

    detalhes = "Cliente removido (soft delete)."
    if bloqueios:
        detalhes += f" FORÇADO apesar de {len(bloqueios)} bloqueio(s) ativo(s)."
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", "clients",
                          client_id, detalhes=detalhes)
    await db.commit()
    return MsgResponse(detail="Cliente removido")


# ═══ Validação de documentos + Acesso ao Portal + Relatório LGPD ═══
from pydantic import BaseModel as _BM, EmailStr as _Email, Field as _Field
from app.core.security import get_password_hash
from app.services.security_service import validar_forca_senha
from app.models.user import User as _User, UserRole as _Role
from fastapi.responses import Response as _Resp


class CriarAcessoReq(_BM):
    email: _Email
    senha_inicial: str = _Field(min_length=8)


@router.post("/{client_id}/criar-acesso", status_code=201)
async def criar_acesso_portal(
    client_id: str, payload: CriarAcessoReq,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio", "advogado"])),
):
    """Cria login do Portal do Cliente vinculado a este cliente."""
    c = (await db.execute(select(Client).where(
        Client.id == client_id, Client.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    # Sigilo interno (A2): criar acesso ao Portal concede visão externa dos dados
    # do cliente — advogado só pode fazê-lo para a PRÓPRIA carteira (gestão passa
    # dentro do helper). 404 não vaza existência, espelhando detalhe/ia-analise.
    if not await _pode_ver_cliente(cu, c, db):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    existe = (await db.execute(select(_User).where(
        _User.email == payload.email.lower()
    ))).scalar_one_or_none()
    if existe:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado no sistema")

    # Política de senha forte também na criação de acesso ao Portal — este era o
    # último ponto de definição de senha sem validação (Field(min_length=8) só
    # garante comprimento). Mesmo padrão de users.criar: ValueError → 400.
    try:
        validar_forca_senha(payload.senha_inicial, payload.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    u = _User(
        id=str(uuid4()), email=payload.email.lower(),
        hashed_password=get_password_hash(payload.senha_inicial),
        full_name=c.nome or c.razao_social or "Cliente",
        role=_Role.cliente_externo,
        client_id=client_id,
        must_change_password=True,   # troca obrigatória no 1º acesso
        is_active=True,
    )
    db.add(u)
    # Ação destacada (A2): criação de credencial EXTERNA é evento de segurança —
    # não pode se diluir nos "CREATE" genéricos da trilha.
    await criar_audit_log(
        db, cu.id, cu.role.value, "PORTAL_ACESSO_CRIADO", "users", u.id,
        detalhes=f"Acesso ao Portal criado p/ cliente {client_id} "
                 f"(email {payload.email.lower()})",
    )
    await db.commit()
    return {
        "user_id": u.id,
        "detail": "Acesso criado. Cliente deve trocar a senha no 1º login.",
    }


@router.get("/{client_id}/relatorio-lgpd")
async def relatorio_lgpd(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """
    Relatório do titular (LGPD art. 18, II) — PDF com todos os dados
    mantidos sobre o cliente. Para atender pedidos de acesso.
    """
    from app.models.case import Case as _Case
    from app.models.document import Document as _Doc
    from app.models.fee import Fee as _Fee
    from app.models.audit_log import AuditLog as _Audit
    from app.services.pdf_service import relatorio_lgpd_pdf_async

    c = (await db.execute(select(Client).where(
        Client.id == client_id, Client.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    casos = (await db.execute(select(_Case).where(
        _Case.client_id == client_id, _Case.deleted_at.is_(None)
    ))).scalars().all()
    docs = (await db.execute(select(_Doc).where(
        _Doc.client_id == client_id, _Doc.deleted_at.is_(None)
    ))).scalars().all()
    fees = (await db.execute(select(_Fee).where(
        _Fee.client_id == client_id, _Fee.deleted_at.is_(None)
    ))).scalars().all()
    acessos = (await db.execute(
        select(_Audit).where(_Audit.registro_id == client_id)
        .order_by(_Audit.created_at.desc()).limit(50)
    )).scalars().all()

    dados = {
        "cliente": {
            "nome": c.nome or c.razao_social, "tipo": c.tipo.value,
            "documento": c.documento_plain or "—",
            "email": c.email, "telefone": c.telefone or c.whatsapp,
            "endereco": ", ".join(filter(None, [c.logradouro, c.numero,
                                  c.bairro, c.cidade, c.estado])) or "—",
            "origem": c.origem.value if c.origem else "—",
            "cadastrado_em": c.created_at.strftime("%d/%m/%Y"),
        },
        "casos": [{"numero": x.numero_interno, "titulo": x.titulo,
                   "status": str(x.status.value)} for x in casos],
        "documentos": [{"titulo": d.titulo,
                        "data": d.created_at.strftime("%d/%m/%Y")} for d in docs],
        "financeiro": [{"descricao": f.descricao,
                        "valor": float(f.valor or 0),
                        "status": str(f.status.value)} for f in fees],
        "acessos": [{"data": a.created_at.strftime("%d/%m/%Y %H:%M"),
                     "acao": a.acao, "perfil": a.user_role or "—"}
                    for a in acessos],
    }
    try:
        pdf = await relatorio_lgpd_pdf_async(dados)
    except RuntimeError:
        logger.warning("Geração do relatório LGPD em PDF indisponível", exc_info=True)
        raise HTTPException(status_code=503, detail="Geração de PDF indisponível no momento")

    await criar_audit_log(db, cu.id, cu.role.value, "DOWNLOAD", "clients",
                          client_id, detalhes="Relatório LGPD art.18 emitido")
    await db.commit()
    return _Resp(content=pdf, media_type="application/pdf",
                 headers={"Content-Disposition":
                          f'attachment; filename="lgpd_{client_id[:8]}.pdf"'})


@router.get("/{client_id}/dados-lgpd.json")
async def dados_lgpd_json(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """
    Portabilidade LGPD (art. 18, V) — dados do titular em JSON estruturado,
    machine-readable, para importação por outro sistema. Complementa o PDF (art. 18, II).
    """
    from app.models.case import Case as _Case
    from app.models.document import Document as _Doc
    from app.models.fee import Fee as _Fee

    c = (await db.execute(select(Client).where(
        Client.id == client_id, Client.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    casos = (await db.execute(select(_Case).where(
        _Case.client_id == client_id, _Case.deleted_at.is_(None)
    ))).scalars().all()
    docs = (await db.execute(select(_Doc).where(
        _Doc.client_id == client_id, _Doc.deleted_at.is_(None)
    ))).scalars().all()
    fees = (await db.execute(select(_Fee).where(
        _Fee.client_id == client_id, _Fee.deleted_at.is_(None)
    ))).scalars().all()

    payload = {
        "titular": {
            "nome": c.nome or c.razao_social, "tipo": c.tipo.value,
            "cpf": c.cpf_plain, "cnpj": c.cnpj_plain, "email": c.email,
            "telefone": c.telefone, "whatsapp": c.whatsapp,
            "cadastrado_em": c.created_at.isoformat() if c.created_at else None,
        },
        "casos": [{"numero_interno": x.numero_interno, "titulo": x.titulo,
                   "area": str(x.area.value), "status": str(x.status.value),
                   "numero_processo": x.numero_processo} for x in casos],
        "documentos": [{"titulo": d.titulo,
                        "data": d.created_at.isoformat() if d.created_at else None}
                       for d in docs],
        "financeiro": [{"descricao": f.descricao, "valor": float(f.valor or 0),
                        "status": str(f.status.value)} for f in fees],
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "base_legal": "LGPD (Lei 13.709/2018), art. 18, incisos II e V",
    }
    await criar_audit_log(db, cu.id, cu.role.value, "EXPORT_LGPD_JSON", "clients",
                          client_id, detalhes="Portabilidade LGPD art.18,V (JSON)")
    await db.commit()
    return payload


class EsquecimentoReq(_BM):
    motivo: Optional[str] = _Field(None, max_length=500)
    forcar: bool = False


@router.get("/{client_id}/esquecimento/bloqueios")
async def verificar_bloqueios_esquecimento(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """Consulta (sem executar) o que impede a anonimização deste cliente agora."""
    from app.services.client_anonimizacao import verificar_bloqueios
    c = (await db.execute(select(Client).where(
        Client.id == client_id, Client.deleted_at.is_(None)
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    bloqueios = await verificar_bloqueios(db, client_id)
    return {
        "client_id": client_id,
        "ja_anonimizado": c.anonimizado_em is not None,
        "pode_anonimizar": not bloqueios and c.anonimizado_em is None,
        "bloqueios": bloqueios,
    }


@router.post("/{client_id}/esquecimento", status_code=200)
async def solicitar_esquecimento(
    client_id: str,
    req: EsquecimentoReq = EsquecimentoReq(),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(require_roles(["superadmin", "admin", "socio"])),
):
    """
    Direito ao esquecimento (LGPD art. 17). Restrito a sócio+/admin dado o
    caráter irreversível — anonimiza PII do cliente, preservando casos/
    financeiro por obrigação legal (art. 16, II). Bloqueado se há caso em
    representação ativa, salvo forcar=true (fica registrado na auditoria).
    """
    from app.services.client_anonimizacao import anonimizar_cliente
    resultado = await anonimizar_cliente(
        db, client_id, cu.id, cu.role.value,
        motivo=req.motivo, forcar=req.forcar,
    )
    return resultado
