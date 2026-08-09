"""Auditoria de importação/leitura de documentos e IA (2026-08).

Trava as três regressões corrigidas nesta auditoria:

1. `provas` do contrato tipado do intake era campo MORTO — `ProvaExtraida`
   nunca era instanciada em lugar nenhum do código e o esquema do prompt nem
   pedia provas de forma estruturada. A pergunta mais prática do advogado
   ("o que eu ainda preciso provar?") não chegava a lugar nenhum.
2. A leitura estratégica disparada no upload de documento existia SÓ dentro de
   `AILog.resposta` (cortada em 8.000 caracteres, sem nenhuma tela que a
   lesse): a IA lia o documento como advogado e o parecer morria no log. Agora
   vira `CaseIntelligenceSnapshot` (origem "documento"), visível em
   GET /cases/{case_id}/inteligencia.
3. O prompt de análise estratégica não pedia provas necessárias nem brechas
   preliminares (prescrição/decadência/competência/legitimidade/nulidades).

Dados 100% fictícios. Fakes locais, no padrão dos testes vizinhos.
"""
from __future__ import annotations

import json

import pytest

from app.services.documento_service import _montar_intake_result
from app.services.event_subscribers import (
    _gravar_snapshot_documento,
    _payload_leitura_documento,
)


# ── 1. provas necessárias chegam ao contrato tipado ──────────────────────────

def test_intake_result_popula_provas_necessarias():
    llm = {
        "classificacao": {"area": "civel"},
        "resumo_executivo": {"fatos": "Atraso na entrega de imóvel."},
        "provas_necessarias": [
            {"titulo": "Contrato de promessa de compra e venda",
             "tipo": "documental", "fato_probando": "Prazo de entrega pactuado",
             "ja_disponivel": True},
            {"titulo": "Comprovantes de aluguel", "tipo": "documental",
             "fato_probando": "Dano material pelo atraso", "ja_disponivel": False},
        ],
    }
    r = _montar_intake_result(llm, {})
    assert [p.titulo for p in r.provas] == [
        "Contrato de promessa de compra e venda", "Comprovantes de aluguel",
    ]
    assert r.provas[0].tipo == "documental"
    # `finalidade` é o fato probando — é o que torna a prova acionável.
    assert r.provas[0].finalidade == "Prazo de entrega pactuado"
    # Toda saída de IA continua sendo minuta.
    assert r.necessita_revisao_humana is True


@pytest.mark.parametrize("entrada", [
    {"provas_necessarias": "isto não é uma lista"},
    {"provas_necessarias": ["string solta", 42, None]},
    {"provas_necessarias": [{"tipo": "documental"}]},  # sem título: não acionável
    {},
])
def test_provas_malformadas_degradam_para_lista_vazia(entrada):
    """Fail-safe do módulo: entrada inválida nunca levanta — vira lacuna."""
    assert _montar_intake_result(entrada, {}).provas == []


# ── 2. o parecer vira snapshot do caso (antes morria no AILog) ───────────────

_PARECER = {
    "sumario_fatos": "Atraso de 26 meses na entrega de imóvel na planta.",
    "pontos_fortes": ["Quitação integral comprovada"],
    "pontos_fracos": ["Ausência de notificação prévia"],
    "estrategia": {"recomendacao": "moderado"},
    "teses_campeas": [{"titulo": "Inadimplemento contratual", "forca": "alta"},
                      {"titulo": "Dano moral in re ipsa"}],
    "riscos": [{"descricao": "Prescrição trienal", "probabilidade": "baixa"}],
    "jurimetria": {"chance_sucesso_percent": 70},
    "brechas_preliminares": {"prescricao": None, "decadencia": None,
                             "nulidades": ["Cláusula de tolerância abusiva"],
                             "observacao": "hipóteses a verificar"},
    "provas_necessarias": [{"titulo": "Contrato", "tipo": "documental",
                            "fato_probando": "prazo de entrega"}],
    "proximos_passos": [{"acao": "Notificar a ré", "prazo": "7 dias"}],
    "alertas": ["Conferir prescrição"],
    "_fontes_rag": [{"fonte": "tese interna"}],
}


def test_payload_carrega_o_raciocinio_do_advogado():
    p = _payload_leitura_documento(_PARECER, "doc-1")
    assert p["documento_id"] == "doc-1"
    assert p["pontos_fortes"] == ["Quitação integral comprovada"]
    assert p["riscos"]["pontos_fracos"] == ["Ausência de notificação prévia"]
    assert p["riscos"]["chance_exito"] == 70
    assert p["provas"][0]["fato_probando"] == "prazo de entrega"
    assert p["estrategia"] == {"recomendacao": "moderado"}
    # Contrato do payload (models/case_intelligence.py): títulos como str.
    assert p["teses"]["principal"] == "Inadimplemento contratual"
    assert p["teses"]["secundarias"] == ["Dano moral in re ipsa"]
    # Sem perder o objeto completo da tese (fundamento/força).
    assert p["teses"]["detalhe"][0]["forca"] == "alta"
    # RAG usado → procedência registrada para o advogado do HITL.
    assert p["fontes"] == ["leitura_documento", "rag_interno"]


