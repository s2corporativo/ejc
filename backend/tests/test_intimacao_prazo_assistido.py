"""Testes do fluxo assistido intimação DJEN -> prazo jurídico (#861)."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.djen import DjenComunicacao
from app.models.user import User, UserRole


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value if isinstance(self.value, list) else []


class _FakeDB:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _query):
        value = self.results.pop(0) if self.results else None
        return _FakeResult(value)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1


class _GestaoResult:
    def __init__(self, rows, total):
        self.rows = rows
        self.total = total

    def scalar(self):
        return self.total

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _GestaoDB:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        if self.calls == 1:
            return _GestaoResult([], len(self.rows))
        return _GestaoResult(self.rows, len(self.rows))


def _user(uid="u1", role=UserRole.advogado):
    return User(id=uid, role=role, email=f"{uid}@teste.local")


def _com(**kw):
    return DjenComunicacao(
        id=kw.get("id", "com-1"),
        comunicacao_id_externo=kw.get("external_id", "ext-1"),
        advogado_id=kw.get("advogado_id", "u1"),
        numero_processo=kw.get("numero_processo", "0000001-00.2026.8.13.0001"),
        tribunal=kw.get("tribunal", "TJMG"),
        tipo_comunicacao=kw.get("tipo", "Intimação"),
        data_disponibilizacao=kw.get("data", date(2026, 7, 7)),
        texto_resumo=kw.get("texto", "Apresente contestação no prazo legal."),
        case_id=kw.get("case_id"),
        processada=kw.get("processada", False),
        prazo_sugerido_status=kw.get("prazo_sugerido_status", "nenhum"),
        prazo_deadline_id=kw.get("prazo_deadline_id"),
    )


async def _sugestao_civel(comunicacao):
    from app.routers.intimacoes import _calcular_sugestao

    comunicacao.case_id = comunicacao.case_id or "case-1"
    return await _calcular_sugestao(comunicacao, _FakeDB(["civil"]))


@pytest.mark.asyncio
async def test_heuristica_reconhece_embargos_5_dias_art_1023():
    s = await _sugestao_civel(_com(texto="Embargos de Declaração."))
    assert s["tipo_detectado"] == "embargos de declaração"
    assert s["dias"] == 5
    assert "1.023" in s["fundamentacao"]
    assert s["regime_processual"] == "civel"
    assert s["disponivel"] is True


@pytest.mark.asyncio
async def test_heuristica_reconhece_contestacao_15_dias_art_335():
    s = await _sugestao_civel(_com(texto="Apresente contestação."))
    assert s["tipo_detectado"] == "contestação"
    assert s["dias"] == 15
    assert "335" in s["fundamentacao"]


@pytest.mark.asyncio
async def test_heuristica_reconhece_apelacao_15_dias_art_1003():
    s = await _sugestao_civel(_com(texto="Interponha apelação."))
    assert s["tipo_detectado"] == "apelação"
    assert s["dias"] == 15
    assert "1.003" in s["fundamentacao"]


@pytest.mark.asyncio
async def test_heuristica_reconhece_manifestacao_despacho_5_dias_art_218():
    s = await _sugestao_civel(_com(texto="Despacho para manifestação."))
    assert s["dias"] == 5
    assert "218" in s["fundamentacao"]
    assert "supletivo" in s["fundamentacao"]


@pytest.mark.asyncio
async def test_termo_especifico_prevalece_sobre_generico():
    s = await _sugestao_civel(_com(texto="Despacho: apresente contestação."))
    assert s["tipo_detectado"] == "contestação"
    assert s["dias"] == 15


@pytest.mark.asyncio
async def test_tipo_desconhecido_nao_inventa_artigo_nem_prazo_padrao():
    s = await _sugestao_civel(_com(texto="Ciência do teor da certidão juntada."))
    assert s["casou"] is False
    assert s["dias"] is None
    assert s["fundamentacao"] is None
    assert s["disponivel"] is False
    assert s["data_sugerida"] is None


@pytest.mark.asyncio
async def test_sem_data_disponibilizacao_fica_indisponivel():
    s = await _sugestao_civel(_com(data=None, texto="Apresente contestação."))
    assert s["disponivel"] is False
    assert s["data_base"] is None
    assert s["data_sugerida"] is None


@pytest.mark.asyncio
async def test_datetime_disponibilizacao_e_normalizado():
    s = await _sugestao_civel(
        _com(data=datetime(2026, 7, 7, 12, tzinfo=timezone.utc), texto="Contestação.")
    )
    assert s["data_base"] == date(2026, 7, 7)
    assert s["data_publicacao"] == date(2026, 7, 8)
    assert s["termo_inicial"] == date(2026, 7, 9)
    assert s["data_sugerida"] == date(2026, 7, 29)


@pytest.mark.asyncio
async def test_regime_desconhecido_falha_fechado():
    from app.routers.intimacoes import _calcular_sugestao

    s = await _calcular_sugestao(_com(case_id=None), _FakeDB([]))
    assert s["disponivel"] is False
    assert s["regime_processual"] is None
    assert "regime" in s["aviso"].lower()


@pytest.mark.asyncio
async def test_gestao_enxerga_intimacao_de_qualquer_advogado():
    from app.routers.intimacoes import listar

    comunicacao = _com(advogado_id="u-outro", processada=True)
    out = await listar(
        apenas_pendentes=False,
        page=1,
        page_size=30,
        db=_GestaoDB([comunicacao]),
        cu=_user("gestao", UserRole.socio),
    )
    assert out["total"] == 1
    assert out["data"][0]["processada"] is True


async def _noop_acesso(*_args, **_kwargs):
    return None


async def _noop_audit(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_aceitar_exige_vinculo_com_caso():
    from app.routers.intimacoes import AceitarPrazoRequest, aceitar_prazo

    comunicacao = _com(case_id=None)
    with pytest.raises(HTTPException) as exc:
        await aceitar_prazo(
            comunicacao.id,
            AceitarPrazoRequest(regime_processual="civel"),
            _FakeDB([comunicacao]),
            _user(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_aceitar_cria_deadline_com_rastreabilidade(monkeypatch):
    import app.routers.intimacoes as mod

    monkeypatch.setattr(mod, "verificar_acesso_caso", _noop_acesso)
    monkeypatch.setattr(mod, "criar_audit_log", _noop_audit)
    comunicacao = _com(case_id="case-1")
    db = _FakeDB([comunicacao])
    out = await mod.aceitar_prazo(
        comunicacao.id,
        mod.AceitarPrazoRequest(
            data_prazo=date(2026, 7, 30), regime_processual="civel"
        ),
        db,
        _user(),
    )
    assert out["criado"] is True
    prazo = next(obj for obj in db.added if obj.__class__.__name__ == "Deadline")
    assert prazo.origem == "djen"
    assert prazo.data_intimacao == date(2026, 7, 7)
    assert prazo.regime_calculo == "civel"
    assert prazo.data_prazo == date(2026, 7, 30)
    assert comunicacao.prazo_sugerido_status == "aceito"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_aceitar_e_idempotente_quando_deadline_ainda_existe(monkeypatch):
    import app.routers.intimacoes as mod

    monkeypatch.setattr(mod, "verificar_acesso_caso", _noop_acesso)
    existente = SimpleNamespace(
        id="deadline-1", data_prazo=date(2026, 7, 28), deleted_at=None
    )
    comunicacao = _com(
        case_id="case-1",
        prazo_sugerido_status="aceito",
        prazo_deadline_id="deadline-1",
    )
    db = _FakeDB([comunicacao, existente])
    out = await mod.aceitar_prazo(
        comunicacao.id, mod.AceitarPrazoRequest(), db, _user()
    )
    assert out["criado"] is False
    assert out["deadline_id"] == "deadline-1"
    assert db.added == []


@pytest.mark.asyncio
async def test_dias_recalcula_pelo_termo_inicial_djen(monkeypatch):
    import app.routers.intimacoes as mod

    monkeypatch.setattr(mod, "verificar_acesso_caso", _noop_acesso)
    monkeypatch.setattr(mod, "criar_audit_log", _noop_audit)
    comunicacao = _com(case_id="case-1", texto="Ciência sem tipo reconhecível.")
    db = _FakeDB([comunicacao])
    out = await mod.aceitar_prazo(
        comunicacao.id,
        mod.AceitarPrazoRequest(dias=15, regime_processual="civel"),
        db,
        _user(),
    )
    assert out["data_prazo"] == date(2026, 7, 29)


@pytest.mark.asyncio
async def test_responsavel_default_e_o_advogado_da_intimacao(monkeypatch):
    import app.routers.intimacoes as mod

    monkeypatch.setattr(mod, "verificar_acesso_caso", _noop_acesso)
    monkeypatch.setattr(mod, "criar_audit_log", _noop_audit)
    comunicacao = _com(
        case_id="case-1", advogado_id="adv-destino", texto="Apresente contestação."
    )
    db = _FakeDB([comunicacao, "civil"])
    await mod.aceitar_prazo(
        comunicacao.id,
        mod.AceitarPrazoRequest(regime_processual="civel"),
        db,
        _user("gestao", UserRole.socio),
    )
    prazo = next(obj for obj in db.added if obj.__class__.__name__ == "Deadline")
    assert prazo.responsavel_id == "adv-destino"


@pytest.mark.asyncio
async def test_recusar_nao_cria_deadline(monkeypatch):
    import app.routers.intimacoes as mod

    monkeypatch.setattr(mod, "verificar_acesso_caso", _noop_acesso)
    monkeypatch.setattr(mod, "criar_audit_log", _noop_audit)
    comunicacao = _com(case_id="case-1")
    db = _FakeDB([comunicacao])
    out = await mod.recusar_prazo(comunicacao.id, db, _user())
    assert out["prazo_sugerido_status"] == "recusado"
    assert not any(obj.__class__.__name__ == "Deadline" for obj in db.added)
    assert db.commits == 1
