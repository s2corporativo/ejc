# ── app/routers/nfse.py ──────────────────────────────────────────────────────
# NFS-e — emissão fiscal a partir de um honorário/recebível (ou avulsa).
#
# Emissão fiscal é AÇÃO SENSÍVEL: tudo gated por NFSE_ENABLED (503 se off) e por
# credenciais configuradas (422 se faltam); emissão/cancelamento exigem socio+ e
# geram audit log ANTES e DEPOIS (a trilha do "antes" é commitada antes de tocar
# o provedor, para não se perder se a chamada externa falhar). Idempotência:
# referencia = fee-<id> — não emite segunda nota para um honorário já em curso.
#
#   GET  /nfse/status          — advogado+ OU perfil financeiro (booleans/ambiente
#                                p/ gate da UI — sem dados)
#   GET  /nfse                 — perfil financeiro (listagem paginada; SEM gate NFSE_ENABLED)
#   POST /nfse/emitir          — socio+     (rate limit; audit; idempotente)
#   POST /nfse/manual          — perfil financeiro (registro de nota emitida FORA do
#                                sistema, no Emissor Nacional gov.br; SEM gate NFSE_ENABLED)
#   POST /nfse/manual/{id}/cancelar — perfil financeiro (cancelamento LÓGICO; sem gate)
#   GET  /nfse/{id}            — perfil financeiro (socio+/financeiro — expõe honorários e CPF/CNPJ)
#   GET  /nfse/{id}/pdf        — perfil financeiro (DANFSe; nota manual → arquivo local)
#   GET  /nfse/{id}/xml        — perfil financeiro (nota manual → arquivo local)
#   POST /nfse/{id}/cancelar   — socio+     (motivo; audit)
from __future__ import annotations

import contextlib
import logging
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path as FSPath
from uuid import uuid4

import aiofiles
from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Request, Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func as sqlfunc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import ROLE_LEVEL, get_current_user, require_roles
from app.models.audit_log import criar_audit_log
from app.models.client import Client
from app.models.fee import Fee
from app.models.nfse import NFSeStatus, NotaFiscalServico
from app.models.user import User
# Validação de upload por magic bytes — MESMO helper do GED (padrão do projeto).
from app.routers.documents import _validar_conteudo
from app.services import nfse as nfse_service
from app.services.nfse import NFSePedidoEmissao, NFSeResultado, NFSeTomador

logger = logging.getLogger("ejc.nfse")

router = APIRouter(prefix="/nfse", tags=["NFS-e (emissão fiscal)"])

# socio+ = socio, admin, superadmin (hierarquia ROLE_LEVEL).
_SOCIO_MAIS = require_roles(["socio"])

# Item 5 (auditoria pré-produção): acesso a nota (consulta/PDF/XML/registro
# manual) expõe honorários e CPF/CNPJ do tomador — alinhado ao gate do módulo
# financeiro (fees.py: _FINANCEIRO_TOTAL). `financeiro` tem nível hierárquico
# BAIXO (4), então require_roles não serve aqui — é allowlist explícita de perfis.
_PERFIS_FINANCEIROS = {"superadmin", "admin", "socio", "financeiro"}


def _req_financeiro_leitura(cu: User = Depends(get_current_user)) -> User:
    """Acesso a dados fiscais reservado aos perfis fiduciários (fees.py).

    Usada em endpoints de LEITURA e também de ESCRITA do modo manual
    (registro/cancelamento) — por isso a mensagem do 403 é neutra, sem
    sugerir que só a consulta foi negada.
    """
    if getattr(cu.role, "value", str(cu.role)) not in _PERFIS_FINANCEIROS:
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para dados fiscais",
        )
    return cu


def _req_status_nfse(cu: User = Depends(get_current_user)) -> User:
    """GET /nfse/status: advogado+ (hierarquia) OU perfil da allowlist financeira.

    O payload é só o gate da UI (booleans/ambiente, sem dados fiscais), mas o
    papel `financeiro` tem nível hierárquico BAIXO (4 < advogado=6) e tomava
    403 no require_roles(["advogado"]) — e é justamente quem opera a tela de
    NFS-e. Dependência própria: hierarquia OU allowlist, sem enfraquecer os
    demais gates.
    """
    role = getattr(cu.role, "value", str(cu.role))
    if role in _PERFIS_FINANCEIROS or ROLE_LEVEL.get(role, 0) >= ROLE_LEVEL["advogado"]:
        return cu
    raise HTTPException(status_code=403, detail="Sem permissão para dados fiscais")

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
    # max_length: 422 de validação em vez de estourar o limite da coluna no banco.
    motivo: str = Field(min_length=3, max_length=500,
                        description="Justificativa do cancelamento")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _role(cu: User) -> str:
    return getattr(cu.role, "value", str(cu.role))


