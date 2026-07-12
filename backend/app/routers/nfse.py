# ── app/routers/nfse.py ──────────────────────────────────────────────────────
# NFS-e — emissão fiscal a partir de um honorário/recebível (ou avulsa).
#
# Emissão fiscal é AÇÃO SENSÍVEL: tudo gated por NFSE_ENABLED (503 se off) e por
# credenciais configuradas (422 se faltam); emissão/cancelamento exigem socio+ e
# geram audit log ANTES e DEPOIS (a trilha do "antes" é commitada antes de tocar
# o provedor, para não se perder se a chamada externa falhar). Idempotência:
# referencia = fee-<id> — não emite segunda nota para um honorário já em curso.
#
#   GET  /nfse/status          — advogado+  (booleans/ambiente p/ gate da UI — sem dados)
#   POST /nfse/emitir          — socio+     (rate limit; audit; idempotente)
#   GET  /nfse/{id}            — perfil financeiro (socio+/financeiro — expõe honorários e CPF/CNPJ)
#   GET  /nfse/{id}/pdf        — perfil financeiro (DANFSe)
#   GET  /nfse/{id}/xml        — perfil financeiro
#   POST /nfse/{id}/cancelar   — socio+     (motivo; audit)
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.fee import Fee
from app.models.nfse import NFSeStatus, NotaFiscalServico
from app.models.user import User
from app.services import nfse as nfse_service
from app.services.nfse import NFSePedidoEmissao, NFSeResultado, NFSeTomador

logger = logging.getLogger("ejc.nfse")

router = APIRouter(prefix="/nfse", tags=["NFS-e (emissão fiscal)"])

# socio+ = socio, admin, superadmin (hierarquia ROLE_LEVEL). advogado+ inclui advogado.
_SOCIO_MAIS = require_roles(["socio"])
_ADVOGADO_MAIS = require_roles(["advogado"])

# Item 5 (auditoria pré-produção): LEITURA de nota (consulta/PDF/XML) expõe
# honorários e CPF/CNPJ do tomador — alinhado ao gate do módulo financeiro
# (fees.py: _FINANCEIRO_TOTAL). `financeiro` tem nível hierárquico BAIXO (4),
# então require_roles não serve aqui — é allowlist explícita de perfis.
_PERFIS_FINANCEIROS = {"superadmin", "admin", "socio", "financeiro"}


def _req_financeiro_leitura(cu: User = Depends(get_current_user)) -> User:
    """Leitura de dados fiscais reservada aos perfis fiduciários (fees.py)."""
    if getattr(cu.role, "value", str(cu.role)) not in _PERFIS_FINANCEIROS:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para consultar dados fiscais",
        )
    return cu

# Status em que uma nota "ocupa" a referência (idempotência do fee).
_STATUS_ATIVOS = (NFSeStatus.processando.value, NFSeStatus.autorizada.value)


# ── Schemas ────────────────────────────────────────────────────────────────────

class TomadorIn(BaseModel):
    documento: str = Field(description="CPF ou CNPJ (com ou sem máscara)")
    nome: str
    email: str | None = None
    cod_municipio_ibge: str | None = None
    uf: str | None = None
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    bairro: str | None = None


class EmitirIn(BaseModel):
    """Informe fee_id (emite a partir do honorário) OU dados avulsos
    (tomador + valor + descrição)."""
    fee_id: str | None = None
    tomador: TomadorIn | None = None
    valor: Decimal | None = None
    descricao: str | None = None
    competencia: str | None = Field(default=None, description="YYYY-MM-DD; default = hoje")

    @model_validator(mode="after")
    def _valida(self):
        if not self.fee_id and not (self.tomador and self.valor is not None and self.descricao):
            raise ValueError(
                "Informe fee_id OU (tomador + valor + descricao) para nota avulsa."
            )
        return self


class CancelarIn(BaseModel):
    motivo: str = Field(min_length=3, description="Justificativa do cancelamento")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _role(cu: User) -> str:
    return getattr(cu.role, "value", str(cu.role))


def _nota_dict(n: NotaFiscalServico) -> dict:
    """Projeção segura da nota (sem segredos)."""
    return {
        "id": n.id,
        "fee_id": n.fee_id,
        "client_id": n.client_id,
        "provider": n.provider,
        "provider_id": n.provider_id,
        "referencia": n.referencia,
        "ambiente": n.ambiente,
        "status": n.status,
        "numero": n.numero,
        "chave_acesso": n.chave_acesso,
        "valor": str(n.valor) if n.valor is not None else None,
        "descricao": n.descricao,
        "pdf_url": n.pdf_url,
        "xml_url": n.xml_url,
        "mensagem_erro": n.mensagem_erro,
    }


