"""Núcleo de ajuizamento — contrato dos conectores, TPU, perfis (SSRF) e assinatura.

Nenhum teste faz I/O real: os transportes HTTP são injetados como fakes e o
SOAP nunca é instanciado. Cobre:

  - contrato da interface única (operação não oferecida → UNSUPPORTED sem I/O);
  - PDPJ: mapeamento documentado, estado do provedor OIDC (sem credencial →
    REQUIRES_AUTHORIZATION sem chamada remota), token (obtenção, cache,
    expiração, recusa) e leitura do callback oficial;
  - PJe/MNI: URL montada a partir do perfil (nunca fixa), versões suportadas,
    envio com token, resposta incompleta, timeout;
  - eproc: sempre CONDITIONAL/REQUIRES_AUTHORIZATION, nunca inventa endpoint;
  - DataJud: leitura/reconciliação e recusa de qualquer escrita;
  - perfis: guarda anti-SSRF da base_url e cálculo de status;
  - TpuService: normalização do SGT e estado CONDITIONAL da sincronização;
  - assinatura: registro externo (hash confere) e provedores dependentes de
    credencial.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.ajuizamento import assinatura as assinatura_mod
from app.services.ajuizamento import perfis as perfis_service
from app.services.ajuizamento.canonico import (
    CanonicalJudicialCase, DocumentoCanonico, Endereco, Identificacao, Parte, Processo,
    Representacao, Assunto,
)
from app.services.ajuizamento.capacidades import ContextoConector, EstadoCapacidade
from app.services.ajuizamento.conectores.base import ErroConector, TimeoutConector
from app.services.ajuizamento.conectores.datajud import DataJudConnector
from app.services.ajuizamento.conectores.eproc import EprocConnector
from app.services.ajuizamento.conectores.pdpj import (
    PDPJConnector, PdpjAuthError, PdpjAuthProvider, PdpjFilingResult, SSO_TOKEN_URLS, mapear_para_pdpj,
)
from app.services.ajuizamento.conectores.pje_mni import (
    MniClient, MniRestTransport, PJeMniConnector, VERSOES_MNI_SUPORTADAS, mapear_para_mni,
)
from app.services.ajuizamento.conectores.roteador import JudicialConnectorRouter, SistemaNaoSuportado
from app.services.ajuizamento.tpu_service import TpuService, TpuTipoInvalido, _normalizar_item_sgt

CPF = "529.982.247-25"
CNPJ = "11.222.333/0001-81"


def _run(coro):
    return asyncio.run(coro)


def _settings(**over) -> Settings:
    base = dict(_env_file=None, APP_ENV="development")
    base.update(over)
    return Settings(**base)


def _perfil(**over):
    base = dict(
        id="perf-1", tribunal_code="TJMG", tribunal_nome="TJMG", segment="estadual", degree="1",
        system="pje_mni", environment="producao", integration_type="rest",
        base_url="https://pje.tjmg.jus.br/mni-client", api_version="2.2.2", auth_type="oidc_client_credentials",
        client_id_ref="pdpj:PDPJ_CLIENT_ID", certificate_ref=None, certificate_required=False,
        filing_supported=True, append_petition_supported=True, process_query_supported=True,
        movement_query_supported=True, document_download_supported=True, notice_query_supported=True,
        callback_supported=False, authorized=True, production_endpoint_verified=True,
        credentials_valid=True, homologation_checklist={"id_sistema_destino": "TJMG"},
        homologated_at=datetime(2026, 8, 1, tzinfo=timezone.utc), status="SUPPORTED",
        documentation_url="https://docs.pje.jus.br/", ativo=True,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc), updated_at=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    base.update(over)
    return SimpleNamespace(**base)


def _canonico() -> CanonicalJudicialCase:
    endereco = Endereco(cep="32600-000", logradouro="Rua A", numero="10", bairro="Centro",
                        municipio="Betim", uf="MG")
    return CanonicalJudicialCase(
        identificacao=Identificacao(
            ejc_id="fil-1", case_id="caso-1", client_id="cli-1", tribunal="TJMG", segmento="estadual",
            grau="1", sistema="pje_mni", jurisdicao="Betim", codigo_localidade="3106705",
            competencia="Cível", competencia_codigo="1", unidade_judicial="2ª Vara", ambiente="producao"),
        processo=Processo(classe_codigo="7", classe_nome="Procedimento Comum Cível",
                          assuntos=(Assunto("10375", "Dano Moral", True),), valor_causa=Decimal("15000.00"),
                          nivel_sigilo=0, gratuidade=True, tutela=True, prioridade="idoso",
                          caracteristicas={"fundamento_tutela": "risco"}),
        partes=(
            Parte(origem_id="cli-1", origem="client", polo="ativo", tipo_pessoa="fisica",
                  nome="Maria da Silva", documento=CPF, nascimento=date(1985, 3, 2), endereco=endereco),
            Parte(origem_id="p-1", origem="case_parte", polo="passivo", tipo_pessoa="juridica",
                  nome="Empresa XPTO LTDA", documento=CNPJ),
        ),
        representacao=(Representacao(advogado_id="adv-1", nome="Dr. João", oab_numero="123456",
                                     oab_uf="MG", documento=CPF, procuracao_id="proc-1"),),
        documentos=(DocumentoCanonico(document_id="peca-1", origem="legal_doc", file_name="inicial.pdf",
                                      mime_type="application/pdf", size=2048, sha256="b" * 64,
                                      document_type="peticao_inicial", signed=True, ordem=0),),
    )


class _Resp:
    def __init__(self, status_code=200, corpo=None):
        self.status_code = status_code
        self._corpo = corpo if corpo is not None else {}
        self.content = b"x"

    def json(self):
        return self._corpo


class _Transporte:
    """Fake de httpx.AsyncClient (só .post)."""

    def __init__(self, resposta=None, erro: Exception | None = None):
        self.resposta = resposta
        self.erro = erro
        self.chamadas: list[tuple] = []

    async def post(self, url, **kw):
        self.chamadas.append((url, kw))
        if self.erro is not None:
            raise self.erro
        return self.resposta


# ── Interface única ──────────────────────────────────────────────────────────

def test_operacao_nao_oferecida_responde_unsupported_sem_io():
    ctx = ContextoConector(settings=_settings(), perfil=None)
    r = _run(DataJudConnector().sign(ctx, document_hash="a" * 64))
    assert r.estado == EstadoCapacidade.UNSUPPORTED


def test_roteador_resolve_todos_os_conectores_e_recusa_sistema_desconhecido():
    r = JudicialConnectorRouter()
    assert set(r.chaves) == {"pdpj", "pje_mni", "eproc", "datajud"}
    with pytest.raises(SistemaNaoSuportado):
        r.conector("sistema_inexistente")
    with pytest.raises(SistemaNaoSuportado):
        r.conector(None)


def test_roteador_credencial_disponivel_so_verifica_presenca():
    r = JudicialConnectorRouter()
    s = _settings(PDPJ_CLIENT_ID="id", PDPJ_CLIENT_SECRET="segredo")
    assert r.credencial_disponivel(s, None, "pdpj") is True
    assert r.credencial_disponivel(_settings(), None, "pdpj") is False
    assert r.credencial_disponivel(_settings(), _perfil(client_id_ref=None, certificate_ref=None), "eproc") is False


# ── PDPJ ─────────────────────────────────────────────────────────────────────

def test_pdpj_mapeamento_usa_campos_documentados_e_marca_pendencia():
    p = mapear_para_pdpj(_canonico())
    db = p.dadosBasicos
    assert db["classeProcessual"] == 7 and db["codigoLocalidade"] == 3106705
    assert db["valorCausa"] == 15000.0 and db["nivelSigilo"] == 0
    assert db["assistenciaJudiciaria"] is True and db["pedidoLiminarAntecipacaoTutela"] is True
    assert db["assuntos"] == [{"codigoNacional": 10375, "principal": True}]
    polos = {x["polo"] for x in db["polo"]}
    assert polos == {"AT", "PA"}
    ativo = [x for x in db["polo"] if x["polo"] == "AT"][0]["parte"][0]
    assert ativo["tipoPessoa"] == "FISICA" and ativo["numeroDocumentoPrincipal"] == "52998224725"
    assert ativo["advogado"][0]["numeroOAB"] == "123456"
    assert p.documentos[0]["tipoDocumento"] == 58
    # O endpoint de envio não é público: o mapeamento nasce NÃO confirmado.
    assert p.mapeamento_confirmado is False


def test_pdpj_auth_sem_credencial_nao_faz_chamada_remota():
    transporte = _Transporte(_Resp(200, {"access_token": "x", "expires_in": 60}))
    auth = PdpjAuthProvider(_settings(PDPJ_INTEGRATION_ENABLED=True), transporte=transporte)
    estado, motivo = auth.estado()
    assert estado == EstadoCapacidade.REQUIRES_AUTHORIZATION and "integracaopdpj@cnj.jus.br" in motivo
    with pytest.raises(PdpjAuthError):
        _run(auth.obter_token())
    assert transporte.chamadas == []


def test_pdpj_token_usa_endpoint_oficial_e_cacheia_ate_expirar():
    transporte = _Transporte(_Resp(200, {"access_token": "tok", "expires_in": 300,
                                         "refresh_token": "r", "token_type": "bearer", "scope": "profile email"}))
    auth = PdpjAuthProvider(_settings(PDPJ_INTEGRATION_ENABLED=True, PDPJ_CLIENT_ID="cid",
                                      PDPJ_CLIENT_SECRET="sec", PDPJ_ENVIRONMENT="producao"), transporte=transporte)
    t1 = _run(auth.obter_token())
    t2 = _run(auth.obter_token())
    assert t1 is t2 and t1.access_token == "tok"
    assert len(transporte.chamadas) == 1
    url, kw = transporte.chamadas[0]
    assert url == SSO_TOKEN_URLS["producao"]
    assert kw["data"]["grant_type"] == "client_credentials"
    assert auth.header_autorizacao(t1) == {"Authorization": "Bearer tok"}


def test_pdpj_token_expirado_e_renovado():
    transporte = _Transporte(_Resp(200, {"access_token": "tok", "expires_in": 0}))
    auth = PdpjAuthProvider(_settings(PDPJ_INTEGRATION_ENABLED=True, PDPJ_CLIENT_ID="cid",
                                      PDPJ_CLIENT_SECRET="sec"), transporte=transporte)
    _run(auth.obter_token())
    _run(auth.obter_token())
    assert len(transporte.chamadas) == 2


def test_pdpj_token_recusado_nao_vaza_corpo():
    transporte = _Transporte(_Resp(401, {"error": "invalid_client", "client_id": "cid"}))
    auth = PdpjAuthProvider(_settings(PDPJ_INTEGRATION_ENABLED=True, PDPJ_CLIENT_ID="cid",
                                      PDPJ_CLIENT_SECRET="sec"), transporte=transporte)
    with pytest.raises(PdpjAuthError) as exc:
        _run(auth.obter_token())
    assert "cid" not in str(exc.value) and "401" in str(exc.value)


def test_pdpj_ambiente_invalido_cai_para_homologacao():
    auth = PdpjAuthProvider(_settings(PDPJ_ENVIRONMENT="qualquer"))
    assert auth.ambiente == "homologacao" and auth.token_url == SSO_TOKEN_URLS["homologacao"]


def test_pdpj_file_new_case_e_requires_authorization_sem_chamada():
    conector = PDPJConnector()
    ctx = ContextoConector(settings=_settings(PDPJ_INTEGRATION_ENABLED=True, PDPJ_CLIENT_ID="c",
                                              PDPJ_CLIENT_SECRET="s"),
                           perfil=_perfil(system="pdpj"), credencial_disponivel=True)
    r = _run(conector.file_new_case(ctx, _canonico(), idempotency_key="k1"))
    assert r.estado == EstadoCapacidade.REQUIRES_AUTHORIZATION
    assert r.protocol_number is None and r.dados.get("payload_hash")


def test_pdpj_callback_oficial_vira_resultado_estruturado():
    corpo = {"protocoloPortal": "PP-1", "protocolo": "2026.0001", "dataHora": "05/09/2026 10:20:30",
             "sucesso": True, "idOrgaoDistribuido": 4321,
             "numeroProcesso": "50012345620268130024", "erros": []}
    r = PdpjFilingResult.de_callback(corpo)
    assert r.sucesso and r.protocol_number == "2026.0001" and r.cnj_number == "50012345620268130024"
    assert r.distribution_unit == "4321" and r.raw_response_hash and len(r.raw_response_hash) == 64
    saida = _run(PDPJConnector().receive_callback(
        ContextoConector(settings=_settings(), perfil=None), corpo))
    assert saida.estado == EstadoCapacidade.SUPPORTED
    assert saida.dados["cnj_number"] == "50012345620268130024"


def test_pdpj_callback_com_erros_nao_e_sucesso():
    r = PdpjFilingResult.de_callback({"sucesso": False, "erros": ["classe inválida"]})
    assert r.sucesso is False and r.erros == ["classe inválida"]


# ── PJe / MNI ────────────────────────────────────────────────────────────────

def test_mni_url_vem_do_perfil_e_versao_e_validada():
    t = MniRestTransport("https://pje.tjmg.jus.br/mni-client/", "2.2.2", 10.0)
    assert t.url_manifestacao == "https://pje.tjmg.jus.br/mni-client/api/2.2.2/manifestacao"
    with pytest.raises(ValueError):
        MniRestTransport("https://x.jus.br", "9.9.9", 10.0)
    assert VERSOES_MNI_SUPORTADAS == ("2.2.2", "2.2.3", "3.0.0")


def test_mni_mapeamento_preenche_dados_basicos_e_polos():
    m = mapear_para_mni(_canonico(), id_sistema_destino="TJMG", versao="2.2.2")
    assert m.dadosBasicos["classeProcessual"] == "7"
    assert m.dadosBasicos["assunto"] == [{"codigoNacional": "10375", "principal": True}]
    nomes = {p["nome"] for p in [x["parte"][0]["pessoa"] for x in m.dadosBasicos["polo"]]}
    assert nomes == {"Maria da Silva", "Empresa XPTO LTDA"}
    params = {p["nome"]: p["valor"] for p in m.dadosBasicos["outroParametro"]}
    assert params["assistenciaJudiciaria"] == "true" and params["pedidoLiminarAntecipacaoTutela"] == "true"
    assert m.to_dict()["idSistemaDestino"] == "TJMG"


def _ctx_mni(**over):
    s = _settings(PJE_MNI_ENABLED=True, PDPJ_CLIENT_ID="c", PDPJ_CLIENT_SECRET="s", **over.pop("settings", {}))
    return ContextoConector(settings=s, perfil=over.pop("perfil", _perfil()), credencial_disponivel=True)


def _conector_mni(resposta=None, erro=None, token="tok"):
    transporte = _Transporte(resposta, erro)
    rest = MniRestTransport("https://pje.tjmg.jus.br/mni-client", "2.2.2", 5.0, transporte=transporte)
    auth = PdpjAuthProvider(_settings(PDPJ_INTEGRATION_ENABLED=True, PDPJ_CLIENT_ID="c", PDPJ_CLIENT_SECRET="s"),
                            transporte=_Transporte(_Resp(200, {"access_token": token, "expires_in": 300})))
    return PJeMniConnector(cliente=MniClient(rest=rest), auth=auth), transporte


def test_mni_envio_bem_sucedido_devolve_protocolo_e_cnj():
    conector, transporte = _conector_mni(_Resp(200, {
        "sucesso": True, "protocoloRecebimento": "PJE-99",
        "numeroProcesso": "50012345620268130024", "recibo": {"hash": "abc"}}))
    r = _run(conector.file_new_case(_ctx_mni(), _canonico(), idempotency_key="k1"))
    assert r.ok and r.protocol_number == "PJE-99" and r.cnj_number == "50012345620268130024"
    assert r.confirmado is True and r.receipt == {"hash": "abc"} and r.response_hash
    url, kw = transporte.chamadas[0]
    assert url.endswith("/api/2.2.2/manifestacao")
    assert kw["headers"]["Authorization"] == "Bearer tok"
    assert kw["headers"]["Idempotency-Key"] == "k1"


def test_mni_resposta_incompleta_nao_vira_protocolo():
    conector, _ = _conector_mni(_Resp(200, {"sucesso": False, "mensagem": "faltou classe"}))
    r = _run(conector.file_new_case(_ctx_mni(), _canonico(), idempotency_key="k1"))
    assert r.estado == EstadoCapacidade.CONDITIONAL
    assert r.dados.get("resposta_incompleta") is True and r.protocol_number is None


def test_mni_timeout_propaga_como_timeout_conector():
    import httpx
    conector, _ = _conector_mni(erro=httpx.TimeoutException("timeout"))
    with pytest.raises(TimeoutConector):
        _run(conector.file_new_case(_ctx_mni(), _canonico(), idempotency_key="k1"))


def test_mni_http_erro_vira_erro_conector_sem_corpo():
    conector, _ = _conector_mni(_Resp(500, {"detalhe": "stacktrace secreto"}))
    with pytest.raises(ErroConector) as exc:
        _run(conector.file_new_case(_ctx_mni(), _canonico(), idempotency_key="k1"))
    assert "stacktrace" not in str(exc.value) and "500" in str(exc.value)


def test_mni_sem_flag_ou_sem_perfil_bloqueia_antes_do_envio():
    conector, transporte = _conector_mni(_Resp(200, {"sucesso": True, "protocoloRecebimento": "X"}))
    ctx = ContextoConector(settings=_settings(PJE_MNI_ENABLED=False), perfil=_perfil(), credencial_disponivel=True)
    r = _run(conector.file_new_case(ctx, _canonico(), idempotency_key="k1"))
    assert r.estado in (EstadoCapacidade.CONDITIONAL, EstadoCapacidade.REQUIRES_AUTHORIZATION)
    assert transporte.chamadas == []

    ctx_sem_perfil = ContextoConector(settings=_settings(PJE_MNI_ENABLED=True), perfil=None, credencial_disponivel=False)
    r2 = _run(conector.file_new_case(ctx_sem_perfil, _canonico(), idempotency_key="k1"))
    assert r2.estado == EstadoCapacidade.REQUIRES_AUTHORIZATION
    assert transporte.chamadas == []


def test_mni_perfil_nao_homologado_nao_envia():
    conector, transporte = _conector_mni(_Resp(200, {"sucesso": True, "protocoloRecebimento": "X"}))
    ctx = _ctx_mni(perfil=_perfil(homologated_at=None))
    r = _run(conector.file_new_case(ctx, _canonico(), idempotency_key="k1"))
    assert r.estado == EstadoCapacidade.REQUIRES_AUTHORIZATION and transporte.chamadas == []


# ── eproc ────────────────────────────────────────────────────────────────────

def test_eproc_nunca_inventa_endpoint():
    conector = EprocConnector()
    ctx = ContextoConector(settings=_settings(EPROC_INTEGRATION_ENABLED=True), perfil=None, credencial_disponivel=False)
    caps = conector.capacidades(ctx)
    assert caps.estado("file_new_case") == EstadoCapacidade.REQUIRES_AUTHORIZATION
    r = _run(conector.file_new_case(ctx, _canonico(), idempotency_key="k"))
    assert r.estado == EstadoCapacidade.REQUIRES_AUTHORIZATION


def test_eproc_com_perfil_homologado_ainda_exige_contrato_do_tribunal():
    conector = EprocConnector()
    perfil = _perfil(system="eproc", documentation_url="https://eproc.trf6.jus.br/docs")
    ctx = ContextoConector(settings=_settings(EPROC_INTEGRATION_ENABLED=True), perfil=perfil,
                           credencial_disponivel=True)
    r = _run(conector.file_new_case(ctx, _canonico(), idempotency_key="k"))
    assert r.estado == EstadoCapacidade.REQUIRES_AUTHORIZATION
    assert "não confirmado" in r.mensagem


# ── DataJud ──────────────────────────────────────────────────────────────────

def test_datajud_nao_protocola_nem_valida_destino():
    conector = DataJudConnector()
    ctx = ContextoConector(settings=_settings(DATAJUD_ENABLED=True, DATAJUD_API_KEY="k"), perfil=None,
                           credencial_disponivel=True)
    caps = conector.capacidades(ctx)
    assert caps.estado("file_new_case") == EstadoCapacidade.UNSUPPORTED
    assert caps.estado("append_petition") == EstadoCapacidade.UNSUPPORTED
    assert caps.estado("read_notices") == EstadoCapacidade.UNSUPPORTED
    assert caps.estado("read_process") == EstadoCapacidade.SUPPORTED
    r = _run(conector.file_new_case(ctx, _canonico(), idempotency_key="k"))
    assert r.estado == EstadoCapacidade.UNSUPPORTED
    assert _run(conector.validate_target(ctx, _canonico())).estado == EstadoCapacidade.UNSUPPORTED


def test_datajud_numero_invalido_nao_chama_servico(monkeypatch):
    chamou = []

    async def _nao_chamar(_):
        chamou.append(1)

    monkeypatch.setattr("app.services.datajud_service.consultar_processo", _nao_chamar)
    r = _run(DataJudConnector().find_process("123"))
    assert r.estado == EstadoCapacidade.UNSUPPORTED and chamou == []


def test_datajud_reconciliacao_aponta_divergencia(monkeypatch):
    async def _fake(numero):
        return {"classe": "Procedimento Comum Cível", "orgao": "1ª Vara Cível de Betim", "movimentos": [{"data": "2026-09-01"}]}

    monkeypatch.setattr("app.services.datajud_service.consultar_processo", _fake)
    r = _run(DataJudConnector().reconcile_process("5001234-56.2026.8.13.0024",
                                                 {"classe": "Execução Fiscal", "orgao": "1ª Vara Cível"}))
    assert r.ok and r.dados["divergencias"] and "classe" in r.dados["divergencias"][0]


def test_datajud_desabilitado_vira_conditional(monkeypatch):
    from app.services import datajud_service

    async def _erro(numero):
        raise datajud_service.DataJudDesabilitadoError("desligado")

    monkeypatch.setattr("app.services.datajud_service.consultar_processo", _erro)
    r = _run(DataJudConnector().find_process("50012345620268130024"))
    assert r.estado == EstadoCapacidade.CONDITIONAL


# ── Perfis / SSRF ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://pje.tjmg.jus.br",              # sem https
    "https://127.0.0.1/mni",               # loopback
    "https://10.0.0.5/mni",                # privado
    "https://169.254.169.254/latest",      # link-local (metadata)
    "https://localhost/mni",
    "https://interno.local/mni",
    "https://user:senha@pje.tjmg.jus.br",  # credencial embutida
    "https://pje.tjmg.jus.br/a?token=x",   # query
    "https://tjmg/mni",                    # sem FQDN
])
def test_base_url_invalida_e_recusada(url):
    with pytest.raises(perfis_service.BaseUrlInvalida):
        perfis_service.validar_base_url(url)


def test_base_url_valida_e_normalizada():
    assert perfis_service.validar_base_url("https://pje.tjmg.jus.br/mni/") == "https://pje.tjmg.jus.br/mni"
    assert perfis_service.validar_base_url(None) is None
    assert perfis_service.validar_base_url("   ") is None


def test_status_do_perfil_reflete_homologacao():
    assert perfis_service.calcular_status(_perfil()) == "SUPPORTED"
    assert perfis_service.calcular_status(_perfil(credentials_valid=False)) == "CONDITIONAL"
    assert perfis_service.calcular_status(
        _perfil(authorized=False, homologated_at=None)) == "REQUIRES_AUTHORIZATION"
    assert perfis_service.calcular_status(_perfil(ativo=False)) == "UNSUPPORTED"


def test_perfil_para_dict_nao_expoe_segredo():
    d = perfis_service.perfil_para_dict(_perfil())
    assert d["client_id_ref"] == "pdpj:PDPJ_CLIENT_ID"
    assert not any("secret" in str(k).lower() for k in d)


def test_referencia_de_credencial_precisa_ser_referencia():
    with pytest.raises(ValueError):
        perfis_service._validar_dominios({"client_id_ref": "valor-cru-da-credencial"})
    perfis_service._validar_dominios({"client_id_ref": "pdpj:PDPJ_CLIENT_ID"})


# ── TPU ──────────────────────────────────────────────────────────────────────

def test_tpu_normaliza_item_do_sgt():
    item = _normalizar_item_sgt({"cod_item": " 7 ", "nome": "Procedimento Comum Cível",
                                 "situacao": "A", "cod_item_pai": "1", "dt_publicacao": "2026-01-01"})
    assert item == {"codigo": "7", "descricao": "Procedimento Comum Cível", "situacao": "ativo",
                    "pai_codigo": "1", "versao": "2026-01-01"}
    assert _normalizar_item_sgt({"nome": "sem código"}) is None
    assert _normalizar_item_sgt("texto solto") is None


def test_tpu_tipo_invalido_e_recusado():
    with pytest.raises(TpuTipoInvalido):
        _run(TpuService(db=None).listar("classe_errada"))


def test_tpu_sync_sem_flag_fica_conditional_sem_io():
    estado, motivo = TpuService.estado_sync()
    assert estado == EstadoCapacidade.CONDITIONAL and "CNJ_SGT_ENABLED" in motivo
    r = _run(TpuService(db=None).sincronizar_por_termo("classe", "comum"))
    assert r["importados"] == 0 and r["estado"] == EstadoCapacidade.CONDITIONAL.value


# ── Assinatura ───────────────────────────────────────────────────────────────

def test_assinatura_registro_externo_confere_hash():
    prov = assinatura_mod.provedor("registro_externo")
    dados = {"certificate_subject": "CN=JOAO:12345678900", "certificate_serial": "0A1B2C3D",
             "signed_document_hash": "c" * 64, "document_sha256": "c" * 64,
             "signed_document_id": "doc-9", "algorithm": "SHA256withRSA"}
    r = _run(prov.assinar(document_hash="b" * 64, dados=dados))
    assert r.ok and r.evidencia.certificate_serial == "0A1B2C3D"
    assert r.evidencia.document_hash == "c" * 64
    assert r.evidencia.to_dict()["signature_type"] == "icp_brasil"


def test_assinatura_recusa_hash_divergente_do_documento():
    prov = assinatura_mod.provedor("registro_externo")
    r = _run(prov.assinar(document_hash="b" * 64, dados={
        "certificate_subject": "CN=X", "certificate_serial": "0A1B", "signed_document_hash": "c" * 64,
        "document_sha256": "d" * 64}))
    assert not r.ok and "não confere" in r.mensagem


@pytest.mark.parametrize("dados,fragmento", [
    ({"certificate_serial": "0A1B", "signed_document_hash": "c" * 64}, "certificate_subject"),
    ({"certificate_subject": "CN=X", "certificate_serial": "0A1B", "signed_document_hash": "zz"}, "SHA-256"),
    ({"certificate_subject": "CN=X", "certificate_serial": "0A1B", "signed_document_hash": "c" * 64,
      "algorithm": "MD5withRSA"}, "algoritmo"),
    ({"certificate_subject": "CN=X", "certificate_serial": "??", "signed_document_hash": "c" * 64},
     "certificate_serial"),
])
def test_assinatura_falha_com_dados_invalidos(dados, fragmento):
    r = _run(assinatura_mod.provedor("registro_externo").assinar(document_hash="b" * 64, dados=dados))
    assert not r.ok and fragmento in r.mensagem


def test_provedores_com_chave_fora_do_ejc_sao_requires_authorization():
    for chave in ("a1", "a3_pkcs11", "psc_nuvem"):
        prov = assinatura_mod.provedor(chave)
        estado, _ = prov.estado()
        assert estado == EstadoCapacidade.REQUIRES_AUTHORIZATION
        r = _run(prov.assinar(document_hash="a" * 64, dados={}))
        assert r.estado == EstadoCapacidade.REQUIRES_AUTHORIZATION and r.evidencia is None
    matriz = {m["provider"]: m["estado"] for m in assinatura_mod.matriz_assinatura()}
    assert matriz["registro_externo"] == EstadoCapacidade.SUPPORTED.value