def _nota_dict(n: NotaFiscalServico) -> dict:
    """Projeção segura da nota (sem segredos; paths locais viram booleans)."""
    if n.provider == "manual":
        # Manual: os booleans refletem os ANEXOS locais realmente gravados.
        tem_pdf = bool(n.pdf_path)
        tem_xml = bool(n.xml_path)
    else:
        # Provedor: DANFSe/XML só existem depois da AUTORIZAÇÃO — antes disso
        # o download falharia no provedor; não acenda o botão na UI.
        autorizada = n.status == NFSeStatus.autorizada.value
        tem_pdf = autorizada and bool(n.pdf_url or n.provider_id)
        tem_xml = autorizada and bool(n.xml_url or n.provider_id)
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
        "data_emissao": n.data_emissao.isoformat() if n.data_emissao else None,
        "competencia": n.competencia.isoformat() if n.competencia else None,
        "motivo_cancelamento": n.motivo_cancelamento,
        # pdf_path/xml_path são paths de SERVIDOR — nunca expostos; só booleans.
        "tem_pdf": tem_pdf,
        "tem_xml": tem_xml,
    }


def _tomador_de(cliente: Client | None, override: TomadorIn | None) -> NFSeTomador:
    """Monta o tomador do body (override) ou do cadastro do cliente.

    Cutover C6/LGPD: o documento do cliente vive só cifrado (cpf_enc/cnpj_enc);
    é decifrado sob demanda aqui (cnpj_plain/cpf_plain) para a DPS, que exige o
    número. PJ-first (o tomador PJ usa CNPJ). Se o cadastro não tiver documento,
    o `tomador` precisa vir no body.
    """
    if override is not None:
        return NFSeTomador(**override.model_dump())
    if cliente is None:
        raise HTTPException(
            status_code=422,
            detail="Sem tomador: informe o objeto `tomador` no body.",
        )
    documento = (cliente.cnpj_plain or cliente.cpf_plain or "").strip()
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


# ── Helpers do modo MANUAL (nota emitida no Emissor Nacional gov.br) ──────────
# Arquivos anexados ficam no MESMO storage do GED (settings.UPLOAD_DIR), em
# subpasta própria `nfse/`, com nome gerado (uuid) — NUNCA o filename do usuário.

_MANUAL_SUBDIR = "nfse"
_EXTENSOES_MANUAL = {".pdf", ".xml"}  # extensões controladas do modo manual


def _filename_seguro(nota: NotaFiscalServico) -> str:
    """Nome p/ Content-Disposition — só [A-Za-z0-9._-].

    `numero` é entrada de usuário no modo manual (e dado externo no provedor):
    nunca interpolar cru no header HTTP (CR/LF/aspas = header injection).
    Vazio após sanitizar → cai para o id (uuid, sempre seguro).
    """
    seguro = re.sub(r"[^A-Za-z0-9._-]", "_", (nota.numero or "").strip())
    return seguro or nota.id


def _parse_data(campo: str, valor: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"{campo} inválida: use o formato YYYY-MM-DD.",
        )


async def _ler_e_validar_upload(upload: UploadFile, ext: str) -> bytes:
    """Lê e valida um anexo da nota manual SEGUINDO O PADRÃO DO GED:
    extensão controlada + limite MAX_UPLOAD_MB + magic bytes (_validar_conteudo).
    """
    assert ext in _EXTENSOES_MANUAL
    nome = (upload.filename or "").lower()
    if not nome.endswith(ext):
        raise HTTPException(
            status_code=415, detail=f"Arquivo deve ter extensão {ext}.",
        )
    # Leitura em CHUNKS com teto: corta em teto+1 byte com 413 em vez de um
    # .read() ilimitado que carregaria upload arbitrário inteiro em memória.
    max_mb = get_settings().MAX_UPLOAD_MB
    max_bytes = max_mb * 1024 * 1024
    partes: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"Arquivo excede {max_mb}MB")
        partes.append(chunk)
    conteudo = b"".join(partes)
    if not conteudo:
        raise HTTPException(status_code=422, detail=f"Arquivo {ext} vazio.")
    _validar_conteudo(ext, conteudo)  # magic bytes (server-side), padrão GED
    # Reforço defensivo além do libmagic:
    if ext == ".pdf" and not conteudo.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="PDF inválido (assinatura %PDF- ausente).")
    if ext == ".xml":
        inicio = conteudo.lstrip()
        if not (inicio.startswith(b"<?xml") or inicio.startswith(b"<")):
            raise HTTPException(status_code=415, detail="XML inválido (conteúdo não é XML).")
    return conteudo


