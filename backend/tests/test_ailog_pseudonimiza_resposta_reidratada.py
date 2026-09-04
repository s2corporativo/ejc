"""A resposta REIDRATADA não chega crua ao AILog (revisão automatizada do PR).

Achado revisado em 03/09/2026: o gateway grava em `AILog.resposta` o texto já
reidratado (marcadores trocados de volta pelos nomes reais), o que pareceria
deixar PII no registro de auditoria. A barreira existe, mas UMA CAMADA ABAIXO —
o `@validates("resposta", "critica_adversarial")` do modelo. Estes testes
travam essa garantia: ela é invisível no call site e sumiria em silêncio se
alguém trocasse o ORM por um INSERT em lote.
"""
from __future__ import annotations

import pytest

from app.models.ai_log import AILog, AIStatusHITL, pseudonimizar_texto_auditoria

pytestmark = pytest.mark.anyio

_NOME = "Joaquim Bernardes de Almeida"
_CPF = "529.982.247-25"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_validates_pseudonimiza_resposta_no_construtor():
    log = AILog(id="x", user_id="u1", tipo_uso="analise_caso",
                prompt_sanitizado="p", pii_removida=True,
                resposta=f"Conforme alegado por {_NOME}, CPF {_CPF}, cabe repetição.",
                status_hitl=AIStatusHITL.gerado)
    assert _NOME not in (log.resposta or "")
    assert _CPF not in (log.resposta or "")


def test_validates_pseudonimiza_critica_adversarial():
    log = AILog(id="x", user_id="u1", tipo_uso="analise_caso",
                prompt_sanitizado="p", pii_removida=True, resposta="ok",
                critica_adversarial=f"Risco: a tese de {_NOME} não tem precedente.")
    assert _NOME not in (log.critica_adversarial or "")


def test_atribuicao_posterior_tambem_passa_pela_barreira():
    # `adversarial.py` grava por atribuição (log.critica_adversarial = ...);
    # o validador precisa valer nesse caminho, não só no construtor.
    log = AILog(id="x", user_id="u1", tipo_uso="analise_caso",
                prompt_sanitizado="p", pii_removida=True, resposta="ok")
    log.resposta = f"Parecer sobre {_NOME}."
    assert _NOME not in (log.resposta or "")


def test_referencia_jurisprudencial_completa_sobrevive():
    # A pseudonimização não pode destruir o que o gate de citações verifica: a
    # referência com tribunal + marcador de precedente + data permanece legível.
    cnj = "0710589-79.2020.8.02.0001"
    texto = (f"═══ ANÁLISE ═══\nO TJMG, no acórdão {cnj}, julgado em 12/03/2021, "
             f"fixou a tese. Autor: {_NOME}.")
    limpo = pseudonimizar_texto_auditoria(texto)
    assert cnj in limpo, "referência jurisprudencial completa é prova auditável"
    assert "═══ ANÁLISE ═══" in limpo, "marcador estrutural do sistema não é PII"
    assert _NOME not in limpo


def test_numero_do_processo_do_cliente_e_mascarado():
    # Sem tribunal/precedente/data em volta, o número é o processo do próprio
    # cliente — PII estrutural, não citação.
    texto = f"O processo 0710589-79.2020.8.02.0001 de {_NOME} está em curso."
    limpo = pseudonimizar_texto_auditoria(texto)
    assert "0710589-79.2020.8.02.0001" not in limpo
    assert _NOME not in limpo


async def test_registrar_ai_log_persiste_resposta_ja_pseudonimizada():
    from app.services.ai_guard import registrar_ai_log

    persistidos: list = []

    class _FakeDB:
        def add(self, obj):
            persistidos.append(obj)

        async def commit(self):
            return None

    await registrar_ai_log(
        _FakeDB(), user_id="u1", tipo_uso="analise_caso", case_id=None,
        prompt_sanitizado="pergunta sanitizada", pii_removida=True,
        resposta=f"Resposta reidratada citando {_NOME} e o CPF {_CPF}.",
        modelo="anthropic/claude-opus-4-8",
    )

    assert len(persistidos) == 1
    gravado = persistidos[0].resposta or ""
    assert _NOME not in gravado
    assert _CPF not in gravado
