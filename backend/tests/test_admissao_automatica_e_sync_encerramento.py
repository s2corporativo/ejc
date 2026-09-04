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
    id = "cli-1"


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
