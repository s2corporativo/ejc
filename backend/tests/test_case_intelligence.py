"""FASE 1 do Orquestrador Jurídico — CaseIntelligenceSnapshot.

Sem Postgres real (padrão test_provas.py): service e handlers chamados
diretamente com fake de sessão. Cobre: versionamento incremental (nunca
sobrescreve), snapshot automático nunca nasce aprovado, congelamento HITL +
409, ownership/roles do endpoint de aprovação, fail-safe do wiring (snapshot
que lança NÃO quebra a triagem) e rotas montadas em main.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.case_intelligence import CaseIntelligenceSnapshot
from app.models.user import User, UserRole
from app.services import case_intelligence_service as cis


# ── Fakes (sem banco) ─────────────────────────────────────────────────────────

class _Res:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalar(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        return self._val if isinstance(self._val, list) else []


class _FakeDB:
    """Sessão fake: fila de resultados para execute(); registra add/commit."""

    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *a, **k):
        return _Res(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _user(role: UserRole, uid: str = "u1") -> User:
    return User(id=uid, role=role)


def _case(**kw) -> Case:
    base = dict(id="case1", titulo="Reclamação Trabalhista", client_id="cli1",
                area="trabalhista", numero_processo=None,
                numero_interno="DPT-2026-0001",
                advogado_responsavel_id=None, advogado_auxiliar_id=None,
                descricao_fatos=None, deleted_at=None)
    base.update(kw)
    return Case(**base)


def _snap(**kw) -> CaseIntelligenceSnapshot:
    base = dict(id="s1", case_id="case1", versao=1, origem="triagem",
                payload={"area": "trabalhista"}, resumo="r", ai_log_ids=[],
                criado_por=None, criado_em=None, congelado=False,
                aprovado_por=None, aprovado_em=None)
    base.update(kw)
    return CaseIntelligenceSnapshot(**base)


# ── Rotas montadas ────────────────────────────────────────────────────────────

def test_rotas_montadas_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/cases/{case_id}/inteligencia") for p in paths)
    assert any(p.endswith("/cases/{case_id}/inteligencia/{snapshot_id}") for p in paths)
    assert any(p.endswith("/cases/{case_id}/inteligencia/{snapshot_id}/aprovar")
               for p in paths)


# ── Versionamento incremental (nunca sobrescreve) ────────────────────────────

async def test_primeiro_snapshot_recebe_versao_1():
    db = _FakeDB([None])  # max(versao) do caso → NULL
    snap = await cis.criar_snapshot(
        db, case_id="case1", origem="triagem",
        payload={"area": "trabalhista"}, resumo="triagem inicial",
        ai_log_ids=["log1"])
    assert snap.versao == 1
    assert snap.origem == "triagem"
    assert snap.ai_log_ids == ["log1"]
    assert db.commits == 1
    assert [o for o in db.added if isinstance(o, CaseIntelligenceSnapshot)] == [snap]


async def test_versao_incrementa_a_partir_do_maximo():
    db = _FakeDB([4])  # já existe v4 → próximo é v5 (nunca sobrescreve)
    snap = await cis.criar_snapshot(
        db, case_id="case1", origem="intake", payload={})
    assert snap.versao == 5


async def test_origem_invalida_rejeitada():
    with pytest.raises(ValueError):
        await cis.criar_snapshot(_FakeDB([]), case_id="case1",
                                 origem="chute", payload={})


async def test_snapshot_automatico_nunca_nasce_aprovado():
    db = _FakeDB([None])
    snap = await cis.criar_snapshot(db, case_id="case1", origem="motor_peca",
                                    payload={}, criado_por=None)
    assert snap.congelado is False
    assert snap.aprovado_por is None and snap.aprovado_em is None


# ── Aprovação HITL / congelamento ────────────────────────────────────────────

async def test_aprovar_congela_e_audita():
    snap = _snap()
    db = _FakeDB([snap])
    out = await cis.aprovar_snapshot(db, "s1", _user(UserRole.advogado))
    assert out.congelado is True
    assert out.aprovado_por == "u1" and out.aprovado_em is not None
    logs = [o for o in db.added if isinstance(o, AuditLog)]
    assert len(logs) == 1
    assert logs[0].entidade == "case_intelligence_snapshots"
    assert logs[0].registro_id == "s1"
    assert db.commits == 1


async def test_aprovar_409_se_ja_congelado():
    db = _FakeDB([_snap(congelado=True)])
    with pytest.raises(HTTPException) as exc:
        await cis.aprovar_snapshot(db, "s1", _user(UserRole.advogado))
    assert exc.value.status_code == 409
    assert db.commits == 0


async def test_aprovar_404_se_inexistente():
    with pytest.raises(HTTPException) as exc:
        await cis.aprovar_snapshot(_FakeDB([None]), "sX", _user(UserRole.advogado))
    assert exc.value.status_code == 404


# ── Endpoints: ownership e roles ─────────────────────────────────────────────

async def test_aprovar_endpoint_403_para_estagiario():
    from app.routers.case_intelligence import aprovar
    with pytest.raises(HTTPException) as exc:
        await aprovar(case_id="case1", snapshot_id="s1",
                      db=_FakeDB([]), cu=_user(UserRole.estagiario))
    assert exc.value.status_code == 403


async def test_aprovar_endpoint_403_para_advogado_sem_vinculo():
    from app.routers.case_intelligence import aprovar
    # caso com responsável/auxiliar ≠ u1 → verificar_acesso_caso barra (403)
    db = _FakeDB([_case(advogado_responsavel_id="outro",
                        advogado_auxiliar_id="outro2")])
    with pytest.raises(HTTPException) as exc:
        await aprovar(case_id="case1", snapshot_id="s1",
                      db=db, cu=_user(UserRole.advogado))
    assert exc.value.status_code == 403


async def test_aprovar_endpoint_fluxo_feliz_socio():
    from app.routers.case_intelligence import aprovar
    snap = _snap()
    db = _FakeDB([_case(), snap])  # verificar_acesso_caso → obter_snapshot
    out = await aprovar(case_id="case1", snapshot_id="s1",
                        db=db, cu=_user(UserRole.socio))
    assert out["ok"] is True
    assert out["snapshot"]["congelado"] is True
    assert snap.congelado is True


async def test_get_inteligencia_ultimo_mais_historico():
    from app.routers.case_intelligence import obter_inteligencia
    s2, s1 = _snap(id="s2", versao=2, origem="intake"), _snap()
    db = _FakeDB([_case(), [s2, s1]])  # acesso → historico (versao desc)
    out = await obter_inteligencia(case_id="case1", db=db,
                                   cu=_user(UserRole.socio))
    assert out["total"] == 2
    assert out["ultimo"]["versao"] == 2 and "payload" in out["ultimo"]
    assert [h["versao"] for h in out["historico"]] == [2, 1]


async def test_get_snapshot_de_outro_caso_404():
    from app.routers.case_intelligence import obter_snapshot
    db = _FakeDB([_case(), None])  # filtro id+case_id não encontra → 404
    with pytest.raises(HTTPException) as exc:
        await obter_snapshot(case_id="case1", snapshot_id="s-alheio",
                             db=db, cu=_user(UserRole.socio))
    assert exc.value.status_code == 404


# ── Fail-safe do wiring ──────────────────────────────────────────────────────

async def test_gravar_snapshot_seguro_engole_falha(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(cis, "criar_snapshot", _boom)
    db = _FakeDB([])
    out = await cis.gravar_snapshot_seguro(
        db, case_id="case1", origem="intake", payload={})
    assert out is None            # nunca propaga
    assert db.rollbacks == 1      # rollback best-effort


async def test_triagem_nao_quebra_quando_snapshot_falha(monkeypatch):
    """Snapshot que lança NÃO pode quebrar a triagem (wiring fail-safe)."""
    from app.services import case_intel

    case = _case(descricao_fatos=(
        "Cliente relata demissão sem justa causa e verbas rescisórias "
        "não pagas pelo empregador."))
    db = _FakeDB([])

    async def _get(model, pk):
        return case
    db.get = _get

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(case_intel, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(case_intel.settings, "AI_ENABLED", True)

    async def _fake_gateway(*a, **k):
        bruto = json.dumps({
            "area": "trabalhista", "assunto": "verbas rescisórias",
            "tese_principal": "Rescisão sem justa causa gera verbas integrais",
            "teses_secundarias": [], "pontos_fortes": "documentos",
            "pontos_fracos": "prova testemunhal", "provas_necessarias": ["CTPS"],
            "oportunidades": "", "chance_exito": 70, "complexidade": "media"})
        return bruto, type("R", (), {"modelo": "m", "provedor": "p"})()
    monkeypatch.setattr(case_intel, "_gateway_json", _fake_gateway)

    import app.services.ai.entidades_caso as ec

    async def _ent(_db, _cid):
        return {}
    monkeypatch.setattr(ec, "entidades_do_caso", _ent)

    async def _boom(*a, **k):
        raise RuntimeError("snapshot indisponível")
    monkeypatch.setattr(cis, "criar_snapshot", _boom)

    await case_intel.triagem_caso("case1")  # não deve levantar
    assert db.commits >= 1  # a triagem persistiu apesar da falha do snapshot


async def test_triagem_grava_snapshot_no_caminho_feliz(monkeypatch):
    from app.services import case_intel

    case = _case(descricao_fatos=(
        "Cliente relata demissão sem justa causa e verbas rescisórias "
        "não pagas pelo empregador."))
    db = _FakeDB([None])  # única query: max(versao) do criar_snapshot

    async def _get(model, pk):
        return case
    db.get = _get

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(case_intel, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(case_intel.settings, "AI_ENABLED", True)

    async def _fake_gateway(*a, **k):
        bruto = json.dumps({
            "area": "trabalhista", "assunto": "verbas rescisórias",
            "tese_principal": "Rescisão sem justa causa gera verbas integrais",
            "teses_secundarias": [], "pontos_fortes": "documentos",
            "pontos_fracos": "prova testemunhal", "provas_necessarias": ["CTPS"],
            "oportunidades": "", "chance_exito": 70, "complexidade": "media"})
        return bruto, type("R", (), {"modelo": "m", "provedor": "p"})()
    monkeypatch.setattr(case_intel, "_gateway_json", _fake_gateway)

    import app.services.ai.entidades_caso as ec

    async def _ent(_db, _cid):
        return {}
    monkeypatch.setattr(ec, "entidades_do_caso", _ent)

    await case_intel.triagem_caso("case1")
    snaps = [o for o in db.added if isinstance(o, CaseIntelligenceSnapshot)]
    assert len(snaps) == 1
    s = snaps[0]
    assert s.origem == "triagem" and s.versao == 1 and s.congelado is False
    assert s.payload["area"] == "trabalhista"
    assert "chance_exito" not in s.payload.get("riscos", {})
    assert s.ai_log_ids and s.criado_por is None  # automático, rastreável


async def test_triagem_area_fora_do_canonico_vira_outro_no_payload(monkeypatch):
    """Item 6 (contrato do model): payload['area'] é SEMPRE canônico — texto da
    IA fora da taxonomia vira 'outro' e o bruto fica em payload['area_bruta']."""
    from app.services import case_intel

    case = _case(descricao_fatos=(
        "Cliente relata demissão sem justa causa e verbas rescisórias "
        "não pagas pelo empregador."))
    db = _FakeDB([None])  # única query: max(versao) do criar_snapshot

    async def _get(model, pk):
        return case
    db.get = _get

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(case_intel, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(case_intel.settings, "AI_ENABLED", True)

    async def _fake_gateway(*a, **k):
        bruto = json.dumps({
            "area": "direito da vizinhança espacial",   # fora do canônico
            "assunto": "x", "tese_principal": "t", "teses_secundarias": [],
            "pontos_fortes": "", "pontos_fracos": "", "provas_necessarias": [],
            "oportunidades": "", "chance_exito": 50, "complexidade": "media"})
        return bruto, type("R", (), {"modelo": "m", "provedor": "p"})()
    monkeypatch.setattr(case_intel, "_gateway_json", _fake_gateway)

    import app.services.ai.entidades_caso as ec

    async def _ent(_db, _cid):
        return {}
    monkeypatch.setattr(ec, "entidades_do_caso", _ent)

    await case_intel.triagem_caso("case1")
    snaps = [o for o in db.added if isinstance(o, CaseIntelligenceSnapshot)]
    assert len(snaps) == 1
    assert snaps[0].payload["area"] == "outro"
    assert snaps[0].payload["area_bruta"] == "direito da vizinhança espacial"


# ── Compactação de payload (limite ~50KB do motor_peca) ──────────────────────

def test_compactar_payload_intacto_quando_pequeno():
    p = {"a": 1, "b": "x"}
    assert cis.compactar_payload(p) == p


def test_compactar_payload_descarta_chaves_gigantes():
    p = {"peca_sugerida": "contestacao", "motivacao_ia": "x" * 80_000}
    out = cis.compactar_payload(p, descartaveis=("motivacao_ia",))
    assert "motivacao_ia" not in out
    assert out["_compactado"] == ["motivacao_ia"]
    assert out["peca_sugerida"] == "contestacao"
    assert len(json.dumps(out).encode()) <= cis.PAYLOAD_MAX_BYTES


def test_compactar_payload_truncagem_anotada_em_compactado():
    """Item 17: o último recurso (truncar strings) fica ANOTADO em _compactado
    e o tamanho é re-verificado após a truncagem."""
    p = {"granda": "x" * 80_000}
    out = cis.compactar_payload(p)   # sem descartáveis → vai direto à truncagem
    assert out["_compactado"] == ["strings_truncadas"]
    assert out["granda"].endswith("[truncado]")
    assert len(json.dumps(out, ensure_ascii=False).encode()) <= cis.PAYLOAD_MAX_BYTES

    # Chave descartada + truncagem: ambas anotadas, na ordem.
    p2 = {"motivacao_ia": "y" * 80_000, "resto": "z" * 80_000}
    out2 = cis.compactar_payload(p2, descartaveis=("motivacao_ia",))
    assert out2["_compactado"] == ["motivacao_ia", "strings_truncadas"]
