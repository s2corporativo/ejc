"""Invariantes das áreas do direito no pipeline de geração de peças.

Trava regressões silenciosas ao adicionar/alterar ramos: toda área de
AREAS_DIREITO é aceita pelo validador do router (mesma lista, normalizada e
sem duplicatas), todo mapeamento área→prompt aponta para chave REAL de
SYSTEM_PROMPTS (anti-drift) e a especialização injetada nas etapas 2/7 nunca
duplica BASE_PROMPT/AVISO_RASCUNHO.
"""
import unicodedata

from app.services.peca_service import (
    AREAS_DIREITO,
    _AREA_PROMPT_KEY,
    _especializacao_area,
)
from app.services.system_prompts import AVISO_RASCUNHO, BASE_PROMPT, SYSTEM_PROMPTS

# Ramos que o sistema cobre (frontend ramosConfig + prompts especializados) e
# que o pipeline DEVE aceitar — pedir peça de área "empresarial" dava 422.
_RAMOS_OBRIGATORIOS = {
    "trabalhista", "civil", "previdenciario", "tributario",
    "criminal", "consumidor", "administrativo", "familia",
    "empresarial", "ambiental", "bancario", "imobiliario",
    "sucessoes", "constitucional", "juizados", "digital_lgpd",
    "transito",
}


def test_toda_area_e_aceita_pelo_validador_do_router():
    # O router valida com `req.area_direito not in AREAS_DIREITO` sobre a MESMA
    # lista importada de peca_service — garante que é o mesmo objeto (sem cópia
    # que pudesse divergir) e que toda área passa no check do endpoint.
    from app.routers.peca_geracao import AREAS_DIREITO as AREAS_ROUTER

    assert AREAS_ROUTER is AREAS_DIREITO
    for area in AREAS_DIREITO:
        assert area in AREAS_ROUTER, f"área '{area}' rejeitada pelo router (422)"


def test_areas_sem_duplicatas_e_normalizadas():
    assert len(AREAS_DIREITO) == len(set(AREAS_DIREITO)), "área duplicada em AREAS_DIREITO"
    for area in AREAS_DIREITO:
        assert area == area.strip().lower(), f"área '{area}' não normalizada (minúsculas)"
        sem_acento = "".join(
            c for c in unicodedata.normalize("NFKD", area) if not unicodedata.combining(c)
        )
        assert area == sem_acento, f"área '{area}' contém acento"
        assert " " not in area, f"área '{area}' contém espaço (use snake_case)"


def test_ramos_do_sistema_estao_em_areas_direito():
    faltando = _RAMOS_OBRIGATORIOS - set(AREAS_DIREITO)
    assert not faltando, f"ramos do sistema ausentes de AREAS_DIREITO: {sorted(faltando)}"


def test_toda_area_tem_entrada_no_mapa_de_prompts():
    # Anti-drift: área nova em AREAS_DIREITO sem decisão explícita de prompt
    # (chave ou None) quebra aqui, em vez de cair silenciosamente no genérico.
    for area in AREAS_DIREITO:
        assert area in _AREA_PROMPT_KEY, \
            f"área '{area}' sem entrada em _AREA_PROMPT_KEY (mapeie a chave ou None)"


def test_toda_chave_nao_none_existe_em_system_prompts():
    for area, chave in _AREA_PROMPT_KEY.items():
        if chave is None:
            continue
        assert chave in SYSTEM_PROMPTS, \
            f"área '{area}': chave '{chave}' ausente em SYSTEM_PROMPTS (drift)"


def test_especializacao_nao_duplica_base_prompt_nem_aviso():
    # O trecho injetado nas etapas 2/7 é só o CORPO do prompt de área — se
    # carregasse BASE_PROMPT/AVISO_RASCUNHO, duplicaria identidade e avisos.
    for area in AREAS_DIREITO:
        bloco = _especializacao_area(area)
        assert bloco.startswith("Especialização:"), f"área '{area}': bloco sem cabeçalho"
        assert area in bloco, f"área '{area}': nome do ramo ausente do bloco"
        assert "## IDENTIDADE" not in bloco, f"área '{area}': BASE_PROMPT duplicado"
        assert "REVISÃO HUMANA OBRIGATÓRIA" not in bloco, \
            f"área '{area}': AVISO_RASCUNHO duplicado"


def test_especializacao_com_prompt_dedicado_traz_corpo():
    # Áreas com prompt dedicado devem injetar conteúdo além da linha-cabeçalho…
    for area, chave in _AREA_PROMPT_KEY.items():
        if chave is None or chave not in SYSTEM_PROMPTS:
            continue
        prompt_area = SYSTEM_PROMPTS[chave]
        if not (prompt_area.startswith(BASE_PROMPT) and prompt_area.endswith(AVISO_RASCUNHO)):
            continue  # fora do padrão → fallback seguro (só o nome do ramo)
        bloco = _especializacao_area(area)
        assert "\n" in bloco, f"área '{area}': corpo da especialização não injetado"


def test_area_sem_prompt_dedicado_usa_fallback_sem_erro():
    # …e áreas sem prompt dedicado funcionam com o genérico + nome do ramo.
    assert _especializacao_area("transito") == \
        "Especialização: use rigorosamente o repertório do ramo transito."
    # Área desconhecida também não pode explodir (fail-safe).
    assert _especializacao_area("area_inexistente_xyz").startswith("Especialização:")
