"""Admissão automática do cliente + sincronização com o tribunal no encerramento.

Cobre as três regras que o titular pediu e que antes não existiam:
  1. cadastrar cliente já emite procuração + contrato (sem depender do
     operador lembrar de pedir) e NUNCA derruba o cadastro se a emissão falhar;
  2. quem não é advogado não figura como contratado no contrato;
  3. encerrar o caso pode disparar a sincronização MNI/PJe, degradando
     graciosamente quando não há número de processo ou a fila está fora.
"""
from __future__ import annotations

import pytest

from fastapi import HTTPException

from app.core.config import get_settings
from app.routers import cases as cases_router
from app.routers import clients as clients_router
from app.services import geracao_documental_cliente as gdc


class _FakeDB:
    """Sessão mínima: registra os efeitos transacionais que os handlers usam."""

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.refreshes = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _obj):
        self.refreshes += 1


class _Cliente:
    def __init__(self, status="ativo"):
        self.id = "cli-1"
        self.status = status


async def _sem_limite(nome, chave, maximo):
    """Cota livre: os testes de enfileiramento não exercitam o rate limit."""
    return None


class _Usuario:
    def __init__(self, role: str, nome: str = "Fulana de Tal"):
        self.id = "user-1"
        self.role = role
        self.full_name = nome


# ── 1) Kit de admissão no cadastro ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_cadastro_gera_procuracao_e_contrato(monkeypatch):
    chamadas = []

    async def _fake_gerar(db, cli, cu, **kw):
        chamadas.append(cli.id)
        return {"status": "rascunho"}

    monkeypatch.setattr(gdc, "gerar_documentos_cliente", _fake_gerar)
    monkeypatch.setattr(get_settings(), "CLIENTE_KIT_ADMISSAO_AUTOMATICO", True)

    db = _FakeDB()
    await clients_router._kit_admissao_automatico(db, _Cliente(), _Usuario("advogado"))

    assert chamadas == ["cli-1"], "cadastro deve emitir o kit de admissão"
    assert db.rollbacks == 0
    # expire_on_commit=False: o commit da emissão não expira o cliente, então
    # o caminho feliz não paga um SELECT extra por cadastro.
    assert db.refreshes == 0


@pytest.mark.asyncio
async def test_papel_nao_juridico_nao_contorna_o_gate_de_ato_juridico(monkeypatch):
    """Emitir procuração/contrato é ato jurídico atrás de `requer_advogado`.

    A rota manual e a listagem dos rascunhos exigem advogado+; o disparo
    automático não pode ser a porta lateral desse mesmo gate.
    """

    async def _nunca(*a, **kw):  # pragma: no cover - não deve ser chamado
        raise AssertionError("secretaria não emite kit de admissão")

    monkeypatch.setattr(gdc, "gerar_documentos_cliente", _nunca)
    monkeypatch.setattr(get_settings(), "CLIENTE_KIT_ADMISSAO_AUTOMATICO", True)

    db = _FakeDB()
    await clients_router._kit_admissao_automatico(db, _Cliente(), _Usuario("secretaria"))
    assert db.refreshes == 0


@pytest.mark.asyncio
async def test_lead_nao_recebe_kit(monkeypatch):
    """Minimização: prospect que talvez nunca contrate não gera documento com
    a qualificação completa (nome, CPF/CNPJ, endereço) em texto puro."""

    async def _nunca(*a, **kw):  # pragma: no cover - não deve ser chamado
        raise AssertionError("lead não recebe kit de admissão")

    monkeypatch.setattr(gdc, "gerar_documentos_cliente", _nunca)
    monkeypatch.setattr(get_settings(), "CLIENTE_KIT_ADMISSAO_AUTOMATICO", True)

    db = _FakeDB()
    await clients_router._kit_admissao_automatico(
        db, _Cliente(status="lead"), _Usuario("advogado")
    )
    assert db.refreshes == 0


@pytest.mark.asyncio
async def test_flag_desligada_nao_gera_nada(monkeypatch):
    async def _nunca(*a, **kw):  # pragma: no cover - não deve ser chamado
        raise AssertionError("kit não deveria ser gerado com a flag desligada")

    monkeypatch.setattr(gdc, "gerar_documentos_cliente", _nunca)
    monkeypatch.setattr(get_settings(), "CLIENTE_KIT_ADMISSAO_AUTOMATICO", False)

    db = _FakeDB()
    await clients_router._kit_admissao_automatico(db, _Cliente(), _Usuario("advogado"))
    assert db.refreshes == 0


