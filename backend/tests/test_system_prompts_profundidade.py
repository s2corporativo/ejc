"""Profundidade dos prompts que serviam agentes de mérito (P2, #1150).

A auditoria de 18/08 mediu: quatro chaves de prompt entregavam a agentes
jurídicos ou uma FRASE (`bancario`, `seguranca_lgpd`) ou o prompt de OUTRA
tarefa (`pesquisa_juridica` e `audiencia` rodavam a análise estratégica de
caso, devolvendo relatório de nove seções onde se pedia resposta com fonte ou
roteiro de sala). Estes testes fixam o piso: prompt próprio, método explícito e
regra de honestidade epistêmica.
"""
from app.services.system_prompts import SYSTEM_PROMPTS
from app.services.system_prompts.analise_caso import PROMPT_ANALISE_CASO

# Chaves que servem agentes internos de conteúdo jurídico de mérito.
_CHAVES = ("bancario", "seguranca_lgpd", "pesquisa_juridica", "audiencia")


def test_chaves_de_merito_tem_prompt_proprio():
    for chave in _CHAVES:
        assert SYSTEM_PROMPTS[chave] != PROMPT_ANALISE_CASO, chave


def test_chaves_de_merito_nao_sao_uma_frase():
    """Piso grosseiro de profundidade — um one-liner não sustenta agente."""
    for chave in _CHAVES:
        corpo = SYSTEM_PROMPTS[chave]
        assert "## FUNÇÃO:" in corpo, chave
        assert len(corpo) > 4000, (chave, len(corpo))


def test_prompts_de_merito_exigem_fonte_ou_admitem_a_lacuna():
    for chave in _CHAVES:
        corpo = SYSTEM_PROMPTS[chave].lower()
        assert "verificar" in corpo or "sem base verificável" in corpo, chave


def test_bancario_ancora_as_teses_na_data_do_contrato():
    """Capitalização e tarifas mudam com a data — transplantar tese é o erro."""
    from app.services.system_prompts.bancario import PROMPT_BANCARIO

    assert "31/03/2000" in PROMPT_BANCARIO          # marco da capitalização
    assert "Súmula 539 STJ" in PROMPT_BANCARIO
    assert "Súmula 382 STJ" in PROMPT_BANCARIO      # 12% ao ano não é abusivo per se
    assert "Súmula 479 STJ" in PROMPT_BANCARIO      # fortuito interno
    assert "Lei 14.905/2024" in PROMPT_BANCARIO     # juros/correção supletivos
    assert "Dec.-Lei 911/1969" in PROMPT_BANCARIO


def test_lgpd_nao_trata_consentimento_como_base_padrao():
    from app.services.system_prompts.lgpd_digital import PROMPT_LGPD_DIGITAL

    assert "art. 11" in PROMPT_LGPD_DIGITAL          # dado sensível tem regime próprio
    assert "Consentimento é UMA base entre" in PROMPT_LGPD_DIGITAL
    # O sigilo do advogado é dever autônomo, mais restritivo que a LGPD.
    assert "EOAB" in PROMPT_LGPD_DIGITAL
    assert "sigilo" in PROMPT_LGPD_DIGITAL.lower()
    # A resposta não pode reproduzir o segredo que analisa.
    assert "nunca reproduza" in PROMPT_LGPD_DIGITAL.lower()


def test_audiencia_identifica_o_rito_antes_do_roteiro():
    from app.services.system_prompts.audiencia import PROMPT_AUDIENCIA

    for marca in ("CPC", "CLT arts. 843-852", "Lei 9.099/95", "CPP arts. 400-405"):
        assert marca in PROMPT_AUDIENCIA, marca
    # Regras de sala que decidem o caso: confissão, contradita e o protesto.
    assert "art. 385 §1º" in PROMPT_AUDIENCIA
    assert "art. 457 §1º" in PROMPT_AUDIENCIA
    assert "CONSIGNAR" in PROMPT_AUDIENCIA


def test_pesquisa_juridica_impoe_hierarquia_e_contraponto():
    from app.services.system_prompts.pesquisa_juridica import PROMPT_PESQUISA_JURIDICA

    assert "art. 927" in PROMPT_PESQUISA_JURIDICA     # precedente vinculante
    assert "CONTRAPONTO" in PROMPT_PESQUISA_JURIDICA
    assert "SEM BASE VERIFICÁVEL" in PROMPT_PESQUISA_JURIDICA
    assert "GRAU DE CONFIANÇA" in PROMPT_PESQUISA_JURIDICA


def test_audiencia_usa_modelo_forte():
    """Ato irrepetível não roda no modelo econômico."""
    from app.services.system_prompts.router import (
        CONFIGURACOES,
        TarefaIA,
        _MARITACA,
    )

    cfg = CONFIGURACOES[TarefaIA.AUDIENCIA]
    assert cfg.provider == "maritaca"
    assert cfg.model == _MARITACA
    assert cfg.max_tokens >= 3000