def _tomador_de(cliente: Client | None, override: TomadorIn | None) -> NFSeTomador:
    """Monta o tomador do body (override) ou do cadastro do cliente.

    Os campos de documento do cliente podem estar apenas cifrados (cpf_enc/
    cnpj_enc) — nesses casos o cadastro não expõe o número em claro e o
    tomador precisa ser informado no body (documento é obrigatório na DPS).
    """
    if override is not None:
        return NFSeTomador(**override.model_dump())
    if cliente is None:
        raise HTTPException(
            status_code=422,
            detail="Sem tomador: informe o objeto `tomador` no body.",
        )
    documento = (cliente.cnpj or cliente.cpf or "").strip()
    nome = (cliente.razao_social or cliente.nome or "").strip()
    if not documento or not nome:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cliente sem documento/nome em claro para a nota. Informe o "
                "objeto `tomador` no body (documento é obrigatório na DPS)."
            ),
        )
    return NFSeTomador(
        documento=documento, nome=nome, email=cliente.email,
        uf=cliente.estado, cep=cliente.cep,
        logradouro=cliente.logradouro, numero=cliente.numero, bairro=cliente.bairro,
    )


def _aplicar_resultado(n: NotaFiscalServico, r: NFSeResultado) -> None:
    n.status = r.status or n.status
    n.provider_id = r.provider_id or n.provider_id
    n.numero = r.numero or n.numero
    n.chave_acesso = r.chave_acesso or n.chave_acesso
    n.ambiente = r.ambiente or n.ambiente
    n.pdf_url = r.pdf_url or n.pdf_url
    n.xml_url = r.xml_url or n.xml_url
    n.mensagem_erro = "; ".join(r.mensagens) if r.mensagens else n.mensagem_erro


def _provider_ou_http():
    """get_provider() traduzindo erros de gate para HTTPException (503/422)."""
    try:
        return nfse_service.get_provider()
    except (nfse_service.NFSeDesabilitadaError, nfse_service.NFSeConfigError) as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
async def status_nfse(cu: User = Depends(_ADVOGADO_MAIS)):
    """Gate da UI — {enabled, configured, ambiente, provedor}, sem segredos."""
    return nfse_service.status_atual()


@router.post("/emitir", dependencies=[Depends(rate_limit("nfse_emitir", 6))])
async def emitir_nfse(
    body: EmitirIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    """Emite uma NFS-e a partir de um honorário (fee_id) ou avulsa."""
    provider = _provider_ou_http()
    ambiente_atual = nfse_service.status_atual()["ambiente"]

    client_id = None
    if body.fee_id:
        fee = await db.get(Fee, body.fee_id)
        if fee is None or getattr(fee, "deleted_at", None) is not None:
            raise HTTPException(status_code=404, detail="Honorário não encontrado.")
        referencia = f"fee-{fee.id}"
        cliente = await db.get(Client, fee.client_id) if fee.client_id else None
        valor = body.valor if body.valor is not None else fee.valor
        descricao = body.descricao or fee.descricao
        client_id = fee.client_id
    else:
        referencia = f"avulso-{uuid4().hex[:16]}"
        cliente = None
        valor = body.valor
        descricao = body.descricao

    if valor is None or not descricao:
        raise HTTPException(
            status_code=422,
            detail="Honorário sem valor/descrição — informe valor e descricao no body.",
        )

    # ── RESERVA ATÔMICA (fix corrida TOCTOU de duplo-clique/retry) ───────────
    # A linha é criada em `processando` e COMITADA *antes* de tocar o provedor.
    # O UNIQUE(provider, referencia) serializa: se duas requisições para o mesmo
    # honorário chegam juntas, só a 1ª reserva a referência; a 2ª cai no
    # IntegrityError → 409, sem uma segunda emissão real no provedor.
    # Bloqueio da linha (with_for_update) evita reemissão dupla quando já existe
    # uma nota terminal (rejeitada/cancelada) sendo reaproveitada.
    existente = await db.scalar(
        select(NotaFiscalServico)
        .where(
            NotaFiscalServico.provider == "nuvemfiscal",
            NotaFiscalServico.referencia == referencia,
        )
        .with_for_update()
    )
    if existente is not None:
        if existente.status in _STATUS_ATIVOS:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Já existe NFS-e ({existente.status}) para este honorário "
                    f"(nota {existente.id}). Cancele-a antes de reemitir."
                ),
            )
        # Terminal (rejeitada/cancelada): reaproveita a linha para reemitir.
        nota = existente
        nota.status = NFSeStatus.processando.value
        nota.ambiente = ambiente_atual
        nota.valor = Decimal(str(valor))
        nota.descricao = descricao
        nota.client_id = client_id
        nota.provider_id = None
        nota.numero = None
        nota.chave_acesso = None
        nota.pdf_url = None
        nota.xml_url = None
        nota.mensagem_erro = None
    else:
        nota = NotaFiscalServico(
            id=str(uuid4()),
            fee_id=body.fee_id, client_id=client_id,
            provider="nuvemfiscal", referencia=referencia,
            ambiente=ambiente_atual, status=NFSeStatus.processando.value,
            valor=Decimal(str(valor)), descricao=descricao, created_by=cu.id,
        )
        db.add(nota)

    # Tomador resolvido só depois do short-circuit de idempotência (nota ativa
    # → 409) e antes do commit da reserva: se faltar tomador (422), a transação
    # é descartada sem deixar a referência presa em `processando`.
    tomador = _tomador_de(cliente, body.tomador)

    # Audit ANTES (durável): registra a INTENÇÃO de emitir antes de tocar o
    # provedor — se a chamada externa falhar, a tentativa fica na trilha.
    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_EMITIR", "nfse", nota.id,
        detalhes=f"ref={referencia} ambiente={ambiente_atual}",
        dados_depois={"referencia": referencia, "fee_id": body.fee_id,
                      "valor": str(valor), "descricao": descricao},
    )
    try:
        await db.commit()   # reserva a referência (UNIQUE fecha a corrida)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe NFS-e em emissão para este honorário. Aguarde e consulte.",
        )

    pedido = NFSePedidoEmissao(
        referencia=referencia, tomador=tomador,
        descricao=descricao, valor=Decimal(str(valor)), competencia=body.competencia,
    )
    try:
        resultado = await provider.emitir(pedido)
    except (nfse_service.NFSeConfigError, nfse_service.NFSeDesabilitadaError,
            nfse_service.NFSeProviderError) as e:
        # Falha ao emitir: marca a nota como rejeitada (estado terminal) para
        # não deixar a referência presa em `processando` — assim uma nova
        # tentativa pode reaproveitar a linha. A trilha do "antes" já foi
        # commitada; registra também a falha.
        code, detail = nfse_service.http_status_para_erro(e)
        nota.status = NFSeStatus.rejeitada.value
        nota.mensagem_erro = detail
        await criar_audit_log(
            db, cu.id, _role(cu), "NFSE_EMISSAO_FALHOU", "nfse", nota.id,
            detalhes=f"http={code}", dados_depois={"status": nota.status},
        )
        await db.commit()
        raise HTTPException(status_code=code, detail=detail)

    _aplicar_resultado(nota, resultado)
    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_EMITIDA", "nfse", nota.id,
        detalhes=f"status={resultado.status} provider_id={resultado.provider_id}",
        dados_depois={"status": resultado.status, "provider_id": resultado.provider_id,
                      "numero": resultado.numero},
    )
    await db.commit()
    return _nota_dict(nota)


