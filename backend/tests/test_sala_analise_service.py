from types import SimpleNamespace

from app.services.sala_analise_service import (
    _extrair_json,
    _normalizar_estado,
    _sincronizar_relatorio_para_conversao,
    estado_inicial,
)


def _analise(relatorio):
    return SimpleNamespace(
        relatorio=relatorio,
        potencial_cliente="Cliente Teste",
    )


def test_estado_inicial_nao_converte_indicio_em_fato_comprovado():
    estado = estado_inicial(
        _analise(
            {
                "sintese_executiva": "Acidente narrado pelo interessado.",
                "fatos_provas": [
                    {"fato": "A placa indicava 5,5 m", "fontes": ["foto-1"]},
                    "O piso teria sido rebaixado depois",
                ],
                "provas": ["Fotografia do veículo"],
                "contradicoes": ["GO-020 x DF-345"],
                "documentos_pendentes": ["Laudo de altura"],
            }
        )
    )

    assert estado["fatos"][0]["classificacao"] == "alegado"
    assert estado["fatos"][0]["confianca"] == "media"
    assert estado["fatos"][1]["classificacao"] == "alegado"
    assert estado["provas"][0]["forca"] == "pendente"
    assert estado["contradicoes"][0]["impacto"] == "moderado"


def test_extrair_json_aceita_cerca_markdown_sem_expor_texto_livre():
    data = _extrair_json('```json\n{"resposta_markdown":"ok","estado":{"fatos":[]}}\n```')
    assert data == {"resposta_markdown": "ok", "estado": {"fatos": []}}


def test_normalizar_estado_preserva_chaves_anteriores_e_limita_campos():
    anterior = {
        "versao": 2,
        "sintese_atual": "síntese anterior",
        "fatos": [{"texto": "fato"}],
        "provas": [],
        "contradicoes": [],
        "questoes_juridicas": [],
        "riscos": [],
        "documentos_pendentes": [],
        "proximos_passos": [],
        "tese_favoravel": [],
        "tese_adversa": [],
        "visao_julgador": "pendente",
    }
    estado = _normalizar_estado(
        {"riscos": [{"texto": "risco novo"}], "campo_injetado": "x"},
        anterior,
    )

    assert estado["versao"] == 3
    assert estado["fatos"] == anterior["fatos"]
    assert estado["riscos"] == [{"texto": "risco novo"}]
    assert "campo_injetado" not in estado
    assert estado["revisao_humana_obrigatoria"] is True


def test_normalizar_estado_nao_apaga_fatos_por_array_vazio_da_ia():
    anterior = {
        "versao": 1,
        "sintese_atual": "síntese",
        "fatos": [{"texto": "fato confirmado", "classificacao": "comprovado"}],
        "provas": [],
        "contradicoes": [],
        "questoes_juridicas": [],
        "riscos": [],
        "documentos_pendentes": [],
        "proximos_passos": [],
        "tese_favoravel": [],
        "tese_adversa": [],
        "visao_julgador": "pendente",
    }

    estado = _normalizar_estado({"fatos": []}, anterior)

    assert estado["fatos"] == anterior["fatos"]


def _estado_para_conversao(riscos):
    return {
        "versao": 4,
        "atualizado_em": "2026-07-24T12:00:00+00:00",
        "sintese_atual": "síntese consolidada pelo advogado",
        "fatos": [{"texto": "local DF-345", "classificacao": "comprovado"}],
        "provas": [{"texto": "boletim", "forca": "media"}],
        "contradicoes": [{"texto": "GO-020 x DF-345", "impacto": "critico"}],
        "questoes_juridicas": [{"texto": "legitimidade", "status": "pendente"}],
        "riscos": riscos,
        "documentos_pendentes": [{"texto": "laudo", "criticidade": "alta"}],
        "proximos_passos": [{"texto": "solicitar certidão", "prioridade": "imediata"}],
        "tese_favoravel": ["erro de sinalização"],
        "tese_adversa": ["culpa concorrente"],
        "visao_julgador": "necessária instrução",
    }


def test_estado_conversacional_e_projetado_no_relatorio_legado_de_conversao():
    analise = _analise({"sintese_executiva": "versão documental original"})
    estado = _estado_para_conversao([
        {"texto": "réu incorreto", "nivel": "critico"},
        {"texto": "dano moral fraco", "nivel": "moderado"},
    ])

    _sincronizar_relatorio_para_conversao(analise, estado)

    assert analise.relatorio["sintese_executiva"] == "síntese consolidada pelo advogado"
    assert analise.relatorio["fatos_provas"] == estado["fatos"]
    assert analise.relatorio["proximos_passos"] == estado["proximos_passos"]
    assert analise.relatorio["risco_nivel"] == "critico"
    assert analise.relatorio["revisao_humana_obrigatoria"] is True


def test_risco_alto_da_sala_e_convertido_para_vocabulario_legado_elevado():
    analise = _analise({})
    estado = _estado_para_conversao([
        {"texto": "nexo ainda pendente", "nivel": "alto"},
    ])

    _sincronizar_relatorio_para_conversao(analise, estado)

    assert analise.relatorio["risco_nivel"] == "elevado"