async def _salvar_arquivo_manual(conteudo: bytes, ext: str) -> str:
    """Grava em UPLOAD_DIR/nfse/<uuid><ext> e devolve o path RELATIVO salvo."""
    base = FSPath(get_settings().UPLOAD_DIR)
    (base / _MANUAL_SUBDIR).mkdir(parents=True, exist_ok=True)
    rel = f"{_MANUAL_SUBDIR}/{uuid4().hex}{ext}"
    async with aiofiles.open(base / rel, "wb") as f:
        await f.write(conteudo)
    return rel


def _arquivo_manual_ou_404(rel_path: str | None, tipo: str) -> FSPath:
    """Resolve o path salvo no banco DENTRO do diretório-base de upload.

    Anti path-traversal: só serve arquivo cujo resolve() permaneça sob
    UPLOAD_DIR (is_relative_to). 404 claro quando não há anexo.
    """
    if not rel_path:
        raise HTTPException(
            status_code=404,
            detail=f"Nota manual sem arquivo {tipo.upper()} anexado.",
        )
    # Confinamento adicional ao resolve/is_relative_to: o modo manual só grava
    # na subpasta nfse/ — path salvo fora dela (registro adulterado apontando
    # p/ outro arquivo do UPLOAD_DIR, ex.: doc do GED) não é servido.
    if not rel_path.startswith(f"{_MANUAL_SUBDIR}/"):
        raise HTTPException(status_code=404, detail="Arquivo da nota inválido.")
    base = FSPath(get_settings().UPLOAD_DIR).resolve()
    destino = (base / rel_path).resolve()
    if not destino.is_relative_to(base):
        raise HTTPException(status_code=404, detail="Arquivo da nota inválido.")
    if not destino.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo {tipo.upper()} da nota não encontrado no armazenamento.",
        )
    return destino


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
async def status_nfse(cu: User = Depends(_req_status_nfse)):
    """Gate da UI — {enabled, configured, ambiente, provedor}, sem segredos.

    `manual_disponivel` é sempre True: o REGISTRO manual (nota emitida no
    Emissor Nacional gov.br) funciona mesmo com NFSE_ENABLED=false.
    """
    payload = nfse_service.status_atual()
    payload["manual_disponivel"] = True
    payload["emissor_nacional_url"] = "https://www.nfse.gov.br/EmissorNacional"
    return payload