@router.get("/{nota_id}")
async def obter_nfse(
    nota_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_leitura),
):
    """Consulta a nota; se `processando`, tenta atualizar do provedor."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if nota.status == NFSeStatus.processando.value and nota.provider_id:
        try:
            provider = nfse_service.get_provider()
            resultado = await provider.consultar(nota.provider_id)
            _aplicar_resultado(nota, resultado)
            await db.commit()
        except nfse_service.NFSeError:
            # Falha ao atualizar não derruba a leitura — devolve o estado salvo.
            logger.info("[nfse] falha ao atualizar nota %s do provedor", nota_id)
    return _nota_dict(nota)


@router.get("/{nota_id}/pdf")
async def baixar_pdf_nfse(
    nota_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_leitura),
):
    """Stream do DANFSe (PDF) da nota."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if not nota.provider_id:
        raise HTTPException(status_code=409, detail="Nota ainda não emitida no provedor.")
    provider = _provider_ou_http()
    try:
        pdf = await provider.baixar_pdf(nota.provider_id)
    except nfse_service.NFSeError as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="nfse-{nota.numero or nota.id}.pdf"'},
    )


@router.get("/{nota_id}/xml")
async def baixar_xml_nfse(
    nota_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_leitura),
):
    """XML autorizado da nota."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if not nota.provider_id:
        raise HTTPException(status_code=409, detail="Nota ainda não emitida no provedor.")
    provider = _provider_ou_http()
    try:
        xml = await provider.baixar_xml(nota.provider_id)
    except nfse_service.NFSeError as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)
    return Response(
        content=xml, media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="nfse-{nota.numero or nota.id}.xml"'},
    )


@router.post("/{nota_id}/cancelar", dependencies=[Depends(rate_limit("nfse_cancelar", 6))])
async def cancelar_nfse(
    nota_id: str,
    body: CancelarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_SOCIO_MAIS),
):
    """Cancela a nota no provedor (motivo obrigatório; audit)."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if not nota.provider_id:
        raise HTTPException(status_code=409, detail="Nota ainda não emitida no provedor.")
    provider = _provider_ou_http()

    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_CANCELAR", "nfse", nota.id,
        detalhes=f"motivo={body.motivo}", dados_antes={"status": nota.status},
    )
    await db.commit()

    try:
        resultado = await provider.cancelar(nota.provider_id, body.motivo)
    except nfse_service.NFSeError as e:
        code, detail = nfse_service.http_status_para_erro(e)
        raise HTTPException(status_code=code, detail=detail)

    _aplicar_resultado(nota, resultado)
    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_CANCELADA", "nfse", nota.id,
        detalhes=f"status={nota.status}", dados_depois={"status": nota.status},
    )
    await db.commit()
    return _nota_dict(nota)
