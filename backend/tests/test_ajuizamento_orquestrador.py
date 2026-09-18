"""Núcleo de ajuizamento — orquestrador ponta a ponta sobre SQLite (aiosqlite).

Padrão do arquivo vizinho (tests/test_dpt360_lifecycle.py): engine em memória
com as tabelas necessárias criadas de Base.metadata e `criar_audit_log`
substituído (AuditLog usa JSONB, Postgres-only).

Cobre o caminho completo CLIENTE → CASO → … → PROTOCOLO → VINCULAÇÃO:
  - validar (preflight persistido, canonico_hash, INVALID/READY_FOR_REVIEW);
  - revisão humana obrigatória (confirmação literal, HITL da peça, hash estável);
  - assinatura (falha não avança; sucesso leva a READY_TO_SUBMIT);
  - protocolo idempotente: chave por tentativa, reenvio após protocolo
    devolve o anterior, timeout exige verificação, REQUIRES_AUTHORIZATION;
  - confirmação manual: registro no ProtocolRegistry, vínculo ao processo/peça
    e movimento na timeline;
  - sincronização: eventos por fonte com precedência e dedupe do DataJud.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.database import Base
from app.models.ajuizamento import (
    EstadoAjuizamento as E, JudicialFilingAttempt, JudicialFilingTransicao,
    JudicialIntegrationProfile, JudicialProtocol, JudicialSyncEvent,
)
from app.models.case import Case, CaseArea, CaseMovimento, CaseStatus
from app.models.case_parte import CaseParte
from app.models.client import Client, ClientTipo
from app.models.document import Document
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.process import Process
from app.models.user import User, UserRole
from app.services.ajuizamento.capacidades import EstadoCapacidade
from app.services.ajuizamento.conectores.base import ResultadoEnvio, ResultadoOperacao, TimeoutConector
from app.services.ajuizamento.conectores.roteador import JudicialConnectorRouter
from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento
from app.services.ajuizamento.orquestrador import (
    AjuizamentoError, CONFIRMACAO_REVISAO, JudicialFilingService,
)

CPF = "529.982.247-25"
CNPJ = "11.222.333/0001-81"
CNPJ_OUTRO = "44.556.677/0001-86"
HASH_PDF = "e" * 64
# Números CNJ fictícios com dígito verificador VÁLIDO (mód. 97, Res. CNJ 65/2008)
# — o registro de protocolo recusa DV inválido, então o teste não pode usar
# número inventado à mão.
CNJ_VALIDO = "50012341220268130024"
CNJ_VALIDO_MASCARA = "5001234-12.2026.8.13.0024"
CNJ_DV_INVALIDO = "50012345620268130024"

_TABELAS = [
    Base.metadata.tables[t] for t in (
        "clients", "cases", "case_partes", "case_movimentos", "users", "documents",
        "legal_docs", "procuracoes", "processes", "tribunais", "judicial_integration_profiles",
        "judicial_filings", "judicial_filing_transicoes", "judicial_filing_attempts",
        "judicial_protocols", "judicial_sync_events", "judicial_tpu_itens",
    )
]


@pytest.fixture(autouse=True)
def _sem_audit(monkeypatch):
    async def _fake(*a, **k):
        return None

    monkeypatch.setattr("app.services.ajuizamento.auditoria.criar_audit_log", _fake)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _settings(**over) -> Settings:
    base = dict(_env_file=None, APP_ENV="development", JUDICIAL_FILING_ENABLED=True)
    base.update(over)
    return Settings(**base)


async def _semear(db, *, peca_status=PecaStatus.aprovada, com_reu=True) -> dict:
    cliente = Client(id="cli-1", tipo=ClientTipo.PF, nome="Maria da Silva", email="m@example.com",
                     cep="32600-000", logradouro="Rua A", numero="10", bairro="Centro",
                     cidade="Betim", estado="MG", data_nascimento=date(1985, 3, 2))
    # Mesmo caminho do router de clientes: PII cifrada em repouso (Fernet).
    cliente.cpf_enc = encrypt(normalizar_documento(CPF))
    cliente.cpf_hash = hash_documento(normalizar_documento(CPF))
    advogado = User(id="adv-1", email="adv@example.com", hashed_password="x", full_name="Dr. João",
                    role=UserRole.advogado, oab_number="123456/MG")
    caso = Case(id="caso-1", numero_interno="DPT-2026-0001", titulo="Ação de danos",
                area=CaseArea.civil, status=CaseStatus.aberto, client_id="cli-1",
                advogado_responsavel_id="adv-1", tribunal="TJMG", comarca="Betim",
                valor_causa=Decimal("15000.00"))
    peca = LegalDoc(id="peca-1", titulo="Petição inicial", tipo_peca=PecaTipo.peticao_inicial,
                    status=peca_status, conteudo="# Inicial", case_id="caso-1", client_id="cli-1",
                    ai_generated=False, human_reviewed=True, versao=1)
    doc = Document(id="doc-1", titulo="Procuração", filename="procuracao.pdf",
                   filepath="/uploads/procuracao.pdf", mimetype="application/pdf",
                   size_bytes=1024, sha256="a" * 64, case_id="caso-1", client_id="cli-1")
    db.add_all([cliente, advogado, caso, peca, doc])
    if com_reu:
        db.add(CaseParte(id="parte-1", case_id="caso-1", tipo="reu", nome="Empresa XPTO LTDA",
                         cpf_cnpj=CNPJ, ativo=True))
    await db.commit()
    return {"cliente": cliente, "caso": caso, "advogado": advogado, "peca": peca, "doc": doc}


def _dados_filing(**over) -> dict:
    base = dict(
        peticao_legal_doc_id="peca-1", tribunal_code="TJMG", system="pje_mni", segment="estadual",
        degree="1", environment="producao", jurisdicao="Betim", codigo_localidade="3106705",
        competencia="Cível", competencia_codigo="1", classe_codigo="7",
        classe_nome="Procedimento Comum Cível",
        assuntos=[{"codigo": "10375", "nome": "Dano Moral", "principal": True}],
        valor_causa=Decimal("15000.00"), nivel_sigilo=0, gratuidade=False, tutela=False,
        documentos=[{"document_id": "doc-1", "document_type": "procuracao", "ordem": 1}],
        advogados=[{"user_id": "adv-1", "tipo": "advogado"}],
    )
    base.update(over)
    return base


async def _perfil(db, **over) -> JudicialIntegrationProfile:
    base = dict(
        id="perf-1", tribunal_code="TJMG", segment="estadual", degree="1", system="pje_mni",
        environment="producao", integration_type="rest", base_url="https://pje.tjmg.jus.br/mni",
        api_version="2.2.2", auth_type="oidc_client_credentials", client_id_ref="pdpj:PDPJ_CLIENT_ID",
        filing_supported=True, append_petition_supported=True, authorized=True,
        production_endpoint_verified=True, credentials_valid=True,
        homologated_at=datetime(2026, 8, 1, tzinfo=timezone.utc), status="SUPPORTED", ativo=True,
    )
    base.update(over)
    p = JudicialIntegrationProfile(**base)
    db.add(p)
    await db.commit()
    return p


class _ConectorFake:
    """Conector controlável para exercitar o orquestrador sem I/O."""
    chave = "pje_mni"
    sistema = "pje_mni"

    def __init__(self, resultado=None, erro=None, recibo=None):
        self.resultado = resultado
        self.erro = erro
        self.recibo = recibo
        self.envios = 0
        self.recibos = 0

    def capacidades(self, ctx):
        from app.services.ajuizamento.capacidades import montar_matriz
        return montar_matriz(conector=self.chave, sistema=self.sistema, ctx=ctx,
                             declaradas={"file_new_case": (EstadoCapacidade.SUPPORTED, "fake")})

    async def validate_target(self, ctx, canonico):
        return ResultadoOperacao(EstadoCapacidade.SUPPORTED, dados={"faltando": []})

    async def file_new_case(self, ctx, canonico, *, idempotency_key):
        self.envios += 1
        self.ultima_chave = idempotency_key
        if self.erro is not None:
            raise self.erro
        return self.resultado

    async def get_receipt(self, ctx, *, idempotency_key, external_protocol=None):
        self.recibos += 1
        return self.recibo or ResultadoOperacao(EstadoCapacidade.UNSUPPORTED, mensagem="sem consulta de recibo")


def _servico(db, conector=None, settings=None) -> JudicialFilingService:
    roteador = JudicialConnectorRouter({"pje_mni": conector} if conector else None)
    return JudicialFilingService(db, settings or _settings(), roteador)


async def _ate_validado(db, svc, cu, **over):
    caso = (await db.execute(select(Case).where(Case.id == "caso-1"))).scalar_one()
    f = await svc.criar(case=caso, cu=cu, dados=_dados_filing(**over))
    await db.commit()
    r = await svc.validar(f, cu=cu)
    await db.commit()
    return f, r


async def _ate_assinado(db, svc, cu, **over):
    f, r = await _ate_validado(db, svc, cu, **over)
    assert r["ready"], r["errors"]
    await svc.aprovar(f, cu=cu, confirmacao=CONFIRMACAO_REVISAO, observacoes="conferido")
    await db.commit()
    await svc.assinar(f, cu=cu, provider="registro_externo", dados={
        "certificate_subject": "CN=JOAO", "certificate_serial": "0A1B2C",
        "signed_document_hash": HASH_PDF, "algorithm": "SHA256withRSA"})
    await db.commit()
    return f


# ── Validação ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validar_monta_canonico_persiste_preflight_e_fica_pronto(db):
    dados = await _semear(db)
    svc = _servico(db)
    f, r = await _ate_validado(db, svc, dados["advogado"])
    assert f.estado == E.READY_FOR_REVIEW.value, r["errors"]
    assert r["ready"] is True and f.preflight["ready"] is True
    assert f.canonico_hash and len(f.canonico_hash) == 64
    # PII do cliente nunca em claro no snapshot persistido.
    assert CPF not in str(f.canonico) and "52998224725" not in str(f.canonico)
    transicoes = (await db.execute(select(JudicialFilingTransicao).where(
        JudicialFilingTransicao.filing_id == f.id))).scalars().all()
    assert [t.para_estado for t in transicoes] == ["DRAFT", "PREPARING", "VALIDATING", "READY_FOR_REVIEW"]


@pytest.mark.asyncio
async def test_validar_sem_polo_passivo_fica_invalid(db):
    dados = await _semear(db, com_reu=False)
    svc = _servico(db)
    f, r = await _ate_validado(db, svc, dados["advogado"])
    assert f.estado == E.INVALID.value
    assert any("Polo passivo" in e for e in r["errors"])


@pytest.mark.asyncio
async def test_validar_recusa_documento_de_outro_caso(db):
    dados = await _semear(db)
    db.add(Document(id="doc-alheio", titulo="X", filename="x.pdf", filepath="/x.pdf",
                    mimetype="application/pdf", size_bytes=1, sha256="f" * 64,
                    case_id="caso-outro", client_id="cli-outro"))
    await db.commit()
    svc = _servico(db)
    caso = dados["caso"]
    f = await svc.criar(case=caso, cu=dados["advogado"], dados=_dados_filing(
        documentos=[{"document_id": "doc-alheio", "document_type": "probatorio", "ordem": 1}]))
    await db.commit()
    with pytest.raises(AjuizamentoError, match="não pertence"):
        await svc.validar(f, cu=dados["advogado"])


@pytest.mark.asyncio
async def test_edicao_apos_validacao_volta_para_draft_e_limpa_preflight(db):
    dados = await _semear(db)
    svc = _servico(db)
    f, _ = await _ate_validado(db, svc, dados["advogado"])
    await svc.atualizar(f, cu=dados["advogado"], dados={"classe_codigo": "1116"})
    await db.commit()
    assert f.estado == E.DRAFT.value and f.preflight is None and f.classe_codigo == "1116"


# ── Revisão humana ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aprovacao_exige_confirmacao_literal(db):
    dados = await _semear(db)
    svc = _servico(db)
    f, _ = await _ate_validado(db, svc, dados["advogado"])
    with pytest.raises(AjuizamentoError, match="confirmação literal"):
        await svc.aprovar(f, cu=dados["advogado"], confirmacao="ok", observacoes=None)
    assert f.estado == E.READY_FOR_REVIEW.value
    await svc.aprovar(f, cu=dados["advogado"], confirmacao=CONFIRMACAO_REVISAO, observacoes="conferido")
    assert f.estado == E.APPROVED.value and f.aprovado_por == "adv-1"


@pytest.mark.asyncio
async def test_aprovacao_exige_peca_com_hitl_aprovado(db):
    dados = await _semear(db, peca_status=PecaStatus.rascunho)
    svc = _servico(db)
    f, _ = await _ate_validado(db, svc, dados["advogado"])
    with pytest.raises(AjuizamentoError, match="HITL"):
        await svc.aprovar(f, cu=dados["advogado"], confirmacao=CONFIRMACAO_REVISAO, observacoes=None)


@pytest.mark.asyncio
async def test_aprovacao_recusa_quando_dados_mudaram_apos_validacao(db):
    dados = await _semear(db)
    svc = _servico(db)
    f, _ = await _ate_validado(db, svc, dados["advogado"])
    # Alteração externa (parte nova) invalida o snapshot revisado.
    db.add(CaseParte(id="parte-2", case_id="caso-1", tipo="reu", nome="Outro Réu",
                     cpf_cnpj=CNPJ_OUTRO, ativo=True))
    await db.commit()
    with pytest.raises(AjuizamentoError, match="mudaram desde a validação"):
        await svc.aprovar(f, cu=dados["advogado"], confirmacao=CONFIRMACAO_REVISAO, observacoes=None)


@pytest.mark.asyncio
async def test_nao_protocola_sem_aprovacao_e_assinatura(db):
    dados = await _semear(db)
    conector = _ConectorFake(ResultadoEnvio(EstadoCapacidade.SUPPORTED, protocol_number="P1"))
    svc = _servico(db, conector)
    f, _ = await _ate_validado(db, svc, dados["advogado"])
    with pytest.raises(AjuizamentoError):
        await svc.protocolar(f, cu=dados["advogado"])
    assert conector.envios == 0


# ── Assinatura ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assinatura_invalida_nao_avanca_estado(db):
    dados = await _semear(db)
    svc = _servico(db)
    f, _ = await _ate_validado(db, svc, dados["advogado"])
    await svc.aprovar(f, cu=dados["advogado"], confirmacao=CONFIRMACAO_REVISAO, observacoes=None)
    r = await svc.assinar(f, cu=dados["advogado"], provider="registro_externo",
                          dados={"certificate_subject": "CN=X"})
    assert r["estado"] != EstadoCapacidade.SUPPORTED.value
    assert f.estado == E.APPROVED.value and f.assinatura is None


@pytest.mark.asyncio
async def test_assinatura_com_certificado_em_nuvem_fica_requires_authorization(db):
    dados = await _semear(db)
    svc = _servico(db)
    f, _ = await _ate_validado(db, svc, dados["advogado"])
    await svc.aprovar(f, cu=dados["advogado"], confirmacao=CONFIRMACAO_REVISAO, observacoes=None)
    r = await svc.assinar(f, cu=dados["advogado"], provider="psc_nuvem", dados={})
    assert r["estado"] == EstadoCapacidade.REQUIRES_AUTHORIZATION.value
    assert f.estado == E.APPROVED.value


@pytest.mark.asyncio
async def test_assinatura_registrada_marca_peticao_como_assinada(db):
    dados = await _semear(db)
    svc = _servico(db)
    f = await _ate_assinado(db, svc, dados["advogado"])
    assert f.estado == E.READY_TO_SUBMIT.value
    assert f.assinatura["certificate_serial"] == "0A1B2C"
    peticao = [d for d in f.canonico["documentos"] if d["document_type"] == "peticao_inicial"][0]
    assert peticao["signed"] is True and peticao["sha256"] == HASH_PDF


# ── Protocolo / idempotência ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_protocolo_confirmado_registra_vincula_e_cria_movimento(db):
    dados = await _semear(db)
    await _perfil(db)
    conector = _ConectorFake(ResultadoEnvio(
        EstadoCapacidade.SUPPORTED, protocol_number="PJE-99",
        cnj_number=CNJ_VALIDO, external_process_id="PJE-ID-1",
        distribution_unit="2ª Vara Cível de Betim", confirmado=True, response_hash="c" * 64))
    svc = _servico(db, conector)
    f = await _ate_assinado(db, svc, dados["advogado"])
    r = await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()

    assert f.estado == E.CONFIRMED.value and conector.envios == 1
    assert r["cnj_number"] == CNJ_VALIDO_MASCARA     # formatado
    protocolo = (await db.execute(select(JudicialProtocol))).scalars().one()
    assert protocolo.status == "CONFIRMED" and protocolo.external_protocol == "PJE-99"
    assert protocolo.request_hash == f.canonico_hash and protocolo.response_hash == "c" * 64
    # Vinculação: processo principal, peça protocolada e movimento na timeline.
    processo = (await db.execute(select(Process))).scalars().one()
    assert processo.numero_cnj == CNJ_VALIDO_MASCARA and processo.is_principal is True
    peca = (await db.execute(select(LegalDoc).where(LegalDoc.id == "peca-1"))).scalar_one()
    assert peca.status == PecaStatus.protocolada and peca.numero_protocolo == "PJE-99"
    movimento = (await db.execute(select(CaseMovimento))).scalars().one()
    assert "protocolada" in movimento.descricao and movimento.tipo == "peticao"


@pytest.mark.asyncio
async def test_reenvio_apos_protocolo_nao_duplica(db):
    dados = await _semear(db)
    await _perfil(db)
    conector = _ConectorFake(ResultadoEnvio(EstadoCapacidade.SUPPORTED, protocol_number="PJE-1",
                                            cnj_number=CNJ_VALIDO, confirmado=True))
    svc = _servico(db, conector)
    f = await _ate_assinado(db, svc, dados["advogado"])
    await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    r2 = await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    assert r2["reutilizada"] is True and conector.envios == 1
    assert len((await db.execute(select(JudicialProtocol))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_idempotency_key_e_unica_por_tentativa_e_derivada_do_hash(db):
    dados = await _semear(db)
    await _perfil(db)
    # Resposta sem protocolo/CNJ: o orquestrador marca FAILED e a próxima
    # tentativa nasce com outra idempotency_key.
    conector = _ConectorFake(ResultadoEnvio(EstadoCapacidade.SUPPORTED))
    svc = _servico(db, conector)
    f = await _ate_assinado(db, svc, dados["advogado"])
    # Resposta sem protocolo → FAILED; a próxima tentativa recebe outra chave.
    await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    chave1 = conector.ultima_chave
    f.estado = E.READY_TO_SUBMIT.value
    await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    tentativas = (await db.execute(select(JudicialFilingAttempt).order_by(
        JudicialFilingAttempt.numero))).scalars().all()
    assert [t.numero for t in tentativas] == [1, 2]
    assert len({t.idempotency_key for t in tentativas}) == 2
    assert chave1 != conector.ultima_chave
    assert all(len(t.idempotency_key) == 64 for t in tentativas)


@pytest.mark.asyncio
async def test_timeout_marca_tentativa_e_bloqueia_reenvio_cego(db):
    dados = await _semear(db)
    await _perfil(db)
    conector = _ConectorFake(erro=TimeoutConector("timeout ao entregar manifestação"))
    svc = _servico(db, conector)
    f = await _ate_assinado(db, svc, dados["advogado"])
    r = await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    assert r["timeout"] is True and f.estado == E.FAILED.value
    tentativa = (await db.execute(select(JudicialFilingAttempt))).scalars().one()
    assert tentativa.estado == "TIMEOUT"

    # Reenvio: como o conector não sabe consultar recibo, exige verificação humana.
    r2 = await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    assert r2["requer_verificacao_manual"] is True
    # Só a 1ª tentativa chegou ao tribunal; o reenvio parou na consulta do recibo.
    assert conector.recibos == 1 and conector.envios == 1


@pytest.mark.asyncio
async def test_timeout_com_recibo_remoto_recupera_protocolo_sem_reenviar(db):
    dados = await _semear(db)
    await _perfil(db)
    conector = _ConectorFake(erro=TimeoutConector("timeout"))
    svc = _servico(db, conector)
    f = await _ate_assinado(db, svc, dados["advogado"])
    await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    conector.recibo = ResultadoOperacao(EstadoCapacidade.SUPPORTED, dados={
        "protocol_number": "PJE-7", "cnj_number": CNJ_VALIDO}, response_hash="d" * 64)
    envios_antes = conector.envios
    r = await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    # Nenhum NOVO envio: o protocolo veio do recibo remoto da tentativa anterior.
    assert conector.envios == envios_antes and f.estado == E.CONFIRMED.value
    assert r["external_protocol"] == "PJE-7"


@pytest.mark.asyncio
async def test_sem_autorizacao_fica_requires_authorization_com_registro_manual(db):
    dados = await _semear(db)
    await _perfil(db, authorized=False, homologated_at=None, credentials_valid=False)
    conector = _ConectorFake(ResultadoEnvio(EstadoCapacidade.SUPPORTED, protocol_number="NUNCA"))
    svc = _servico(db, conector)
    f = await _ate_assinado(db, svc, dados["advogado"])
    r = await svc.protocolar(f, cu=dados["advogado"])
    await db.commit()
    assert f.estado == E.REQUIRES_AUTHORIZATION.value
    assert r["registro_manual_disponivel"] is True and r["requisitos_autorizacao"]
    assert conector.envios == 0
    assert (await db.execute(select(JudicialProtocol))).scalars().all() == []


@pytest.mark.asyncio
async def test_flag_desligada_impede_protocolo(db):
    dados = await _semear(db)
    await _perfil(db)
    conector = _ConectorFake(ResultadoEnvio(EstadoCapacidade.SUPPORTED, protocol_number="P"))
    svc = _servico(db, conector, settings=_settings(JUDICIAL_FILING_ENABLED=False))
    f = await _ate_assinado(db, svc, dados["advogado"])
    with pytest.raises(AjuizamentoError, match="JUDICIAL_FILING_ENABLED"):
        await svc.protocolar(f, cu=dados["advogado"])
    assert conector.envios == 0


# ── Confirmação manual ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirmar_manual_registra_protocolo_e_vincula(db):
    dados = await _semear(db)
    svc = _servico(db)
    f = await _ate_assinado(db, svc, dados["advogado"])
    r = await svc.confirmar_manual(f, cu=dados["advogado"], dados={
        "cnj_number": CNJ_VALIDO_MASCARA, "external_protocol": "PORTAL-1",
        "distribution_unit": "2ª Vara Cível", "receipt_document_id": "doc-1",
        "external_process_id": None, "protocolado_em": None})
    await db.commit()
    assert f.estado == E.CONFIRMED.value and r["cnj_number"] == CNJ_VALIDO_MASCARA
    protocolo = (await db.execute(select(JudicialProtocol))).scalars().one()
    assert protocolo.connector == "manual" and protocolo.receipt_document_id == "doc-1"
    peca = (await db.execute(select(LegalDoc).where(LegalDoc.id == "peca-1"))).scalar_one()
    assert peca.protocolo_comprovante_doc_id == "doc-1" and peca.status == PecaStatus.protocolada


@pytest.mark.asyncio
async def test_confirmar_manual_recusa_cnj_invalido_e_comprovante_alheio(db):
    dados = await _semear(db)
    svc = _servico(db)
    f = await _ate_assinado(db, svc, dados["advogado"])
    with pytest.raises(ValueError, match="CNJ inválido"):
        await svc.confirmar_manual(f, cu=dados["advogado"], dados={"cnj_number": CNJ_DV_INVALIDO})
    with pytest.raises(AjuizamentoError, match="Comprovante inválido"):
        await svc.confirmar_manual(f, cu=dados["advogado"], dados={
            "external_protocol": "P-1", "receipt_document_id": "doc-inexistente"})
    with pytest.raises(AjuizamentoError, match="número CNJ ou o número do protocolo"):
        await svc.confirmar_manual(f, cu=dados["advogado"], dados={})


# ── Sincronização ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sincronizacao_registra_evento_por_fonte(db, monkeypatch):
    dados = await _semear(db)
    svc = _servico(db, settings=_settings(DATAJUD_ENABLED=True, DATAJUD_API_KEY="k"))
    f = await _ate_assinado(db, svc, dados["advogado"])
    await svc.confirmar_manual(f, cu=dados["advogado"], dados={"cnj_number": CNJ_VALIDO_MASCARA})
    await db.commit()

    chamadas = []

    async def _sync(db_, case):
        chamadas.append(case.id)
        return 3

    async def _reconcile(self, numero, esperado):
        return ResultadoOperacao(EstadoCapacidade.SUPPORTED, dados={"encontrado": True, "divergencias": []})

    monkeypatch.setattr("app.services.datajud_service.sincronizar_caso", _sync)
    monkeypatch.setattr(
        "app.services.ajuizamento.conectores.datajud.DataJudConnector.reconcile_process", _reconcile)
    r = await svc.sincronizar(f, cu=dados["advogado"])
    await db.commit()
    assert r["movimentos_novos"] == 3 and chamadas == ["caso-1"]
    eventos = (await db.execute(select(JudicialSyncEvent))).scalars().all()
    fontes = {e.fonte: e.estado for e in eventos}
    assert fontes["datajud"] == "ok" and "pje_mni" in fontes
    assert f.estado == E.CONFIRMED.value


@pytest.mark.asyncio
async def test_sincronizacao_com_datajud_desligado_nao_falha(db):
    dados = await _semear(db)
    svc = _servico(db)
    f = await _ate_assinado(db, svc, dados["advogado"])
    await svc.confirmar_manual(f, cu=dados["advogado"], dados={"cnj_number": CNJ_VALIDO_MASCARA})
    await db.commit()
    r = await svc.sincronizar(f, cu=dados["advogado"])
    await db.commit()
    estados_fontes = {x["fonte"]: x["estado"] for x in r["fontes"]}
    assert estados_fontes["datajud"] == "desabilitado"


@pytest.mark.asyncio
async def test_cancelar_so_antes_do_protocolo(db):
    dados = await _semear(db)
    svc = _servico(db)
    f = await _ate_assinado(db, svc, dados["advogado"])
    await svc.confirmar_manual(f, cu=dados["advogado"], dados={"external_protocol": "P-1"})
    await db.commit()
    with pytest.raises(AjuizamentoError, match="já protocolado"):
        await svc.cancelar(f, cu=dados["advogado"], motivo="desistiu")
