from types import SimpleNamespace

from app.services.sala_analise_service import (
    _extrair_json,
    _normalizar_estado,
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
    estado = _normalizar_estado({"riscos": [{"texto": "risco novo"}], "campo_injetado": "x"}, anterior)

    assert estado["versao"] == 3
    assert estado["fatos"] == anterior["fatos"]
    assert estado["riscos"] == [{"texto": "risco novo"}]
    assert "campo_injetado" not in estado
    assert estado["revisao_humana_obrigatoria"] is True
