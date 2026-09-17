"""Inventário canônico dos prompts do núcleo (dívida 5.3, #1150).

Sem um lugar único que diga quais prompts existem, quem os consome e qual
versão produziu uma saída, um erro jurídico numa peça não é rastreável até a
instrução que o causou. Pior: uma chave consumida e NÃO registrada faz o núcleo
cair no prompt `default` — o advogado recebe resposta genérica onde deveria
haver especialização, sem nenhum erro visível.
"""
from app.services.system_prompts import PROMPT_EXTRAS, SYSTEM_PROMPTS
from app.services.system_prompts.inventario import (
    chaves_fantasma,
    impressao,
    inventario,
    resumo,
    versao_do_prompt,
)


def test_inventario_cobre_todo_o_registro():
    chaves = {(x["tipo"], x["chave"]) for x in inventario()}
    assert chaves == (
        {("system", k) for k in SYSTEM_PROMPTS}
        | {("extra", k) for k in PROMPT_EXTRAS}
    )


def test_nenhuma_chave_fantasma():
    """Agente/tarefa apontando para prompt inexistente cai no `default`."""
    assert chaves_fantasma() == []


def test_nenhum_prompt_orfao():
    """Prompt registrado que ninguém consome é dívida silenciosa."""
    assert resumo()["orfaos"] == []


def test_aposentados_sao_exatamente_os_da_consolidacao_38_para_8():
    """Trava o conjunto: um órfão NOVO deve cair em 'orfaos' (falhar o teste
    acima), não ser silenciosamente absorvido aqui."""
    from app.services.system_prompts.inventario import PROMPTS_APOSENTADOS

    assert resumo()["aposentados"] == sorted(PROMPTS_APOSENTADOS)
    assert PROMPTS_APOSENTADOS == {
        "agrario", "agronegocio", "contratual", "eleitoral", "internacional",
        "medico", "previdenciario", "saude", "transito",
    }


def test_versao_muda_com_o_conteudo_e_e_estavel():
    assert impressao("texto A") == impressao("texto A")
    assert impressao("texto A") != impressao("texto A ")
    assert len(impressao("qualquer")) == 12


def test_versao_do_prompt_resolve_chave_registrada():
    assert versao_do_prompt("prazos") == impressao(SYSTEM_PROMPTS["prazos"])
    assert versao_do_prompt("chave-que-nao-existe") is None


def test_consumidores_nomeiam_agente_e_tarefa():
    linha = next(x for x in inventario() if x["chave"] == "prazos")
    assert any(c.startswith("tarefa:") for c in linha["consumidores"])
    linha_peca = next(x for x in inventario() if x["chave"] == "minutas")
    assert linha_peca["consumidores"]


def test_saida_do_orquestrador_carrega_a_versao_do_prompt():
    """A rastreabilidade só serve se chegar ao consumidor da resposta."""
    import inspect

    from app.services.ai.core import orchestrator

    fonte = inspect.getsource(orchestrator)
    assert '"prompt_versao": prompt_versao(system_prompt)' in fonte
    assert '"prompt_key": agente.prompt_key' in fonte


def test_payload_da_peca_carrega_a_versao_do_prompt():
    import inspect

    from app.services import peca_service

    fonte = inspect.getsource(peca_service)
    assert '"prompt_versao": prompt_versao_peca' in fonte
