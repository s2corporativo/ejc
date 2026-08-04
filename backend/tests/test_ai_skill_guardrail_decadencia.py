"""Integração do guardrail jurídico determinístico (Issue #554) com
`ai_skill_service.executar_skill` — prova que uma resposta que classifica
prescrição/decadência como "extinção sem resolução de mérito" é CORRIGIDA
antes de chegar ao usuário (campo `conteudo` da resposta da API), e que o
aviso obrigatório de revisão humana (HITL) menciona o problema.

Escopo: só as skills `prescricao-decadencia` e `simulador-defesa-adversarial`
— uma terceira skill com o mesmo texto errado prova que o guardrail NÃO
altera o comportamento de skills fora do escopo da Issue.
"""
from __future__ import annotations

from app.models.ai_skill import EjcSkill
from app.services import ai_skill_service


class _ResSkill:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val


class _FakeDBExecucao:
    def __init__(self, skill):
        self._skill = skill

    async def execute(self, *a, **k):
        return _ResSkill(self._skill)

    async def commit(self):
        pass


def _skill(name: str, **kw) -> EjcSkill:
    base = dict(
        id="s1", name=name, display_name="Skill de teste",
        system_prompt="Prompt de teste.", engine="groq", area="estrategia",
        active=True, oab_restricted=False, requires_human_review=True,
        vezes_executado=0, ultima_execucao=None,
    )
    base.update(kw)
    return EjcSkill(**base)


_TEXTO_ERRADO = (
    "Reconheço a PRESCRIÇÃO da pretensão. Julgo o processo extinto sem "
    "resolução de mérito, nos termos do art. 485 do CPC."
)


def _mockar_gateway_e_log(monkeypatch, texto_resposta: str):
    from app.services import ai_gateway, ai_guard

    class _GatewayResponseFake:
        texto = texto_resposta
        modelo = "modelo-x"
        provedor = "groq"
        input_tokens = 10
        output_tokens = 20
        custo_estimado_brl = 0.01

    async def _chat_fake(*args, **kwargs):
        return _GatewayResponseFake()

    respostas_gravadas = {}

    async def _registrar_ai_log_fake(db, **kwargs):
        respostas_gravadas["resposta"] = kwargs.get("resposta")
        return "log-1"

    monkeypatch.setattr(ai_gateway, "chat", _chat_fake)
    monkeypatch.setattr(ai_guard, "registrar_ai_log", _registrar_ai_log_fake)
    monkeypatch.setattr(ai_skill_service, "registrar_ai_log", _registrar_ai_log_fake)
    return respostas_gravadas


async def test_prescricao_decadencia_corrige_qualificacao_de_merito(monkeypatch):
    skill = _skill("prescricao-decadencia")
    db = _FakeDBExecucao(skill)
    gravados = _mockar_gateway_e_log(monkeypatch, _TEXTO_ERRADO)

    resultado = await ai_skill_service.executar_skill(
        db=db, skill_name="prescricao-decadencia", query="analise o prazo",
        user_id="u1", user_role="advogado",
    )

    # A resposta devolvida AO USUÁRIO já vem corrigida...
    assert "extinto COM resolução de mérito (art. 487, II, do CPC)" in resultado["conteudo"]
    assert "GUARDRAIL DETERMINÍSTICO" in resultado["conteudo"]
    # ...o AILog persistido reflete a MESMA correção (não só a leitura futura)...
    assert "extinto COM resolução de mérito" in gravados["resposta"]
    # ...e o aviso força revisão humana (HITL) citando o problema encontrado.
    assert resultado["requer_revisao"] is True
    assert "487, II" in resultado["aviso"]


async def test_simulador_defesa_adversarial_corrige_qualificacao_de_merito(monkeypatch):
    skill = _skill("simulador-defesa-adversarial")
    db = _FakeDBExecucao(skill)
    _mockar_gateway_e_log(monkeypatch, _TEXTO_ERRADO)

    resultado = await ai_skill_service.executar_skill(
        db=db, skill_name="simulador-defesa-adversarial", query="critique a peça",
        user_id="u1", user_role="advogado",
    )

    assert "extinto COM resolução de mérito (art. 487, II, do CPC)" in resultado["conteudo"]


async def test_skill_fora_do_escopo_da_issue_nao_e_alterada(monkeypatch):
    # Controle negativo: mesma resposta errada, skill DIFERENTE das duas da
    # Issue #554 — o guardrail não deve tocar no texto (escopo restrito).
    skill = _skill("outra-skill-qualquer")
    db = _FakeDBExecucao(skill)
    _mockar_gateway_e_log(monkeypatch, _TEXTO_ERRADO)

    resultado = await ai_skill_service.executar_skill(
        db=db, skill_name="outra-skill-qualquer", query="qualquer coisa",
        user_id="u1", user_role="advogado",
    )

    assert resultado["conteudo"] == _TEXTO_ERRADO
    assert "aviso" not in resultado


async def test_resposta_ja_correta_nao_ganha_aviso_extra(monkeypatch):
    texto_correto = (
        "Reconheço a prescrição. Trata-se de sentença de mérito, art. 487, "
        "II, do CPC — não de extinção sem resolução de mérito."
    )
    skill = _skill("prescricao-decadencia")
    db = _FakeDBExecucao(skill)
    _mockar_gateway_e_log(monkeypatch, texto_correto)

    resultado = await ai_skill_service.executar_skill(
        db=db, skill_name="prescricao-decadencia", query="analise o prazo",
        user_id="u1", user_role="advogado",
    )

    # Mesmo com falso-positivo eventual do regex simples, o resultado final
    # nunca reintroduz a qualificação errada nem perde a correta.
    assert "art. 487, II" in resultado["conteudo"]


async def test_cumulacao_cdc_sem_diferenciar_prazos_gera_alerta(monkeypatch):
    texto = (
        "Há vício do produto e também fato do produto que causou dano ao "
        "consumidor; aplicam-se os arts. 26 e 27 do CDC ao mesmo pedido."
    )
    skill = _skill("prescricao-decadencia")
    db = _FakeDBExecucao(skill)
    _mockar_gateway_e_log(monkeypatch, texto)

    resultado = await ai_skill_service.executar_skill(
        db=db, skill_name="prescricao-decadencia", query="analise o caso de consumo",
        user_id="u1", user_role="advogado",
    )

    assert "aviso" in resultado
    assert "cumulação automática" in resultado["aviso"]
    assert resultado["requer_revisao"] is True


async def test_cumulacao_cdc_fundamentada_separadamente_nao_gera_alerta(monkeypatch):
    texto = (
        "Pretensão de vício do produto (CDC, art. 26): prazo decadencial de "
        "90 dias. Pretensão de fato do produto — defeito que causa dano (CDC, "
        "art. 27): prazo prescricional de 5 anos. São pretensões autônomas, "
        "com termo inicial e prazo próprios."
    )
    skill = _skill("prescricao-decadencia")
    db = _FakeDBExecucao(skill)
    _mockar_gateway_e_log(monkeypatch, texto)

    resultado = await ai_skill_service.executar_skill(
        db=db, skill_name="prescricao-decadencia", query="analise o caso de consumo",
        user_id="u1", user_role="advogado",
    )

    assert "aviso" not in resultado
