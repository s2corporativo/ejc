"""GET /ai/logs — guardrail jurídico determinístico aplicado NA LEITURA
(Issue #554). Cobre os achados de review #5 e #6 (Codex, PR #703):

  5. Idempotência: reler um log JÁ corrigido não pode reescrever/duplicar o
     próprio aviso de correção.
  6. HITL: quando a correção acontece AGORA, na leitura, de um log LEGADO já
     marcado `revisado`/`aplicado`, a resposta não pode expor o status antigo
     como se aplicasse ao texto CORRIGIDO — precisa reexpor como pendente de
     revisão.
"""
from __future__ import annotations

from app.models.ai_log import AIRiscoIA, AIStatusHITL, AITipoUso
from app.routers.ai import listar_logs


class _Role:
    def __init__(self, value="socio"):
        self.value = value


class _CU:
    id = "user-1"
    role = _Role()


class _FakeLog:
    def __init__(self, resposta, status_hitl=AIStatusHITL.gerado,
                 revisado_por=None, revisado_em="2026-01-01"):
        self.id = "log-1"
        self.tipo_uso = AITipoUso.outro
        self.modelo = "groq/modelo-x"
        self.status_hitl = status_hitl
        self.revisado_por = revisado_por
        self.revisado_em = revisado_em
        self.pii_removida = False
        self.risco_ia = AIRiscoIA.medio_risco
        self.case_id = None
        self.created_at = "2026-01-01"
        self.resposta = resposta
        self.critica_adversarial = None


class _ResultLogs:
    def __init__(self, rows):
        self._rows = rows

    def scalar(self):
        return len(self._rows)

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DBLogs:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *a, **k):
        return _ResultLogs(self._rows)


_TEXTO_ERRADO = (
    "Reconheço a PRESCRIÇÃO da pretensão. Julgo o processo extinto sem "
    "resolução de mérito, nos termos do art. 485 do CPC."
)


async def test_correcao_na_leitura_de_log_novo_gerado_nao_mexe_no_hitl():
    # Log recém-criado (status "gerado", nunca revisado) — a correção na
    # leitura acontece normalmente, sem necessidade de reexpor nada.
    log = _FakeLog(_TEXTO_ERRADO, status_hitl=AIStatusHITL.gerado)
    r = await listar_logs(page=1, page_size=20, case_id=None, db=_DBLogs([log]), cu=_CU())

    linha = r["data"][0]
    assert "COM resolução de mérito" in linha["resposta"]
    assert linha["corrigido_automaticamente_na_leitura"] is True
    assert linha["status_hitl"] == "gerado"


async def test_correcao_na_leitura_de_log_legado_ja_revisado_reseta_status_exposto():
    # Achado #6: log LEGADO (persistido antes deste guardrail existir), já
    # marcado "revisado" por um humano que viu o texto ERRADO. A leitura
    # corrige agora — não pode expor "revisado" como se aplicasse à versão
    # corrigida (o humano nunca viu essa versão).
    log = _FakeLog(
        _TEXTO_ERRADO, status_hitl=AIStatusHITL.revisado,
        revisado_por="advogado-x", revisado_em="2026-01-01",
    )
    r = await listar_logs(page=1, page_size=20, case_id=None, db=_DBLogs([log]), cu=_CU())

    linha = r["data"][0]
    assert "COM resolução de mérito" in linha["resposta"]
    assert linha["corrigido_automaticamente_na_leitura"] is True
    assert linha["status_hitl"] == "gerado"
    assert linha["revisado_por"] is None
    assert linha["revisado_em"] is None
    # O dado no banco (objeto ORM) não foi tocado — só a resposta desta
    # leitura; nenhuma migration de dados no escopo desta Issue.
    assert log.status_hitl == AIStatusHITL.revisado
    assert log.revisado_por == "advogado-x"


async def test_correcao_na_leitura_de_log_legado_ja_aplicado_reseta_status_exposto():
    log = _FakeLog(
        _TEXTO_ERRADO, status_hitl=AIStatusHITL.aplicado,
        revisado_por="advogado-x", revisado_em="2026-01-01",
    )
    r = await listar_logs(page=1, page_size=20, case_id=None, db=_DBLogs([log]), cu=_CU())

    linha = r["data"][0]
    assert linha["status_hitl"] == "gerado"
    assert linha["revisado_por"] is None


async def test_log_ja_corrigido_nao_reaplica_nem_reseta_hitl_de_novo():
    # Achado #5: reler um log que JÁ contém o aviso de correção (persistido
    # numa execução POSTERIOR a esta correção, já revisado depois de ver o
    # texto CORRETO) não pode reaplicar o guardrail — ele encontraria as
    # palavras-gatilho dentro do próprio aviso. Também não deve resetar o
    # HITL, porque a correção não está acontecendo agora: já tinha acontecido
    # antes da revisão humana.
    from app.services.ai import juridico_guardrails

    texto_ja_corrigido, houve = juridico_guardrails.aplicar_guardrail_merito(_TEXTO_ERRADO)
    assert houve is True

    log = _FakeLog(
        texto_ja_corrigido, status_hitl=AIStatusHITL.aplicado,
        revisado_por="advogado-x", revisado_em="2026-01-01",
    )
    r = await listar_logs(page=1, page_size=20, case_id=None, db=_DBLogs([log]), cu=_CU())

    linha = r["data"][0]
    assert linha["resposta"] == texto_ja_corrigido
    assert linha["resposta"].count("GUARDRAIL DETERMINÍSTICO") == 1
    assert linha["corrigido_automaticamente_na_leitura"] is False
    # Já tinha sido revisado ANTES desta leitura, e a leitura não corrigiu
    # nada agora — o status_hitl legítimo é preservado.
    assert linha["status_hitl"] == "aplicado"
    assert linha["revisado_por"] == "advogado-x"


async def test_resposta_sem_erro_nao_e_alterada_e_hitl_preservado():
    texto_correto = "Reconheço a prescrição. Sentença de mérito, art. 487, II, do CPC."
    log = _FakeLog(
        texto_correto, status_hitl=AIStatusHITL.revisado,
        revisado_por="advogado-x",
    )
    r = await listar_logs(page=1, page_size=20, case_id=None, db=_DBLogs([log]), cu=_CU())

    linha = r["data"][0]
    assert linha["resposta"] == texto_correto
    assert linha["corrigido_automaticamente_na_leitura"] is False
    assert linha["status_hitl"] == "revisado"
    assert linha["revisado_por"] == "advogado-x"
