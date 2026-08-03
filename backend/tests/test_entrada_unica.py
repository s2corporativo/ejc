"""Entrada Única (Bloco 3 — routers/entrada.py + services/entrada_service.py).

Cobertura pedida pela especificação:
  (a) analisar só-texto com IA indisponível → degradado, nunca 500;
  (b) criar-caso transacional — falha no meio não deixa documento vinculado
      nem caso criado;
  (c) idempotência do criar-caso (lock + batch.case_id);
  (d) gates 409 (conflito / duplicado) e 422 (responsável, documento alheio);
  (f) regressão: entrada-universal/processar continua no pipeline compartilhado.

Padrão dos vizinhos: fakes locais + aiosqlite em memória (sem Postgres).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.case import Case, CaseMovimento, CaseStatus
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.document import DocConfidencialidade, Document
from app.models.document_intake import DocumentIntakeBatch, DocumentIntakeItem
from app.models.user import User, UserRole
from app.schemas.entrada import ClienteEntrada, CriarCasoEntradaRequest
from app.services import entrada_service


def _user_ns(role: str = "advogado"):
    return SimpleNamespace(id="u1", role=role)


RELATO = (
    "Negativação indevida após quitação integral do contrato em março de 2026; "
    "a cobrança persistiu por quatro meses mesmo após reclamação formal."
)


# ── schemas (barreira 422 antes do serviço) ──────────────────────────────────

def test_criar_caso_exige_confirmacao_explicita():
    with pytest.raises(ValidationError):
        CriarCasoEntradaRequest(
            cliente={"novo_nome": "Fulano de Tal"}, area="civil",
            titulo="Caso X", advogado_responsavel_id="u1",
            confirmo_dados_revisados=False,
        )


def test_cliente_exige_exatamente_um_entre_id_e_novo_nome():
    with pytest.raises(ValidationError):
        ClienteEntrada()
    with pytest.raises(ValidationError):
        ClienteEntrada(client_id="c1", novo_nome="Fulano de Tal")
    assert ClienteEntrada(client_id="c1").client_id == "c1"
    assert ClienteEntrada(novo_nome="Fulano de Tal").novo_nome == "Fulano de Tal"


def test_gates_default_off():
    p = CriarCasoEntradaRequest(
        cliente={"novo_nome": "Fulano de Tal"}, area="civil", titulo="Caso X",
        advogado_responsavel_id="u1", confirmo_dados_revisados=True,
    )
    assert p.conflict_confirmed is False
    assert p.duplicate_confirmed is False
    assert p.documentos_ids == []


# ── (a) analisar só-texto com IA indisponível → degradado, não 500 ───────────

@pytest.mark.anyio
async def test_analisar_so_texto_com_ia_desabilitada_degrada(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "AI_ENABLED", False)

    batch = DocumentIntakeBatch(id="b1", status="processando", created_by="u1")
    proposta = await entrada_service.analisar_entrada(
        None, _user_ns(), batch=batch, files=[], texto=RELATO,
    )
    assert proposta["degradado"] is True
    assert proposta["avisos"]  # aviso honesto — não é tela de erro
    assert proposta["rascunho_id"] == "b1"
    assert proposta["fatos"] == RELATO  # o determinístico é preservado
    assert proposta["cliente"]["client_id"] is None
    assert proposta["documentos"] == []
    assert proposta["proxima_acao"]  # G1: sempre há "o que fazer agora"
    assert proposta["revisao_obrigatoria"] is True


@pytest.mark.anyio
async def test_analisar_so_texto_com_gateway_fora_degrada(monkeypatch):
    from app.core.config import get_settings
    from app.services import triagem_entrevista_service as tes

    monkeypatch.setattr(get_settings(), "AI_ENABLED", True)

    async def _fora(*args, **kwargs):
        raise tes.TriagemIndisponivelError("provider fora do ar")

    monkeypatch.setattr(tes, "analisar_relato", _fora)
    batch = DocumentIntakeBatch(id="b2", status="processando", created_by="u1")
    proposta = await entrada_service.analisar_entrada(
        None, _user_ns(), batch=batch, files=[], texto=RELATO,
    )
    assert proposta["degradado"] is True
    assert any("indisponível" in a for a in proposta["avisos"])
    assert proposta["fatos"] == RELATO


@pytest.mark.anyio
async def test_analisar_router_422_sem_texto_e_sem_arquivo():
    from app.routers.entrada import analisar

    with pytest.raises(HTTPException) as ei:
        await analisar(files=[], texto="curto demais", db=None, cu=_user_ns())
    assert ei.value.status_code == 422


# ── harness aiosqlite (padrão dos vizinhos: sem Postgres) ────────────────────

# AuditLog fica de fora: usa JSONB (Postgres-only) e não compila no sqlite —
# criar_audit_log é substituído por um coletor em memória (fixture abaixo).
_TABELAS = [
    User.__table__, Client.__table__, Case.__table__, CaseMovimento.__table__,
    Document.__table__, DocumentIntakeBatch.__table__,
    DocumentIntakeItem.__table__, Deadline.__table__,
]


@pytest.fixture
async def sessao_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=_TABELAS)
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def numeracao_fake(monkeypatch):
    # proximo_numero_interno usa pg_advisory_xact_lock (Postgres-only).
    async def _fake(db):
        return "DPT-2026-0001"
    monkeypatch.setattr(entrada_service, "proximo_numero_interno", _fake)


@pytest.fixture
def auditoria_fake(monkeypatch):
    """AuditLog usa JSONB (Postgres-only): coletor em memória no lugar,
    preservando a asserção de que a trilha É gravada na mesma transação."""
    registros: list[tuple] = []

    async def _fake(db, user_id, user_role, acao, entidade,
                    registro_id=None, detalhes=None, **kw):
        registros.append((acao, entidade, registro_id, detalhes))

    monkeypatch.setattr(entrada_service, "criar_audit_log", _fake)
    return registros


async def _semear(db) -> User:
    """Advogado ativo + rascunho da Entrada Única com 1 documento no lote."""
    u = User(id="u1", email="adv@teste.adv.br", hashed_password="h",
             full_name="Dr. Teste", role=UserRole.advogado, is_active=True)
    batch = DocumentIntakeBatch(
        id="b1", status="concluido", created_by="u1", document_count=1,
        resultado={"entrada_unica": {"rascunho_id": "b1"}},
    )
    doc = Document(id="d1", titulo="Comprovante de pagamento",
                   filename="comprovante.pdf", filepath="2026/08/d1.pdf",
                   confidencialidade=DocConfidencialidade.normal)
    item = DocumentIntakeItem(
        id="i1", batch_id="b1", document_id="d1", filename="comprovante.pdf",
        original_filename="comprovante.pdf", extension=".pdf",
        size_bytes=10, sha256="0" * 64,
    )
    db.add_all([u, batch, doc, item])
    await db.commit()
    return u


def _payload(**kw) -> CriarCasoEntradaRequest:
    base = dict(
        cliente={"novo_nome": "Fulano de Tal"}, area="civil",
        titulo="Negativação indevida — Fulano de Tal",
        fatos="Fatos revisados na conferência.",
        parte_contraria=None, documentos_ids=["d1"],
        advogado_responsavel_id="u1", confirmo_dados_revisados=True,
    )
    base.update(kw)
    return CriarCasoEntradaRequest(**base)


# ── (b) transacionalidade: falha no meio não persiste NADA ───────────────────

@pytest.mark.anyio
async def test_criar_caso_falha_no_meio_nao_deixa_rastro(
    sessao_db, numeracao_fake, monkeypatch,
):
    user = await _semear(sessao_db)

    async def _explode(*args, **kwargs):
        raise RuntimeError("falha simulada no meio da transação")

    # O AuditLog é o ÚLTIMO passo: quando ele falha, cliente, caso, vínculo de
    # documento e prazo já foram adicionados — nada disso pode sobreviver.
    monkeypatch.setattr(entrada_service, "criar_audit_log", _explode)
    payload = _payload(prazo={"titulo": "Prazo de defesa", "data": date(2026, 9, 1)})
    with pytest.raises(RuntimeError):
        await entrada_service.criar_caso_do_rascunho(sessao_db, user, "b1", payload)
    await sessao_db.rollback()

    assert (await sessao_db.execute(select(Case))).scalars().all() == []
    assert (await sessao_db.execute(select(Client))).scalars().all() == []
    assert (await sessao_db.execute(select(Deadline))).scalars().all() == []
    doc = await sessao_db.get(Document, "d1")
    assert doc.case_id is None and doc.client_id is None
    batch = await sessao_db.get(DocumentIntakeBatch, "b1")
    assert batch.case_id is None  # rascunho segue reutilizável


# ── (c) idempotência + efeitos completos do caminho feliz ────────────────────

@pytest.mark.anyio
async def test_criar_caso_feliz_e_idempotente(sessao_db, numeracao_fake, auditoria_fake):
    user = await _semear(sessao_db)
    payload = _payload(prazo={"titulo": "Prazo de defesa", "data": date(2026, 9, 1)})

    r1 = await entrada_service.criar_caso_do_rascunho(sessao_db, user, "b1", payload)
    await sessao_db.commit()

    assert r1["ja_convertido"] is False
    assert r1["numero_interno"] == "DPT-2026-0001"
    assert r1["documentos_vinculados"] == 1
    assert r1["deadline_id"]

    caso = await sessao_db.get(Case, r1["case_id"])
    # Transição automática NA MESMA transação: documento vinculado ⇒ em_instrucao
    assert caso.status == CaseStatus.em_instrucao
    assert caso.proxima_acao  # G1
    assert caso.descricao_fatos == "Fatos revisados na conferência."

    doc = await sessao_db.get(Document, "d1")
    assert doc.case_id == caso.id and doc.client_id == r1["client_id"]

    prazo = await sessao_db.get(Deadline, r1["deadline_id"])
    assert prazo.case_id == caso.id
    assert prazo.origem == "entrada_unica"
    assert prazo.responsavel_id == "u1"  # default: responsável do caso

    movimentos = (await sessao_db.execute(select(CaseMovimento))).scalars().all()
    descricoes = " | ".join(m.descricao for m in movimentos)
    assert "Entrada Única" in descricoes                 # movimento de abertura
    assert "avançado automaticamente para em_instrucao" in descricoes
    assert auditoria_fake and auditoria_fake[0][0] == "ENTRADA_UNICA_CRIAR_CASO"

    # Segundo clique no botão: nada novo é criado.
    r2 = await entrada_service.criar_caso_do_rascunho(sessao_db, user, "b1", _payload())
    assert r2 == {"case_id": r1["case_id"], "ja_convertido": True}
    assert len((await sessao_db.execute(select(Case))).scalars().all()) == 1
    assert len((await sessao_db.execute(select(Client))).scalars().all()) == 1


# ── (d) gates de servidor ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_criar_caso_409_conflito_sem_reconhecimento(
    sessao_db, numeracao_fake, auditoria_fake, monkeypatch,
):
    user = await _semear(sessao_db)

    async def _com_conflito(db, u, **kw):
        return [{
            "tipo": "CONFLITO_parte_contraria_eh_cliente", "nome": "Banco X",
            "mensagem": "conflito potencial grave", "protegido": False,
        }]

    monkeypatch.setattr(entrada_service, "analisar_conflito", _com_conflito)
    with pytest.raises(HTTPException) as ei:
        await entrada_service.criar_caso_do_rascunho(sessao_db, user, "b1", _payload())
    assert ei.value.status_code == 409
    assert "alertas_conflito" in ei.value.detail

    # Reconhecido explicitamente → criação prossegue.
    r = await entrada_service.criar_caso_do_rascunho(
        sessao_db, user, "b1", _payload(conflict_confirmed=True),
    )
    assert r["ja_convertido"] is False


@pytest.mark.anyio
async def test_criar_caso_409_cliente_possivelmente_duplicado(
    sessao_db, numeracao_fake, auditoria_fake,
):
    user = await _semear(sessao_db)
    sessao_db.add(Client(id="c-dup", nome="Fulano de Tal", responsavel_id="u1"))
    await sessao_db.commit()

    with pytest.raises(HTTPException) as ei:
        await entrada_service.criar_caso_do_rascunho(sessao_db, user, "b1", _payload())
    assert ei.value.status_code == 409
    assert "clientes_possivelmente_duplicados" in ei.value.detail

    r = await entrada_service.criar_caso_do_rascunho(
        sessao_db, user, "b1", _payload(duplicate_confirmed=True),
    )
    assert r["ja_convertido"] is False


@pytest.mark.anyio
async def test_criar_caso_422_responsavel_nao_advogado(sessao_db, numeracao_fake):
    user = await _semear(sessao_db)
    sessao_db.add(User(id="u2", email="est@teste.adv.br", hashed_password="h",
                       full_name="Estagiário", role=UserRole.estagiario,
                       is_active=True))
    await sessao_db.commit()

    with pytest.raises(HTTPException) as ei:
        await entrada_service.criar_caso_do_rascunho(
            sessao_db, user, "b1", _payload(advogado_responsavel_id="u2"),
        )
    assert ei.value.status_code == 422

    with pytest.raises(HTTPException) as ei2:
        await entrada_service.criar_caso_do_rascunho(
            sessao_db, user, "b1", _payload(advogado_responsavel_id="nao-existe"),
        )
    assert ei2.value.status_code == 422


@pytest.mark.anyio
async def test_criar_caso_422_documento_que_nao_e_do_rascunho(
    sessao_db, numeracao_fake,
):
    user = await _semear(sessao_db)
    # Documento real, mas de OUTRO lote — não pode ser vinculado por aqui.
    sessao_db.add(Document(id="d-alheio", titulo="Doc alheio",
                           filename="x.pdf", filepath="2026/08/x.pdf"))
    await sessao_db.commit()

    with pytest.raises(HTTPException) as ei:
        await entrada_service.criar_caso_do_rascunho(
            sessao_db, user, "b1", _payload(documentos_ids=["d1", "d-alheio"]),
        )
    assert ei.value.status_code == 422
    doc = await sessao_db.get(Document, "d-alheio")
    assert doc.case_id is None


@pytest.mark.anyio
async def test_criar_caso_404_rascunho_inexistente_e_403_rascunho_alheio(
    sessao_db, numeracao_fake,
):
    user = await _semear(sessao_db)
    with pytest.raises(HTTPException) as ei:
        await entrada_service.criar_caso_do_rascunho(
            sessao_db, user, "nao-existe", _payload(),
        )
    assert ei.value.status_code == 404

    outro = User(id="u9", email="outro@teste.adv.br", hashed_password="h",
                 full_name="Outro Advogado", role=UserRole.advogado,
                 is_active=True)
    sessao_db.add(outro)
    await sessao_db.commit()
    with pytest.raises(HTTPException) as ei2:
        await entrada_service.criar_caso_do_rascunho(sessao_db, outro, "b1", _payload())
    assert ei2.value.status_code == 403


# ── (f) regressão: entrada-universal/processar segue o mesmo pipeline ────────

def test_processar_delegou_para_o_nucleo_compartilhado():
    import inspect

    from app.routers import entrada_universal as eu

    fonte = inspect.getsource(eu.processar)
    assert "ingerir_arquivos_lote(" in fonte
    # A Entrada Única consome o MESMO núcleo (sem duplicação de pipeline).
    assert "ingerir_arquivos_lote" in inspect.getsource(
        entrada_service.analisar_entrada
    )


@pytest.mark.anyio
async def test_ingerir_arquivos_lote_mantem_limite_de_bytes(monkeypatch):
    from app.routers import entrada_universal as eu

    monkeypatch.setattr(eu, "MAX_BYTES_LOTE", 10)

    class _Arq:
        filename = "relato.txt"
        content_type = "text/plain"

        async def read(self):
            return b"x" * 11

    batch = DocumentIntakeBatch(id="b9", status="processando", created_by="u1")
    with pytest.raises(HTTPException) as ei:
        await eu.ingerir_arquivos_lote(
            None, _user_ns(), batch=batch, files=[_Arq()],
            conf=DocConfidencialidade.normal,
        )
    assert ei.value.status_code == 413
