"""Sala Jurídica Conversacional — contratos de payload e invariantes (V1).

Sem chamadas de IA nem banco: valida os schemas Pydantic (barreira 422 antes
do gateway) e as invariantes do service (mapeamento modo→task_type completo,
congelamento pós-conversão).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.legal_chat import CHAT_MODOS, SESSION_STATUS
from app.schemas.legal_chat import (
    MAX_MENSAGEM_CHARS,
    ConverterRequest,
    EstadoUpdate,
    MensagemCreate,
    SaidaAlternativaRequest,
    SessaoUpdate,
)
from app.services.legal_chat_service import MODO_INSTRUCAO, MODO_TASK_TYPE


# ── mensagens ────────────────────────────────────────────────────────────────

def test_mensagem_modo_invalido_422():
    with pytest.raises(ValidationError):
        MensagemCreate(conteudo="analise", modo="modo_inexistente")


def test_mensagem_acima_do_teto_422():
    with pytest.raises(ValidationError):
        MensagemCreate(conteudo="x" * (MAX_MENSAGEM_CHARS + 1))


def test_mensagem_vazia_422():
    with pytest.raises(ValidationError):
        MensagemCreate(conteudo="")


def test_todos_os_modos_roteiam_para_task_type():
    # Nenhum modo do seletor pode ficar sem rota no gateway (KeyError em prod).
    assert set(MODO_TASK_TYPE) == CHAT_MODOS
    assert set(MODO_INSTRUCAO) == CHAT_MODOS


# ── estado jurídico ──────────────────────────────────────────────────────────

def test_estado_chave_desconhecida_422():
    with pytest.raises(ValidationError):
        EstadoUpdate(estado={"achismos": []})


def test_estado_valor_nao_lista_422():
    with pytest.raises(ValidationError):
        EstadoUpdate(estado={"fatos": "não é lista"})


def test_estado_valido_passa():
    e = EstadoUpdate(estado={"fatos": [{"texto": "x", "classificacao": "alegado"}]})
    assert e.estado["fatos"][0]["classificacao"] == "alegado"


# ── sessão ───────────────────────────────────────────────────────────────────

def test_sessao_status_invalido_422():
    with pytest.raises(ValidationError):
        SessaoUpdate(status="status_inexistente")


def test_sessao_status_livres_aceitos():
    # Somente os status "livres" são setáveis via PATCH; os derivados têm
    # fluxos dedicados (/converter, /vincular-caso, /saida).
    livres = SESSION_STATUS - {"convertida_em_caso", "arquivada"}
    assert livres == {"em_analise", "aguardando_documentos", "pronta_para_caso"}
    for status in livres:
        assert SessaoUpdate(status=status).status == status


def test_sessao_status_derivados_rejeitados_no_patch():
    for status in ("convertida_em_caso", "arquivada"):
        with pytest.raises(ValidationError):
            SessaoUpdate(status=status)


def test_sessao_null_explicito_rejeitado():
    # {"campo": null} viraria 500 na coluna non-nullable — 422 na borda.
    for campo in ("titulo", "status", "favorita"):
        with pytest.raises(ValidationError):
            SessaoUpdate(**{campo: None})
    # Omitido continua válido (PATCH parcial).
    assert SessaoUpdate().titulo is None


# ── conversão em caso ────────────────────────────────────────────────────────

def test_converter_exige_confirmacoes_explicitas():
    with pytest.raises(ValidationError):
        ConverterRequest(
            novo_cliente_nome="Fulano", area="civel", titulo_caso="Caso X",
            advogado_responsavel_id="u1",
            confirmo_conflito_verificado=False,
            confirmo_dados_revisados=True,
        )


def test_congelamento_bloqueia_escrita():
    from datetime import datetime, timezone
    from app.models.legal_chat import LegalChatSession
    from app.services.legal_chat_service import exigir_nao_congelada

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    exigir_nao_congelada(sessao)  # sem congelamento: passa
    sessao.frozen_at = datetime.now(timezone.utc)
    with pytest.raises(HTTPException) as exc:
        exigir_nao_congelada(sessao)
    assert exc.value.status_code == 409


# ── saídas alternativas ──────────────────────────────────────────────────────

def test_descartar_sem_justificativa_422():
    with pytest.raises(ValidationError):
        SaidaAlternativaRequest(acao="descartar", justificativa="  ")


def test_descartar_justificativa_omitida_422():
    # model_validator: field_validator não roda com o campo OMITIDO do payload.
    with pytest.raises(ValidationError):
        SaidaAlternativaRequest(acao="descartar")


def test_arquivar_sem_justificativa_ok():
    assert SaidaAlternativaRequest(acao="arquivar").acao == "arquivar"


# ── vínculo a caso existente ─────────────────────────────────────────────────

def test_vincular_exige_confirmacao_explicita():
    from app.schemas.legal_chat import VincularCasoRequest

    with pytest.raises(ValidationError):
        VincularCasoRequest(case_id="c1", confirmo_dados_revisados=False)
    assert VincularCasoRequest(
        case_id="c1", confirmo_dados_revisados=True
    ).case_id == "c1"


# ── padrão obrigatório da Sala (system prompt aditivo) ───────────────────────

def test_prompt_extra_sala_registrado():
    # O bloco institucional precisa estar registrado E ser o que o service pede;
    # sem isto o orchestrator ignora a chave e a Sala perde o padrão de resposta.
    import inspect

    from app.services import legal_chat_service as svc
    from app.services.system_prompts import PROMPT_EXTRAS

    assert "sala_juridica" in PROMPT_EXTRAS
    corpo = PROMPT_EXTRAS["sala_juridica"]
    for exigencia in ("[A PREENCHER", "prescrição", "teses favoráveis E contrárias"):
        assert exigencia in corpo
    assert '"prompt_extra": "sala_juridica"' in inspect.getsource(svc.enviar_mensagem)


# ── exportação (DOCX/PDF) ────────────────────────────────────────────────────

def _sessao_exporta():
    from app.models.legal_chat import LegalChatMessage, LegalChatSession

    sessao = LegalChatSession(
        id="s1", titulo="Análise Teste", created_by="u1",
        workspace_texto="Fatos colados pelo advogado.",
    )
    msgs = [
        LegalChatMessage(id="m1", session_id="s1", autor="user",
                         modo="conversa_livre", conteudo="Analise o caso."),
        LegalChatMessage(id="m2", session_id="s1", autor="ia",
                         modo="conversa_livre", conteudo="## Resumo executivo\nX."),
    ]
    return sessao, msgs


def test_exportar_docx_gera_documento_com_conteudo():
    import io

    from docx import Document

    from app.services.legal_chat_service import exportar_docx

    sessao, msgs = _sessao_exporta()
    conteudo = exportar_docx(sessao, msgs, None)
    doc = Document(io.BytesIO(conteudo))
    textos = "\n".join(p.text for p in doc.paragraphs)
    assert "Fatos colados pelo advogado." in textos
    assert "Resumo executivo" in textos
    assert "rascunho" in textos  # aviso HITL sempre presente


def test_exportar_pdf_gera_bytes_pdf():
    from app.services.legal_chat_service import exportar_pdf

    sessao, msgs = _sessao_exporta()
    conteudo = exportar_pdf(sessao, msgs, None)
    assert conteudo.startswith(b"%PDF-")


# ── extração automática de estado (V2) ───────────────────────────────────────

async def _rodar_extracao(monkeypatch, conteudo_llm: str, custo: float = 0.0):
    from app.services import legal_chat_service as svc

    async def fake_run_ai_task(**kwargs):
        return {"conteudo": conteudo_llm, "custo_estimado_brl": custo}

    import app.services.ai.core.orchestrator as orch
    monkeypatch.setattr(orch, "run_ai_task", fake_run_ai_task)
    return await svc._extrair_estado_automatico(
        None, None, estado_atual={"fontes": []},
        pergunta="p", resposta="r",
    )


@pytest.mark.anyio
async def test_extracao_estado_json_valido(monkeypatch):
    saida, custo = await _rodar_extracao(
        monkeypatch,
        '{"fatos": [{"texto": "x", "classificacao": "alegado"}], "_resumo": "ok"}',
    )
    assert saida is not None
    assert saida["fatos"][0]["classificacao"] == "alegado"
    assert saida["_resumo"] == "ok"
    assert custo == 0


@pytest.mark.anyio
async def test_extracao_estado_json_invalido_fail_soft(monkeypatch):
    saida, _ = await _rodar_extracao(monkeypatch, "não sei responder em JSON")
    assert saida is None


@pytest.mark.anyio
async def test_extracao_estado_chave_desconhecida_fail_soft(monkeypatch):
    saida, _ = await _rodar_extracao(monkeypatch, '{"achismos": []}')
    assert saida is None


@pytest.mark.anyio
async def test_extracao_estado_devolve_custo_mesmo_em_falha(monkeypatch):
    # A 2ª chamada de IA pode cair em fallback pago: o custo nunca é perdido,
    # mesmo quando o JSON devolvido é inválido (fail-soft do estado apenas).
    from decimal import Decimal

    saida, custo = await _rodar_extracao(
        monkeypatch, "resposta sem JSON", custo=0.37
    )
    assert saida is None
    assert custo == Decimal("0.37")


# ── fakes de banco (padrão do arquivo: sem DB real) ──────────────────────────

class _Result:
    def __init__(self, itens):
        self._itens = list(itens)

    def scalars(self):
        return self

    def all(self):
        return self._itens

    def scalar_one_or_none(self):
        return self._itens[0] if self._itens else None

    def scalar_one(self):
        return self._itens[0]

    def scalar(self):
        return self._itens[0] if self._itens else None


class _FakeDB:
    """Fake mínimo de AsyncSession: roteia selects pela entidade mapeada."""

    def __init__(self, sessao=None, mensagens=(), anexos=(), estado_atual=None):
        self.sessao = sessao
        self.mensagens = list(mensagens)  # ordem cronológica
        self.anexos = list(anexos)
        self.estado_atual = estado_atual
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def scalar(self, stmt, params=None):
        # max(versao) do snapshot / agregações — fake devolve 0.
        return 0

    async def get(self, entidade, pk):
        # Só o responsável da conversão é buscado por PK: devolve advogado
        # ativo (o caminho negativo é coberto por teste próprio).
        from types import SimpleNamespace

        return SimpleNamespace(id=pk, role="advogado", is_active=True)

    async def execute(self, stmt, params=None):
        from app.models.legal_chat import (
            LegalChatAttachment,
            LegalChatMessage,
            LegalChatSession,
            LegalChatStateVersion,
        )

        descr = getattr(stmt, "column_descriptions", None)
        if not descr:  # SQL bruto (advisory lock / numeração canônica)
            return _Result([])
        entity = descr[0]["entity"]
        if entity is LegalChatMessage:
            return _Result(reversed(self.mensagens))  # created_at desc
        if entity is LegalChatAttachment:
            return _Result(self.anexos)
        if entity is LegalChatStateVersion:
            return _Result([self.estado_atual] if self.estado_atual else [])
        if entity is LegalChatSession:
            return _Result([self.sessao] if self.sessao else [])
        return _Result([])


def _user(role: str = "advogado"):
    from types import SimpleNamespace

    return SimpleNamespace(id="u1", role=role)


# ── histórico + anexos entram na mensagem ao núcleo ──────────────────────────

@pytest.mark.anyio
async def test_enviar_mensagem_inclui_historico_e_anexos(monkeypatch):
    from app.models.legal_chat import (
        LegalChatAttachment,
        LegalChatMessage,
        LegalChatSession,
    )
    from app.services import legal_chat_service as svc

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    mensagens = [
        LegalChatMessage(id="m1", session_id="s1", autor="user",
                         modo="conversa_livre", conteudo="pergunta anterior"),
        LegalChatMessage(id="m2", session_id="s1", autor="ia",
                         modo="conversa_livre", conteudo="resposta anterior"),
    ]
    anexos = [
        LegalChatAttachment(
            id="a1", session_id="s1", nome_original="contrato.pdf",
            filepath="x", size_bytes=1, sha256="h", uploaded_by="u1",
            resultado_analise={"partes": ["Fulano", "Banco X"]},
        ),
    ]
    db = _FakeDB(sessao=sessao, mensagens=mensagens, anexos=anexos)

    chamadas = []

    async def fake_run_ai_task(**kwargs):
        chamadas.append(kwargs)
        return {"conteudo": "ok", "custo_estimado_brl": 0}

    import app.services.ai.core.orchestrator as orch
    monkeypatch.setattr(orch, "run_ai_task", fake_run_ai_task)

    payload = MensagemCreate(conteudo="qual o próximo passo?")
    await svc.enviar_mensagem(db, sessao, payload, _user())

    prompt = chamadas[0]["mensagem"]  # 1ª chamada = análise principal
    assert "[HISTÓRICO DA CONVERSA]" in prompt
    assert "Advogado: pergunta anterior" in prompt
    assert "IA: resposta anterior" in prompt
    assert "[DOCUMENTOS ANEXADOS]" in prompt
    assert "contrato.pdf" in prompt
    assert "Banco X" in prompt
    # A própria pergunta nova não entra duplicada no histórico.
    assert prompt.count("qual o próximo passo?") == 1


# ── merge parcial do estado extraído ─────────────────────────────────────────

@pytest.mark.anyio
async def test_extracao_parcial_preserva_chaves_omitidas(monkeypatch):
    from decimal import Decimal

    from app.models.legal_chat import LegalChatSession, LegalChatStateVersion
    from app.services import legal_chat_service as svc

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    estado_atual = LegalChatStateVersion(
        id="v3", session_id="s1", versao=3,
        estado={
            "provas": [{"nome": "contrato", "forca": "alta"}],
            "riscos": [{"descricao": "prescrição", "nivel": "alto"}],
            "fontes": [],
        },
    )
    db = _FakeDB(sessao=sessao, estado_atual=estado_atual)

    async def fake_run_ai_task(**kwargs):
        return {"conteudo": "ok", "custo_estimado_brl": 0.05}

    async def fake_extracao(*args, **kwargs):
        # Extração devolve SÓ "fatos": provas/riscos anteriores não podem sumir.
        return (
            {"fatos": [{"texto": "x", "classificacao": "alegado"}]},
            Decimal("0.10"),
        )

    import app.services.ai.core.orchestrator as orch
    from app.core.config import get_settings
    monkeypatch.setattr(orch, "run_ai_task", fake_run_ai_task)
    monkeypatch.setattr(svc, "_extrair_estado_automatico", fake_extracao)
    monkeypatch.setattr(get_settings(), "SALA_JURIDICA_AUTO_ESTADO", True)

    payload = MensagemCreate(conteudo="analise")
    await svc.enviar_mensagem(db, sessao, payload, _user())

    versoes = [o for o in db.added if isinstance(o, LegalChatStateVersion)]
    assert len(versoes) == 1
    novo = versoes[0].estado
    assert novo["fatos"][0]["texto"] == "x"
    assert novo["provas"] == [{"nome": "contrato", "forca": "alta"}]
    assert novo["riscos"] == [{"descricao": "prescrição", "nivel": "alto"}]
    # Custo da extração somado ao total da sessão (item de auditoria de gasto).
    assert sessao.custo_ia_total == Decimal("0.15")


# ── gate de equipe jurídica (router) ─────────────────────────────────────────

@pytest.mark.anyio
async def test_gate_equipe_juridica_403_para_papeis_administrativos():
    from app.routers.legal_chat import exigir_equipe_juridica

    for role in ("financeiro", "secretaria", "cliente_externo"):
        with pytest.raises(HTTPException) as exc:
            await exigir_equipe_juridica(_user(role))
        assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_gate_equipe_juridica_aceita_equipe():
    from app.routers.legal_chat import exigir_equipe_juridica

    for role in ("advogado", "estagiario", "advogado_auxiliar", "socio"):
        user = await exigir_equipe_juridica(_user(role))
        assert user.role == role


# ── idempotência do vínculo/conversão sob lock ───────────────────────────────

@pytest.mark.anyio
async def test_vincular_sessao_ja_convertida_retorna_ja_convertido():
    from datetime import datetime, timezone

    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    # Sessão já convertida E congelada: repetir o vínculo é idempotente
    # (ja_convertido=True), não 409 de congelamento.
    sessao = LegalChatSession(
        id="s1", titulo="t", created_by="u1",
        convertido_case_id="case-antigo",
        frozen_at=datetime.now(timezone.utc),
    )
    db = _FakeDB(sessao=sessao)
    resultado = await svc.vincular_caso_existente(db, sessao, "case-novo", _user())
    assert resultado == {"case_id": "case-antigo", "ja_convertido": True}
    assert db.added == []  # nenhum registro novo


@pytest.mark.anyio
async def test_converter_sessao_ja_convertida_retorna_ja_convertido():
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    sessao = LegalChatSession(
        id="s1", titulo="t", created_by="u1", convertido_case_id="case-antigo",
    )
    db = _FakeDB(sessao=sessao)
    payload = ConverterRequest(
        novo_cliente_nome="Fulano", area="civil", titulo_caso="Caso X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    resultado = await svc.converter_em_caso(db, sessao, payload, _user())
    assert resultado == {"case_id": "case-antigo", "ja_convertido": True}
    assert db.added == []


# ── conversão popula proxima_acao (guarda G1 do caminho canônico) ────────────

@pytest.mark.anyio
async def test_converter_popula_proxima_acao_default():
    from app.models.case import Case
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    db = _FakeDB(sessao=sessao)
    payload = ConverterRequest(
        novo_cliente_nome="Fulano", area="civil", titulo_caso="Caso X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    resultado = await svc.converter_em_caso(db, sessao, payload, _user())
    assert resultado["ja_convertido"] is False
    casos = [o for o in db.added if isinstance(o, Case)]
    assert len(casos) == 1
    assert casos[0].proxima_acao == (
        "Revisar a análise convertida da Sala Jurídica e definir a próxima providência"
    )
    # Numeração no formato canônico DPT-AAAA-NNNN (alocador compartilhado).
    assert casos[0].numero_interno.startswith("DPT-")


@pytest.mark.anyio
async def test_converter_respeita_proxima_acao_informada():
    from app.models.case import Case
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    db = _FakeDB(sessao=sessao)
    payload = ConverterRequest(
        novo_cliente_nome="Fulano", area="civil", titulo_caso="Caso X",
        proxima_acao="Notificar a parte contrária",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    await svc.converter_em_caso(db, sessao, payload, _user())
    caso = next(o for o in db.added if isinstance(o, Case))
    assert caso.proxima_acao == "Notificar a parte contrária"


# ── paridade Raio-X na conversão (gates, snapshot, anexos) ───────────────────

def test_converter_request_gates_default_off():
    p = ConverterRequest(
        novo_cliente_nome="Fulano", area="civil", titulo_caso="X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    assert p.conflict_confirmed is False
    assert p.duplicate_confirmed is False
    assert p.transferir_anexos is True


def test_origem_sala_juridica_valida_no_snapshot():
    from app.models.case_intelligence import ORIGENS_SNAPSHOT
    assert "sala_juridica" in ORIGENS_SNAPSHOT


def test_nomes_partes_anexos_extrai_dedup_e_piso():
    from types import SimpleNamespace

    from app.services.legal_chat_service import _nomes_partes_anexos

    anexos = [
        SimpleNamespace(resultado_analise={"intake_result": {"partes": [
            "Banco Alfa S/A",
            {"nome": "João da Silva"},
            {"valor": "Banco Alfa S/A"},   # duplicado (case-insensitive)
            "ré",                            # abaixo do piso de 4 chars
            {"nome": {"valor": "Construtora Beta"}},
        ]}}),
        SimpleNamespace(resultado_analise={"partes": ["banco alfa s/a"]}),
        SimpleNamespace(resultado_analise=None),
    ]
    assert _nomes_partes_anexos(anexos) == [
        "Banco Alfa S/A", "João da Silva", "Construtora Beta",
    ]


@pytest.mark.anyio
async def test_converter_cria_snapshot_sala_juridica():
    from app.models.case_intelligence import CaseIntelligenceSnapshot
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    db = _FakeDB(sessao=sessao)
    payload = ConverterRequest(
        novo_cliente_nome="Fulano de Tal", area="civil", titulo_caso="Caso X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    resultado = await svc.converter_em_caso(db, sessao, payload, _user())
    snaps = [o for o in db.added if isinstance(o, CaseIntelligenceSnapshot)]
    assert len(snaps) == 1
    assert snaps[0].origem == "sala_juridica"
    assert snaps[0].versao == 1
    assert snaps[0].payload["revisao_humana_obrigatoria"] is True
    assert snaps[0].payload["sala_juridica_session_id"] == "s1"
    assert resultado["snapshot_versao"] == 1
    assert resultado["documentos_transferidos"] == []


@pytest.mark.anyio
async def test_converter_409_conflito_detectado_sem_reconhecimento(monkeypatch):
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    async def fake_preview(db, sessao, user, **kw):
        return {
            "alertas_conflito": [{
                "tipo": "parte_corresponde_a_cliente",
                "nome": "X", "mensagem": "conflito", "protegido": False,
            }],
            "clientes_possivelmente_duplicados": [],
            "casos_ativos_do_cliente": [],
            "anexos_disponiveis": [],
            "bloqueia": True,
        }

    monkeypatch.setattr(svc, "preview_conversao", fake_preview)
    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    payload = ConverterRequest(
        novo_cliente_nome="Fulano", area="civil", titulo_caso="X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    with pytest.raises(HTTPException) as ei:
        await svc.converter_em_caso(_FakeDB(sessao=sessao), sessao, payload, _user())
    assert ei.value.status_code == 409
    assert "alertas_conflito" in ei.value.detail

    # Reconhecido explicitamente → conversão prossegue.
    payload_ok = payload.model_copy(update={"conflict_confirmed": True})
    resultado = await svc.converter_em_caso(
        _FakeDB(sessao=LegalChatSession(id="s2", titulo="t", created_by="u1")),
        LegalChatSession(id="s2", titulo="t", created_by="u1"),
        payload_ok, _user(),
    )
    assert resultado["ja_convertido"] is False


@pytest.mark.anyio
async def test_converter_409_cliente_duplicado_sem_reconhecimento(monkeypatch):
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    async def fake_preview(db, sessao, user, **kw):
        return {
            "alertas_conflito": [],
            "clientes_possivelmente_duplicados": [
                {"id": "c9", "nome": "Fulano de Tal", "protegido": False},
            ],
            "casos_ativos_do_cliente": [],
            "anexos_disponiveis": [],
            "bloqueia": False,
        }

    monkeypatch.setattr(svc, "preview_conversao", fake_preview)
    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    payload = ConverterRequest(
        novo_cliente_nome="Fulano de Tal", area="civil", titulo_caso="X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    with pytest.raises(HTTPException) as ei:
        await svc.converter_em_caso(_FakeDB(sessao=sessao), sessao, payload, _user())
    assert ei.value.status_code == 409
    assert "clientes_possivelmente_duplicados" in ei.value.detail


@pytest.mark.anyio
async def test_converter_409_caso_ativo_de_cliente_existente(monkeypatch):
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    async def fake_preview(db, sessao, user, **kw):
        return {
            "alertas_conflito": [],
            "clientes_possivelmente_duplicados": [],
            "casos_ativos_do_cliente": [
                {"id": "k1", "titulo": "Caso em curso",
                 "numero_interno": "DPT-2026-0001", "protegido": False},
            ],
            "anexos_disponiveis": [],
            "bloqueia": False,
        }

    monkeypatch.setattr(svc, "preview_conversao", fake_preview)
    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    payload = ConverterRequest(
        client_id="c9", area="civil", titulo_caso="X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    with pytest.raises(HTTPException) as ei:
        await svc.converter_em_caso(_FakeDB(sessao=sessao), sessao, payload, _user())
    assert ei.value.status_code == 409
    assert "casos_ativos_do_cliente" in ei.value.detail


@pytest.mark.anyio
async def test_converter_422_anexo_sem_arquivo_fisico_nao_congela():
    from app.models.legal_chat import LegalChatAttachment, LegalChatSession
    from app.services import legal_chat_service as svc

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    anexo = LegalChatAttachment(
        id="a1", session_id="s1", nome_original="contrato.pdf",
        filepath="sala-juridica/inexistente/x.pdf", size_bytes=10,
        sha256="0" * 64, uploaded_by="u1", resultado_analise={},
    )
    db = _FakeDB(sessao=sessao, anexos=[anexo])
    payload = ConverterRequest(
        novo_cliente_nome="Fulano de Tal", area="civil", titulo_caso="X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    with pytest.raises(HTTPException) as ei:
        await svc.converter_em_caso(db, sessao, payload, _user())
    assert ei.value.status_code == 422
    assert "contrato.pdf" in str(ei.value.detail)
    # A sessão NÃO pode ter sido congelada/convertida (fica retryável).
    assert sessao.frozen_at is None
    assert sessao.convertido_case_id is None


# ── auditoria de segurança: gates de carteira e wildcards ────────────────────

def test_padrao_like_escapa_wildcards_do_input():
    """Nome com % ou _ NÃO pode virar curinga: senão o piso de 4 chars é
    contornado e a checagem ética vira oráculo de substring da base."""
    from app.services.conflito_service import _padrao_like

    assert _padrao_like("____") == "%\\_\\_\\_\\_%"
    assert _padrao_like("%Ab%") == "%\\%Ab\\%%"
    assert _padrao_like("Silva") == "%Silva%"
    # Barra invertida do input é escapada ANTES (senão desescaparia os demais).
    assert _padrao_like("a\\b") == "%a\\\\b%"


@pytest.mark.anyio
async def test_converter_com_client_id_alheio_404(monkeypatch):
    """IDOR: converter com client_id de outra carteira criaria um Case com o
    requisitante como responsável — e pode_ver_cliente passaria a conceder
    acesso permanente ao cliente por esse próprio vínculo."""
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    async def fake_preview(db, sessao, user, **kw):
        return {
            "alertas_conflito": [], "clientes_possivelmente_duplicados": [],
            "casos_ativos_do_cliente": [], "anexos_disponiveis": [],
            "bloqueia": False,
        }

    async def nega_cliente(db, user, client_id):
        raise HTTPException(404, "Cliente não encontrado")

    monkeypatch.setattr(svc, "preview_conversao", fake_preview)
    monkeypatch.setattr(svc, "obter_cliente_autorizado", nega_cliente)
    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    payload = ConverterRequest(
        client_id="cliente-de-outra-carteira", area="civil", titulo_caso="X",
        advogado_responsavel_id="u1",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )
    with pytest.raises(HTTPException) as ei:
        await svc.converter_em_caso(_FakeDB(sessao=sessao), sessao, payload, _user())
    assert ei.value.status_code == 404


def test_serializar_anexo_nao_ecoa_chaves_internas():
    """Chaves `_`-prefixadas (texto sanitizado retido p/ virar ocr_text) são
    internas por convenção do repo — nunca saem na API."""
    from app.models.legal_chat import LegalChatAttachment
    from app.services.legal_chat_service import serializar_anexo

    anexo = LegalChatAttachment(
        id="a1", session_id="s1", nome_original="x.pdf", filepath="p",
        size_bytes=1, sha256="0" * 64, uploaded_by="u1",
        resultado_analise={"tipo_documento": "contrato",
                           "_texto_sanitizado": "conteúdo integral do documento"},
    )
    out = serializar_anexo(anexo)
    assert out["resultado_analise"] == {"tipo_documento": "contrato"}
    assert "_texto_sanitizado" not in str(out)


@pytest.mark.anyio
async def test_converter_rejeita_responsavel_invalido(monkeypatch):
    """advogado_responsavel_id era str livre indo direto ao modelo: id
    inexistente virava 500 (FK) e qualquer id atribuía caso a terceiro."""
    from app.models.legal_chat import LegalChatSession
    from app.services import legal_chat_service as svc

    async def fake_preview(db, sessao, user, **kw):
        return {
            "alertas_conflito": [], "clientes_possivelmente_duplicados": [],
            "casos_ativos_do_cliente": [], "anexos_disponiveis": [],
            "bloqueia": False,
        }

    monkeypatch.setattr(svc, "preview_conversao", fake_preview)
    payload = ConverterRequest(
        novo_cliente_nome="Fulano de Tal", area="civil", titulo_caso="X",
        advogado_responsavel_id="nao-existe",
        confirmo_conflito_verificado=True, confirmo_dados_revisados=True,
    )

    class _SemUsuario(_FakeDB):
        async def get(self, entidade, pk):
            return None

    sessao = LegalChatSession(id="s1", titulo="t", created_by="u1")
    with pytest.raises(HTTPException) as ei:
        await svc.converter_em_caso(_SemUsuario(sessao=sessao), sessao, payload, _user())
    assert ei.value.status_code == 422

    # Perfil abaixo de advogado (estagiário) também é recusado.
    class _Estagiario(_FakeDB):
        async def get(self, entidade, pk):
            from types import SimpleNamespace
            return SimpleNamespace(id=pk, role="estagiario", is_active=True)

    sessao2 = LegalChatSession(id="s2", titulo="t", created_by="u1")
    with pytest.raises(HTTPException) as ei2:
        await svc.converter_em_caso(_Estagiario(sessao=sessao2), sessao2, payload, _user())
    assert ei2.value.status_code == 422


def test_ficha_confirmada_nao_e_rebaixada_por_escrita_automatica():
    """TOCTOU: confirmação humana concorrente não pode ser revertida a
    'rascunho' pelo pré-preenchimento automático (fecharia o gate da peça)."""
    import inspect

    from app.services import ficha_triagem_service as fts
    from app.routers import triagem_entrevista as te

    fonte = inspect.getsource(fts.salvar)
    assert "preservar_confirmada" in fonte
    assert 'ficha.status == "confirmada"' in fonte
    # A ponte Entrevista→Ficha precisa realmente pedir a preservação.
    assert "preservar_confirmada=True" in inspect.getsource(te._alimentar_ficha)


# ── Fatos derivados da sessão na conversão (Issue #552) ──────────────────────
# `ConverterRequest.descricao` é opcional; omiti-la criava um Case com
# `descricao_fatos` NULO, embora a sessão contivesse estado, área de trabalho e
# relato. Aqui a função DETERMINÍSTICA que deriva o texto — sem chamada de IA.

from types import SimpleNamespace  # noqa: E402

from app.services.legal_chat_service import (  # noqa: E402
    LIMITE_DESCRICAO_FATOS,
    _fatos_para_conversao,
)


def _sessao_fake(workspace=None):
    return SimpleNamespace(workspace_texto=workspace)


def _msg(autor, conteudo):
    return SimpleNamespace(autor=autor, conteudo=conteudo)


def _estado(resumo, versao=3):
    return SimpleNamespace(resumo=resumo, versao=versao)


def test_fatos_sessao_vazia_nao_fabrica_conteudo():
    """Critério 5: sessão sem nada devolve None — não string vazia, não
    placeholder. Preencher o campo com texto inventado seria pior que o NULL."""
    assert _fatos_para_conversao(_sessao_fake(), [], None) is None
    assert _fatos_para_conversao(_sessao_fake("   "), [_msg("user", "  ")], None) is None


def test_fatos_reunem_estado_workspace_e_relato_do_advogado():
    """Critério 1: estado, área de trabalho e relato entram — nessa ordem."""
    texto = _fatos_para_conversao(
        _sessao_fake("Área: negativação em 03/2026."),
        [_msg("user", "Protocolo 99887 aberto em 10/03/2026.")],
        _estado("Consumidor, dano moral presumido."),
    )
    assert "Consumidor, dano moral presumido." in texto
    assert "Área: negativação em 03/2026." in texto
    assert "Protocolo 99887 aberto em 10/03/2026." in texto
    # Critério 2: data e protocolo informados continuam localizáveis.
    assert texto.index("Consumidor") < texto.index("Área:") < texto.index("Protocolo")


def test_fatos_rotulam_a_origem_de_cada_bloco():
    """Critério 3: síntese de IA e relato do advogado não podem entrar no caso
    oficial com a mesma autoridade — alegação não vira fato comprovado."""
    texto = _fatos_para_conversao(
        _sessao_fake("Anotações."),
        [_msg("user", "Relato do cliente.")],
        _estado("Síntese automática."),
    )
    assert "[Síntese do estado jurídico da sessão (v3)" in texto
    assert "apoio de IA" in texto
    assert "[Área de trabalho do advogado]" in texto
    assert "[Relato registrado pelo advogado na sessão]" in texto


def test_fatos_ignoram_a_analise_da_ia_nas_mensagens():
    """A resposta da IA é análise, não fato. Só a mensagem do advogado entra."""
    texto = _fatos_para_conversao(
        _sessao_fake(),
        [_msg("user", "O contrato foi assinado em 2024."),
         _msg("ia", "Tese sugerida: revisional com pedido de tutela.")],
        None,
    )
    assert "O contrato foi assinado em 2024." in texto
    assert "Tese sugerida" not in texto


def test_fatos_truncam_no_limite_do_contrato():
    """Critério 6: o texto derivado não pode nascer maior do que o campo aceita
    do advogado (10.000), e o corte precisa ser visível."""
    texto = _fatos_para_conversao(_sessao_fake("x" * 40_000), [], None)
    assert len(texto) == LIMITE_DESCRICAO_FATOS
    assert texto.endswith("caracteres do contrato de conversão.")


def test_fatos_estado_sem_resumo_nao_quebra():
    """Critério 4: estado ausente ou sem resumo degrada, não estoura."""
    assert "Anotações." in _fatos_para_conversao(
        _sessao_fake("Anotações."), [], _estado(None)
    )