@router.get("")
async def listar_nfse(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_leitura),
):
    """Listagem paginada das notas (manuais e de provedor). Sem gate NFSE_ENABLED."""
    filtros = []
    if status:
        filtros.append(NotaFiscalServico.status == status)
    if client_id:
        filtros.append(NotaFiscalServico.client_id == client_id)
    if provider:
        filtros.append(NotaFiscalServico.provider == provider)

    total = await db.scalar(
        select(sqlfunc.count()).select_from(NotaFiscalServico).where(*filtros)
    )
    rows = (
        await db.execute(
            select(NotaFiscalServico)
            .where(*filtros)
            .order_by(NotaFiscalServico.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return {"items": [_nota_dict(n) for n in rows], "total": int(total or 0)}


@router.post("/manual", dependencies=[Depends(rate_limit("nfse_manual", 6))])
async def registrar_nfse_manual(
    # Request p/ rejeitar cedo corpo acima do teto via Content-Length (o default
    # None só existe p/ chamadas diretas nos testes; no HTTP o FastAPI injeta).
    request: Request = None,
    # max_length nos Form: 422 de validação em vez de estourar coluna no banco.
    numero: str = Form(..., max_length=30),
    data_emissao: str = Form(..., description="YYYY-MM-DD"),
    valor: Decimal = Form(...),
    descricao: str = Form(..., max_length=2000),
    chave_acesso: str | None = Form(default=None, max_length=60),
    competencia: str | None = Form(default=None, description="YYYY-MM-DD"),
    client_id: str | None = Form(default=None),
    fee_id: str | None = Form(default=None),
    pdf: UploadFile | None = File(default=None),
    xml: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_leitura),
):
    """Registra nota emitida FORA do sistema (Emissor Nacional gov.br).

    Escrituração, não emissão fiscal — por isso perfil financeiro (allowlist
    de fees.py) e SEM gate NFSE_ENABLED. Anexos opcionais (DANFSe PDF e XML)
    validados por magic bytes como no GED.
    """
    # Rejeição CEDO por Content-Length (teto do GED): corpo declaradamente
    # acima do limite toma 413 antes de qualquer leitura do stream multipart.
    if request is not None:
        max_mb = get_settings().MAX_UPLOAD_MB
        content_length = (request.headers.get("content-length") or "").strip()
        if content_length.isdigit() and int(content_length) > max_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"Requisição excede {max_mb}MB",
            )

    numero = numero.strip()
    descricao = descricao.strip()
    if not numero:
        raise HTTPException(status_code=422, detail="Informe o número da nota.")
    if not descricao:
        raise HTTPException(status_code=422, detail="Informe a descrição do serviço.")
    if valor <= 0:
        raise HTTPException(status_code=422, detail="Valor deve ser maior que zero.")
    dt_emissao = _parse_data("data_emissao", data_emissao)
    dt_competencia = _parse_data("competencia", competencia) if competencia else None

    # Idempotência do registro manual: mesmo `numero` com nota manual ATIVA
    # (não cancelada) já escriturada → 409, evitando duplicar em duplo-clique/
    # retry (o Emissor Nacional não emite duas notas com o mesmo número).
    ja_registrada = await db.scalar(
        select(NotaFiscalServico.id).where(
            NotaFiscalServico.provider == "manual",
            NotaFiscalServico.numero == numero,
            NotaFiscalServico.status != NFSeStatus.cancelada.value,
        )
    )
    if ja_registrada:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Já existe nota manual ativa com o número {numero} "
                f"(nota {ja_registrada}). Cancele-a antes de registrar novamente."
            ),
        )

    if fee_id:
        fee = await db.get(Fee, fee_id)
        if fee is None or getattr(fee, "deleted_at", None) is not None:
            raise HTTPException(status_code=404, detail="Honorário não encontrado.")
        if not client_id:
            client_id = fee.client_id
    if client_id:
        cliente = await db.get(Client, client_id)
        if cliente is None:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    # Valida os DOIS anexos antes de gravar qualquer um (sem órfão em falha).
    conteudo_pdf = await _ler_e_validar_upload(pdf, ".pdf") if pdf is not None else None
    conteudo_xml = await _ler_e_validar_upload(xml, ".xml") if xml is not None else None

    # Da gravação em disco ao commit em bloco único: se QUALQUER passo falhar
    # (audit, commit, gravação do 2º arquivo), remove do storage o que já foi
    # gravado — sem arquivo órfão sem registro no banco — e re-levanta o erro.
    pdf_path = xml_path = None
    try:
        pdf_path = await _salvar_arquivo_manual(conteudo_pdf, ".pdf") if conteudo_pdf else None
        xml_path = await _salvar_arquivo_manual(conteudo_xml, ".xml") if conteudo_xml else None

        nota = NotaFiscalServico(
            id=str(uuid4()),
            fee_id=fee_id, client_id=client_id,
            provider="manual", referencia=f"manual-{uuid4().hex[:12]}",
            ambiente="producao",  # nota REAL, emitida no Emissor Nacional
            status=NFSeStatus.autorizada.value,
            numero=numero, chave_acesso=(chave_acesso or "").strip() or None,
            valor=valor, descricao=descricao,  # valor já é Decimal (Form tipado)
            data_emissao=dt_emissao, competencia=dt_competencia,
            pdf_path=pdf_path, xml_path=xml_path,
            created_by=cu.id,
        )
        db.add(nota)
        await criar_audit_log(
            db, cu.id, _role(cu), "NFSE_MANUAL_REGISTRADA", "nfse", nota.id,
            detalhes=f"numero={numero} data_emissao={dt_emissao.isoformat()}",
            dados_depois={
                "numero": numero, "valor": str(valor), "descricao": descricao,
                "data_emissao": dt_emissao.isoformat(),
                "competencia": dt_competencia.isoformat() if dt_competencia else None,
                "chave_acesso": nota.chave_acesso,
                "fee_id": fee_id, "client_id": client_id,
                "tem_pdf": bool(pdf_path), "tem_xml": bool(xml_path),
            },
        )
        await db.commit()
    except Exception:
        base = get_settings().UPLOAD_DIR
        for rel in (pdf_path, xml_path):
            if rel:
                with contextlib.suppress(OSError):
                    os.remove(f"{base}/{rel}")
        raise
    return _nota_dict(nota)