def test_brecha_sem_indicio_nao_vira_achado():
    """Prescrição/decadência null NÃO entram: dict com tudo vazio faria a tela
    anunciar brecha onde a IA admitiu lacuna."""
    p = _payload_leitura_documento(_PARECER, "doc-1")
    assert p["brechas"] == {"nulidades": ["Cláusula de tolerância abusiva"]}
    assert "prescricao" not in p["brechas"]
    assert "observacao" not in p["brechas"]


async def test_grava_snapshot_com_origem_documento_e_sem_aprovacao_automatica():
    chamadas: list[dict] = []

    async def _fake_gravar(db, **kwargs):
        chamadas.append(kwargs)

    import app.services.case_intelligence_service as cis
    original = cis.gravar_snapshot_seguro
    cis.gravar_snapshot_seguro = _fake_gravar
    try:
        await _gravar_snapshot_documento(
            None, case_id="caso-1", doc_id="doc-1",
            resultado=_PARECER, ai_log_id="log-1",
        )
    finally:
        cis.gravar_snapshot_seguro = original

    assert len(chamadas) == 1
    kw = chamadas[0]
    assert kw["case_id"] == "caso-1"
    assert kw["origem"] == "documento"
    # HITL: origem automática nunca nasce aprovada nem com autor humano.
    assert kw["criado_por"] is None
    # Rastreabilidade IA → o snapshot aponta para o AILog que o gerou.
    assert kw["ai_log_ids"] == ["log-1"]
    assert kw["payload"]["provas"][0]["titulo"] == "Contrato"


@pytest.mark.parametrize("resultado", [
    {"erro": "Falha ao parsear resposta da IA"},
    {},                       # IA não produziu nada de jurídico
    "resposta em texto",      # tipo inesperado
    None,
])
async def test_parecer_vazio_ou_com_erro_nao_gera_snapshot(resultado):
    """Não polui o histórico versionado do caso com snapshot sem parecer."""
    chamado = []

    async def _fake_gravar(db, **kwargs):
        chamado.append(kwargs)

    import app.services.case_intelligence_service as cis
    original = cis.gravar_snapshot_seguro
    cis.gravar_snapshot_seguro = _fake_gravar
    try:
        await _gravar_snapshot_documento(
            None, case_id="caso-1", doc_id="doc-1",
            resultado=resultado, ai_log_id="log-1",
        )
    finally:
        cis.gravar_snapshot_seguro = original
    assert chamado == []


async def test_falha_ao_gravar_snapshot_nao_propaga():
    """Roda em BackgroundTask depois do 200 do upload: quebrar aqui não pode
    afetar o advogado que já recebeu a resposta."""
    async def _explode(db, **kwargs):
        raise RuntimeError("banco fora do ar")

    import app.services.case_intelligence_service as cis
    original = cis.gravar_snapshot_seguro
    cis.gravar_snapshot_seguro = _explode
    try:
        await _gravar_snapshot_documento(
            None, case_id="caso-1", doc_id="doc-1",
            resultado=_PARECER, ai_log_id="log-1",
        )
    finally:
        cis.gravar_snapshot_seguro = original


def test_origem_documento_e_valida_no_service():
    from app.models.case_intelligence import ORIGENS_SNAPSHOT
    assert "documento" in ORIGENS_SNAPSHOT


# ── 3. o prompt pede a leitura do advogado ──────────────────────────────────

def test_prompt_pede_provas_necessarias_e_brechas():
    from app.services.analise_estrategica import PROMPT_ANALISE

    prompt = PROMPT_ANALISE.format(contexto="CASO FICTÍCIO PARA TESTE")
    for chave in ("provas_necessarias", "fato_probando", "brechas_preliminares",
                  "prescricao", "decadencia", "incompetencia", "ilegitimidade",
                  "nulidades", "pontos_fortes", "pontos_fracos"):
        assert chave in prompt, f"prompt perdeu {chave}"

    # O molde continua sendo JSON válido depois do .format() — o parser da
    # resposta depende disso, e um {} solto no texto quebraria o template.
    inicio = prompt.index('{\n  "partes"')
    json.loads(prompt[inicio: prompt.rindex("}") + 1])


def test_prompt_mantem_regras_anti_alucinacao():
    """A leitura mais rica não pode afrouxar o gate: brecha é hipótese a
    verificar, jurisprudência só da base interna."""
    from app.services.analise_estrategica import PROMPT_ANALISE

    prompt = PROMPT_ANALISE.format(contexto="x")
    assert "NUNCA invente jurisprudência" in prompt
    assert "HIPÓTESE A VERIFICAR" in prompt
    assert "BASE DE CONHECIMENTO INTERNA" in prompt
