"""Base anti-alucinação (IA-04) — injeção da identidade nas tarefas de prosa."""
from app.services.legal_base import aplicar_base, garantir_identidade, _TASKS_COM_BASE


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


# ── garantir_identidade: barreira INCONDICIONAL (canais autorais do usuário) ──

def test_garantir_identidade_independe_do_task_type():
    # Ao contrário de aplicar_base, injeta mesmo sem passar task_type nenhum —
    # cobre EjcSkill (area financeiro/operacional) e PromptJuridico (task livre).
    out = garantir_identidade(_msgs())
    assert "[IDENTIDADE]" in out[0]["content"]


def test_garantir_identidade_cria_system_para_mensagem_so_de_usuario():
    # PromptJuridico envia só {"role": "user", ...} — precisa ganhar o system.
    out = garantir_identidade([{"role": "user", "content": "minuta"}])
    assert out[0]["role"] == "system"
    assert "[IDENTIDADE]" in out[0]["content"]
    assert out[-1]["role"] == "user"


def test_garantir_identidade_idempotente():
    once = garantir_identidade([{"role": "user", "content": "x"}])
    twice = garantir_identidade(once)
    assert twice[0]["content"].count("[IDENTIDADE]") == 1


def test_garantir_identidade_lista_vazia():
    out = garantir_identidade([])
    assert out[0]["role"] == "system"
    assert "[IDENTIDADE]" in out[0]["content"]


def test_pipeline_runtime_combinado_nao_duplica():
    # Garantia (a) da revisão: o canal autoral chama garantir_identidade e, em
    # seguida, o gateway chama aplicar_base. Mesmo quando o task_type ESTÁ em
    # _TASKS_COM_BASE (ex.: skill juridico → elaboracao_peca), não pode duplicar.
    task = next(iter(_TASKS_COM_BASE))
    autoral = garantir_identidade([
        {"role": "system", "content": "Prompt autoral da skill."},
        {"role": "user", "content": "pergunta"},
    ])
    final = aplicar_base(autoral, task)
    assert final[0]["content"].count("[IDENTIDADE]") == 1
