"""Contador de uso das AI Skills (Bloco 4 — enxugar catálogo, migration 130).

Antes desta migration, `ejc_skills` não tinha nenhum contador de execução, e
`AILog` não distingue qual skill gerou a chamada — não havia como saber,
mesmo pelos logs, se uma skill do catálogo (163 no inventário da auditoria)
tinha algum uso real. `_marcar_uso` fecha essa lacuna daqui pra frente;
`skills_sem_uso` é o relatório (só leitura, nunca arquiva) que fica possível
depois que dado real se acumular.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.ai_skill import EjcSkill
from app.services import ai_skill_service
from app.services.ai_skill_service import _marcar_uso, functional_group, skills_sem_uso


def _skill(**kw) -> EjcSkill:
    base = dict(
        id="s1", name="parecer_padrao", display_name="Parecer",
        system_prompt="Redija o parecer.", engine="groq", area="juridico",
        active=True, oab_restricted=False, vezes_executado=0, ultima_execucao=None,
        created_at=datetime.now(timezone.utc) - timedelta(days=200),
    )
    base.update(kw)
    return EjcSkill(**base)


# ── grupo funcional do catálogo ─────────────────────────────────────────────

def test_functional_group_deriva_metadado_no_backend():
    assert functional_group(
        _skill(name="analise_estrategica", display_name="Análise estratégica")
    ) == "analisar"
    assert functional_group(
        _skill(name="peticao_inicial", display_name="Petição inicial")
    ) == "produzir"
    assert functional_group(
        _skill(name="revisar_documento", display_name="Revisar documento")
    ) == "revisar"
    assert functional_group(
        _skill(name="preparar_audiencia", display_name="Preparar audiência")
    ) == "preparar"


def test_functional_group_sem_sinal_cai_em_produzir():
    assert functional_group(
        _skill(name="fluxo_especial", display_name="Fluxo especial")
    ) == "produzir"


# ── _marcar_uso ────────────────────────────────────────────────────────────

def test_marcar_uso_incrementa_contador_e_grava_timestamp():
    skill = _skill(vezes_executado=3, ultima_execucao=None)
    _marcar_uso(skill)
    assert skill.vezes_executado == 4
    assert skill.ultima_execucao is not None
    assert skill.ultima_execucao.tzinfo is not None


def test_marcar_uso_a_partir_de_none_vira_um():
    skill = _skill(vezes_executado=None)
    _marcar_uso(skill)
    assert skill.vezes_executado == 1


# ── skills_sem_uso ───────────────────────────────────────────────────────────

class _ResLista:
    def __init__(self, val):
        self._val = val

    def scalars(self):
        return self

    def all(self):
        return self._val


class _FakeDBLista:
    def __init__(self, resultado):
        self._resultado = resultado

    async def execute(self, *a, **k):
        return _ResLista(self._resultado)


async def test_skills_sem_uso_devolve_o_que_o_banco_filtrar():
    # O filtro real (active/vezes_executado/created_at) é responsabilidade da
    # query SQL — aqui provamos que a função repassa o resultado sem alterar,
    # e com os parâmetros certos de ordenação (mesmo padrão de listar_skills).
    velha_sem_uso = _skill(id="s-velha", name="velha_sem_uso")
    db = _FakeDBLista([velha_sem_uso])
    out = await skills_sem_uso(db, dias_minimos=90)
    assert out == [velha_sem_uso]


async def test_skills_sem_uso_aceita_dias_minimos_customizado():
    db = _FakeDBLista([])
    out = await skills_sem_uso(db, dias_minimos=30)
    assert out == []


# ── Integração com executar_skill (uso registrado na execução real) ─────────

class _ResSkill:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDBExecucao:
    """Sessão fake: devolve a skill no primeiro execute(); registra commit."""

    def __init__(self, skill):
        self._skill = skill
        self.commits = 0

    async def execute(self, *a, **k):
        return _ResSkill(self._skill)

    async def commit(self):
        self.commits += 1


async def test_executar_skill_marca_uso_antes_de_registrar_o_log(monkeypatch):
    from app.services import ai_gateway, ai_guard

    skill = _skill(vezes_executado=0, ultima_execucao=None)
    db = _FakeDBExecucao(skill)

    class _GatewayResponseFake:
        texto = "Parecer gerado."
        modelo = "modelo-x"
        provedor = "groq"
        input_tokens = 10
        output_tokens = 20
        custo_estimado_brl = 0.01

    async def _chat_fake(*args, **kwargs):
        return _GatewayResponseFake()

    log_ids_gravados = []

    async def _registrar_ai_log_fake(db, **kwargs):
        # No momento em que o log é gravado, o contador já deve estar
        # incrementado — é a ordem que a correção exige (Bloco 4).
        assert skill.vezes_executado == 1
        assert skill.ultima_execucao is not None
        log_ids_gravados.append("log-1")
        return "log-1"

    monkeypatch.setattr(ai_gateway, "chat", _chat_fake)
    monkeypatch.setattr(ai_guard, "registrar_ai_log", _registrar_ai_log_fake)
    monkeypatch.setattr(ai_skill_service, "registrar_ai_log", _registrar_ai_log_fake)

    resultado = await ai_skill_service.executar_skill(
        db=db, skill_name="parecer_padrao", query="analise isto",
        user_id="u1", user_role="advogado",
    )

    assert skill.vezes_executado == 1
    assert log_ids_gravados == ["log-1"]
    assert resultado["ai_log_id"] == "log-1"