@pytest.mark.asyncio
async def test_falha_na_geracao_nao_derruba_o_cadastro(monkeypatch):
    """O cliente já foi commitado: a emissão é acessória, não pode propagar erro."""

    async def _explode(*a, **kw):
        raise RuntimeError("tabela OAB indisponível")

    monkeypatch.setattr(gdc, "gerar_documentos_cliente", _explode)
    monkeypatch.setattr(get_settings(), "CLIENTE_KIT_ADMISSAO_AUTOMATICO", True)

    db = _FakeDB()
    await clients_router._kit_admissao_automatico(db, _Cliente(), _Usuario("advogado"))

    assert db.rollbacks == 1, "a transação parcial da emissão é revertida"
    assert db.refreshes == 1, "rollback expira a sessão — o cliente é reidratado"


# ── 2) Quem assina o contrato como contratado ────────────────────────────────

def test_secretaria_nao_vira_advogado_contratado():
    assert gdc._nome_advogado(_Usuario("secretaria")) == "[advogado responsável]"
    assert gdc._nome_advogado(_Usuario("advogado")) == "Fulana de Tal"
    assert gdc._nome_advogado(_Usuario("advogado", nome="  ")) == "[advogado responsável]"


# ── 3) Sincronização MNI/PJe no encerramento ─────────────────────────────────

class _Caso:
    def __init__(self, numero_processo=None):
        self.id = "case-1"
        self.numero_processo = numero_processo


class _Payload:
    def __init__(self, solicitar: bool, numero_cnj=None):
        self.sincronizar_processo_eletronico = solicitar
        self.numero_cnj = numero_cnj


@pytest.mark.asyncio
async def test_sem_solicitacao_nao_toca_no_tribunal():
    db = _FakeDB()
    res = await cases_router._sincronizar_no_encerramento(
        db, _Caso("1234567-89.2026.8.13.0027"), _Usuario("advogado"), _Payload(False)
    )
    assert res["solicitada"] is False
    assert db.commits == 0


@pytest.mark.asyncio
async def test_caso_sem_numero_reporta_em_vez_de_falhar():
    db = _FakeDB()
    res = await cases_router._sincronizar_no_encerramento(
        db, _Caso(None), _Usuario("advogado"), _Payload(True)
    )
    assert res["status"] == "sem_numero"
    assert db.commits == 0, "nada a enfileirar, nada a auditar"


@pytest.mark.asyncio
async def test_enfileira_com_o_numero_do_caso(monkeypatch):
    enviados = []

    class _Job:
        id = "job-42"

    def _delay(case_id, numero):
        enviados.append((case_id, numero))
        return _Job()

    import app.tasks.processo_eletronico_tasks as pe_tasks

    monkeypatch.setattr(pe_tasks.sincronizar_processo_task, "delay", _delay)

    auditorias = []

    async def _audit(db, *a, **kw):
        auditorias.append(a)

    monkeypatch.setattr(cases_router, "criar_audit_log", _audit)

    db = _FakeDB()
    res = await cases_router._sincronizar_no_encerramento(
        db, _Caso("1234567-89.2026.8.13.0027"), _Usuario("advogado"), _Payload(True)
    )

    assert res["status"] == "enfileirado"
    assert res["job_id"] == "job-42"
    assert enviados == [("case-1", "1234567-89.2026.8.13.0027")]
    assert auditorias, "enfileiramento entra na trilha de auditoria do caso"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_numero_do_payload_prevalece_sobre_o_do_caso(monkeypatch):
    enviados = []

    class _Job:
        id = "job-7"

    import app.tasks.processo_eletronico_tasks as pe_tasks

    monkeypatch.setattr(
        pe_tasks.sincronizar_processo_task, "delay",
        lambda c, n: (enviados.append((c, n)), _Job())[1],
    )

    async def _audit(db, *a, **kw):
        return None

    monkeypatch.setattr(cases_router, "criar_audit_log", _audit)

    await cases_router._sincronizar_no_encerramento(
        _FakeDB(), _Caso("0000000-00.2020.8.13.0001"), _Usuario("advogado"),
        _Payload(True, numero_cnj="9999999-99.2026.8.13.0027"),
    )
    assert enviados == [("case-1", "9999999-99.2026.8.13.0027")]


