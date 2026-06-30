"""Base anti-alucinação (IA-04) — injeção da identidade nas tarefas de prosa."""
from app.services.legal_base import aplicar_base


def _msgs():
    return [{"role": "system", "content": "Instrução do sistema."},
            {"role": "user", "content": "pergunta"}]


def test_tarefas_de_prosa_recebem_base():
    for task in ("estrategia", "auditoria_peca", "elaboracao_peca",
                 "redacao_peca", "chat_rapido"):
        out = aplicar_base(_msgs(), task)
        assert "[IDENTIDADE]" in out[0]["content"], task


def test_saida_estruturada_e_resumo_nao_recebem():
    # JSON de extração e resumo ficam de fora (não quebrar formato).
    for task in ("analise_juridica", "resumo"):
        out = aplicar_base(_msgs(), task)
        assert "[IDENTIDADE]" not in out[0]["content"], task


def test_idempotente():
    once = aplicar_base(_msgs(), "estrategia")
    twice = aplicar_base(once, "estrategia")
    assert once[0]["content"].count("[IDENTIDADE]") == 1
    assert twice[0]["content"].count("[IDENTIDADE]") == 1


def test_cria_system_se_nao_houver():
    out = aplicar_base([{"role": "user", "content": "oi"}], "redacao_peca")
    assert out[0]["role"] == "system"
    assert "[IDENTIDADE]" in out[0]["content"]
