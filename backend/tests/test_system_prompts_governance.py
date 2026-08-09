from app.services.system_prompts.base import BASE_PROMPT, AVISO_RASCUNHO
from app.services.system_prompts.juizados import PROMPT_JUIZADOS
from app.services.system_prompts.minutas import PROMPT_MINUTAS
from app.services.system_prompts.padrao_ouro import PADRAO_OURO_PECA


def test_prompt_base_distingue_forma_completa_de_autorizacao_para_protocolo():
    assert "FORMATO\n   PROFISSIONAL de protocolo" in BASE_PROMPT
    assert "estado no EJC continua RASCUNHO" in PADRAO_OURO_PECA
    assert "aprovação HITL" in BASE_PROMPT
    assert "NUNCA gere peça final para protocolo" not in BASE_PROMPT
    assert "NÃO está aprovado para protocolo" in AVISO_RASCUNHO


def test_minutas_podem_ser_completas_sem_perder_estado_rascunho():
    assert "MINUTAS tecnicamente completas" in PROMPT_MINUTAS
    assert "permanece RASCUNHO" in PROMPT_MINUTAS
    assert "aprovação HITL" in PROMPT_MINUTAS
    assert "FORMA PROFISSIONAL PARA REVISÃO" in PROMPT_MINUTAS
    assert "=== NOTA INTERNA — NÃO PROTOCOLAR ===" in PROMPT_MINUTAS


def test_juizados_separam_jec_jef_e_jefp():
    assert "NÃO trate JEC, JEF e JEFP como um único regime" in PROMPT_JUIZADOS
    assert "art. 3º, §3º" in PROMPT_JUIZADOS
    assert "art. 17, §4º" in PROMPT_JUIZADOS
    assert "art. 13, §5º" in PROMPT_JUIZADOS
    assert "NÃO transplante esta regra automaticamente para JEF/JEFP" in PROMPT_JUIZADOS
    assert "o ajuizamento implica renúncia ao que exceder a alçada" not in PROMPT_JUIZADOS


def test_juizados_nao_generalizam_prazo_diferenciado_ou_jus_postulandi():
    assert "NÃO presuma prazo em dobro ou prazo diferenciado" in PROMPT_JUIZADOS
    assert "Lei 10.259/2001 art. 9º" in PROMPT_JUIZADOS
    assert "Lei 12.153/2009 art. 7º" in PROMPT_JUIZADOS
    assert "No JEC, a assistência por advogado é" in PROMPT_JUIZADOS
    assert "No JEF, considere a regra própria de representação" in PROMPT_JUIZADOS
    assert "Não generalize jus postulandi" in PROMPT_JUIZADOS


def test_juizados_exigem_fonte_verificavel_para_norma_e_sumula():
    assert "Cite somente dispositivo confirmado nas FONTES fornecidas" in PROMPT_JUIZADOS
    assert "confirme-a na fonte oficial do RAG" in PROMPT_JUIZADOS
    assert "Sem fonte verificável" in PROMPT_JUIZADOS