@pytest.mark.asyncio
async def test_fila_indisponivel_nao_desfaz_o_encerramento(monkeypatch):
    import app.tasks.processo_eletronico_tasks as pe_tasks

    def _explode(*a, **kw):
        raise RuntimeError("broker fora do ar")

    monkeypatch.setattr(pe_tasks.sincronizar_processo_task, "delay", _explode)

    db = _FakeDB()
    res = await cases_router._sincronizar_no_encerramento(
        db, _Caso("1234567-89.2026.8.13.0027"), _Usuario("advogado"), _Payload(True)
    )
    assert res["status"] == "falha_ao_enfileirar"
    assert res["detalhe"], "o operador precisa saber por que não sincronizou"
    assert db.commits == 0


# ── Vocabulário do encerramento (contrato com o formulário) ──────────────────

def test_resultados_aceitos_pelo_encerramento():
    """A UI monta o select a partir deste vocabulário — divergir dá 422."""
    campo = cases_router.EncerrarCasoReq.model_fields["resultado"]
    padrao = next(
        m.pattern for m in campo.metadata if hasattr(m, "pattern")
    )
    for valor in ("exito", "exito_parcial", "acordo", "derrota", "desistencia", "arquivado"):
        assert valor in padrao


# ── Poderes pedidos não podem ser ignorados pela idempotência ────────────────

class _DBComCliente(_FakeDB):
    """Sessão que devolve sempre o mesmo cliente para o SELECT do handler."""

    def __init__(self, cliente):
        super().__init__()
        self._cliente = cliente

    async def execute(self, *_a, **_kw):
        cliente = self._cliente

        class _Res:
            def scalar_one_or_none(self):
                return cliente

        return _Res()


async def _chamar_gerar(monkeypatch, payload, resultado_service):
    from fastapi import HTTPException

    cli = _Cliente()

    async def _pode_ver(*_a, **_kw):
        return True

    async def _gerar(*_a, **_kw):
        return resultado_service

    monkeypatch.setattr(clients_router, "_pode_ver_cliente", _pode_ver)
    monkeypatch.setattr(gdc, "gerar_documentos_cliente", _gerar)

    try:
        return await clients_router.gerar_documentos_cliente(
            "cli-1", payload, _DBComCliente(cli), _Usuario("advogado")
        ), None
    except HTTPException as e:
        return None, e


@pytest.mark.asyncio
async def test_poderes_pedidos_sobre_kit_existente_falham_alto(monkeypatch):
    """Devolver a procuração antiga faria o advogado assinar poderes que não
    são os que ele pediu — o aviso no corpo da resposta não obriga ninguém."""
    payload = clients_router.GerarDocsClienteIn(tipo_poderes="ad_judicia_et_extra")
    ok, erro = await _chamar_gerar(monkeypatch, payload, {"ja_existia": True})

    assert ok is None
    assert erro is not None and erro.status_code == 409
    assert "forcar_novo=true" in erro.detail
    assert "tipo_poderes" in erro.detail


@pytest.mark.asyncio
async def test_kit_existente_sem_poderes_explicitos_ainda_e_idempotente(monkeypatch):
    """Sem pedido de poderes, reaproveitar o rascunho continua correto."""
    ok, erro = await _chamar_gerar(
        monkeypatch, clients_router.GerarDocsClienteIn(), {"ja_existia": True}
    )
    assert erro is None
    assert ok == {"ja_existia": True}


@pytest.mark.asyncio
async def test_primeira_emissao_com_poderes_passa(monkeypatch):
    payload = clients_router.GerarDocsClienteIn(poderes_especiais="art. 105 CPC")
    ok, erro = await _chamar_gerar(monkeypatch, payload, {"ja_existia": False})
    assert erro is None
    assert ok == {"ja_existia": False}


# ── Achados da review do Codex (PR #1458) ────────────────────────────────────

@pytest.mark.asyncio
async def test_cota_do_tribunal_nao_e_consumida_sem_sincronizacao(monkeypatch):
    """Encerramento comum não pode gastar a cota MNI.

    Regressão: o rate limit entrara como dependency da rota, e o FastAPI a
    resolve ANTES do handler — dez encerramentos comuns num minuto derrubavam o
    décimo primeiro com 429 e ainda esgotavam a cota do endpoint dedicado, sem
    nenhuma chamada a tribunal.
    """
    consumos = []

    async def _consumir(nome, chave, maximo):
        consumos.append(nome)

    monkeypatch.setattr(cases_router, "consumir", _consumir)

    await cases_router._sincronizar_no_encerramento(
        _FakeDB(), _Caso("1234567-89.2026.8.13.0027"), _Usuario("advogado"),
        _Payload(False),
    )
    assert consumos == [], "encerramento sem sincronização não gasta cota do tribunal"