@router.post(
    "/manual/{nota_id}/cancelar",
    dependencies=[Depends(rate_limit("nfse_manual_cancelar", 6))],
)
async def cancelar_nfse_manual(
    nota_id: str,
    body: CancelarIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_leitura),
):
    """Cancelamento LÓGICO de nota manual (não toca provedor; sem gate NFSE_ENABLED)."""
    # FOR UPDATE serializa cancelamentos concorrentes da mesma nota: o 2º clique
    # espera o lock e, após o commit do 1º, cai no 409 "já cancelada" em vez de
    # sobrescrever o motivo/auditar duas vezes.
    nota = await db.scalar(
        select(NotaFiscalServico)
        .where(NotaFiscalServico.id == nota_id)
        .with_for_update()
    )
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if nota.provider != "manual":
        raise HTTPException(
            status_code=409,
            detail="Nota não é manual — use POST /nfse/{id}/cancelar (provedor).",
        )
    if nota.status == NFSeStatus.cancelada.value:
        raise HTTPException(status_code=409, detail="Nota manual já cancelada.")

    dados_antes = {"status": nota.status, "motivo_cancelamento": nota.motivo_cancelamento}
    nota.status = NFSeStatus.cancelada.value
    nota.motivo_cancelamento = body.motivo
    await criar_audit_log(
        db, cu.id, _role(cu), "NFSE_MANUAL_CANCELADA", "nfse", nota.id,
        detalhes=f"motivo={body.motivo}",
        dados_antes=dados_antes,
        dados_depois={"status": nota.status, "motivo_cancelamento": body.motivo},
    )
    await db.commit()
    return _nota_dict(nota)


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
        # Idempotência cruzada com o modo MANUAL: se o honorário já tem nota
        # manual ATIVA escriturada, emitir de novo no provedor duplicaria a
        # nota fiscal do mesmo serviço → 409 orientando cancelar o registro
        # manual antes.
        manual_ativa = await db.scalar(
            select(NotaFiscalServico.id).where(
                NotaFiscalServico.provider == "manual",
                NotaFiscalServico.fee_id == body.fee_id,
                NotaFiscalServico.status != NFSeStatus.cancelada.value,
            )
        )
        if manual_ativa:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Este honorário já tem nota manual ativa (nota {manual_ativa}). "
                    "Cancele o registro manual antes de emitir pelo provedor."
                ),
            )
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
    """Consulta a nota; se `processando`, tenta atualizar do provedor.

    Nota MANUAL: apenas devolve o registro (não há provedor para consultar).
    """
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if nota.provider == "manual":
        return _nota_dict(nota)
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
    """Stream do DANFSe (PDF) da nota. Nota MANUAL → arquivo local (sem gate)."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if nota.provider == "manual":
        caminho = _arquivo_manual_ou_404(nota.pdf_path, "pdf")
        await criar_audit_log(
            db, cu.id, _role(cu), "NFSE_ARQUIVO_BAIXADO", "nfse", nota.id,
            detalhes="tipo=pdf",
        )
        await db.commit()
        return FileResponse(
            caminho, media_type="application/pdf",
            headers={"Content-Disposition":
                     f'inline; filename="nfse-{_filename_seguro(nota)}.pdf"'},
        )
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
        headers={"Content-Disposition": f'inline; filename="nfse-{_filename_seguro(nota)}.pdf"'},
    )


@router.get("/{nota_id}/xml")
async def baixar_xml_nfse(
    nota_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_req_financeiro_leitura),
):
    """XML autorizado da nota. Nota MANUAL → arquivo local (sem gate)."""
    nota = await db.get(NotaFiscalServico, nota_id)
    if nota is None:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada.")
    if nota.provider == "manual":
        caminho = _arquivo_manual_ou_404(nota.xml_path, "xml")
        await criar_audit_log(
            db, cu.id, _role(cu), "NFSE_ARQUIVO_BAIXADO", "nfse", nota.id,
            detalhes="tipo=xml",
        )
        await db.commit()
        return FileResponse(
            caminho, media_type="application/xml",
            headers={"Content-Disposition":
                     f'attachment; filename="nfse-{_filename_seguro(nota)}.xml"'},
        )
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
        headers={"Content-Disposition": f'attachment; filename="nfse-{_filename_seguro(nota)}.xml"'},
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