@pytest.mark.asyncio
async def test_cota_excedida_nao_derruba_o_encerramento(monkeypatch):
    async def _estourar(nome, chave, maximo):
        raise HTTPException(status_code=429, detail="Limite excedido")

    monkeypatch.setattr(cases_router, "consumir", _estourar)

    db = _FakeDB()
    res = await cases_router._sincronizar_no_encerramento(
        db, _Caso("1234567-89.2026.8.13.0027"), _Usuario("advogado"), _Payload(True)
    )
    assert res["status"] == "limite_excedido"
    assert res["detalhe"]
    assert db.commits == 0


@pytest.mark.asyncio
async def test_numero_em_branco_cai_no_do_caso(monkeypatch):
    """`numero_cnj` só com espaços é truthy e vencia o `or`, virando vazio
    depois do strip — o caso perdia a sincronização tendo número válido."""
    enviados = []

    class _Job:
        id = "job-9"

    import app.tasks.processo_eletronico_tasks as pe_tasks

    monkeypatch.setattr(
        pe_tasks.sincronizar_processo_task, "delay",
        lambda c, n: (enviados.append((c, n)), _Job())[1],
    )
    monkeypatch.setattr(cases_router, "consumir", _sem_limite)

    async def _audit(db, *a, **kw):
        return None

    monkeypatch.setattr(cases_router, "criar_audit_log", _audit)

    res = await cases_router._sincronizar_no_encerramento(
        _FakeDB(), _Caso("1234567-89.2026.8.13.0027"), _Usuario("advogado"),
        _Payload(True, numero_cnj="   "),
    )
    assert res["status"] == "enfileirado"
    assert enviados == [("case-1", "1234567-89.2026.8.13.0027")]


@pytest.mark.asyncio
async def test_falha_na_trilha_nao_vira_500_com_caso_ja_encerrado(monkeypatch):
    """A task já está na fila e o caso já foi commitado como encerrado: falha
    ao gravar a auditoria não pode propagar, ou a UI diria "falha ao encerrar"
    para um caso encerrado e o retry devolveria "Caso já encerrado"."""

    class _Job:
        id = "job-11"

    import app.tasks.processo_eletronico_tasks as pe_tasks

    monkeypatch.setattr(pe_tasks.sincronizar_processo_task, "delay", lambda c, n: _Job())
    monkeypatch.setattr(cases_router, "consumir", _sem_limite)

    async def _audit_explode(db, *a, **kw):
        raise RuntimeError("trilha WORM indisponível")

    monkeypatch.setattr(cases_router, "criar_audit_log", _audit_explode)

    db = _FakeDB()
    res = await cases_router._sincronizar_no_encerramento(
        db, _Caso("1234567-89.2026.8.13.0027"), _Usuario("advogado"), _Payload(True)
    )
    assert res["status"] == "enfileirado", "o estado real é enfileirado"
    assert res["auditada"] is False, "a resposta admite que a trilha não foi gravada"
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_lead_convertido_recebe_o_kit(monkeypatch):
    """Conversão do lead é O caminho de admissão: sem o disparo no PATCH, o
    cliente convertido — o que assina procuração e contrato — ficaria sem o kit,
    dependendo da ação manual que esta feature existe para eliminar."""
    chamadas = []

    async def _fake_gerar(db, cli, cu, **kw):
        chamadas.append(cli.id)
        return {"status": "rascunho"}

    monkeypatch.setattr(gdc, "gerar_documentos_cliente", _fake_gerar)
    monkeypatch.setattr(get_settings(), "CLIENTE_KIT_ADMISSAO_AUTOMATICO", True)

    from app.models.client import ClientStatus

    class _ClienteAtivo:
        id = "cli-1"
        status = ClientStatus.ativo

    await clients_router._kit_admissao_automatico(
        _FakeDB(), _ClienteAtivo(), _Usuario("advogado")
    )
    assert chamadas == ["cli-1"], "cliente admitido recebe o kit"


def test_patch_dispara_o_kit_na_saida_de_lead():
    """Trava estrutural: o handler de PATCH precisa comparar o status anterior
    e chamar o disparo. Sem isso o board do CRM converte o lead em silêncio."""
    import inspect

    fonte = inspect.getsource(clients_router.atualizar)
    assert "status_antes" in fonte
    assert "_kit_admissao_automatico" in fonte
