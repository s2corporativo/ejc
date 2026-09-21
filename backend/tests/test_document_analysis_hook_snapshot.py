"""Regressões da leitura estratégica de documento → inteligência do caso.

Dados integralmente fictícios. Estes testes não chamam LLM, rede nem banco.
"""
from __future__ import annotations

import pytest

from app.models.case_intelligence import ORIGENS_SNAPSHOT
from app.services.document_analysis_hook import (
    _gravar_snapshot_documento,
    payload_snapshot_documento,
)


_PARECER = {
    "sumario_fatos": "Fornecedor atrasou a entrega contratual em 45 dias.",
    "pontos_fortes": ["Contrato assinado e notas fiscais disponíveis"],
    "pontos_fracos": ["Notificação extrajudicial ainda não localizada"],
    "estrategia": {
        "recomendacao": "moderado",
        "justificativa_recomendacao": "Priorizar composição sem renunciar à prova.",
    },
    "teses_campeas": [
        {"titulo": "Inadimplemento contratual", "forca": "alta"},
        {"titulo": "Perdas e danos", "forca": "media"},
    ],
    "riscos": [
        {
            "descricao": "Discussão sobre mora",
            "probabilidade": "media",
            "impacto": "medio",
        }
    ],
    "jurimetria": {"chance_sucesso_percent": 65},
    "proximos_passos": [
        {"acao": "Localizar notificação", "prazo": "imediato", "prioridade": "alta"}
    ],
    "alertas": ["Validar termo inicial da mora"],
    "_fontes_rag": [{"fonte": "tese interna fictícia"}],
}


def test_payload_snapshot_preserva_raciocinio_juridico_sem_inventar_campos():
    payload = payload_snapshot_documento(_PARECER, "doc-ficticio-1")

    assert payload["documento_id"] == "doc-ficticio-1"
    assert payload["fatos"] == _PARECER["sumario_fatos"]
    assert payload["pontos_fortes"] == _PARECER["pontos_fortes"]
    assert payload["riscos"]["pontos_fracos"] == _PARECER["pontos_fracos"]
    assert "chance_exito" not in payload["riscos"]
    assert payload["teses"]["principal"] == "Inadimplemento contratual"
    assert payload["teses"]["secundarias"] == ["Perdas e danos"]
    assert payload["teses"]["detalhe"][0]["forca"] == "alta"
    assert payload["fontes"] == ["leitura_documento", "rag_interno"]
    assert "provas" not in payload  # prompt atual ainda não produz este contrato
    assert "brechas" not in payload


def test_payload_vazio_nao_inventa_parecer():
    assert payload_snapshot_documento({}, "doc-ficticio-2") == {
        "documento_id": "doc-ficticio-2",
        "fontes": ["leitura_documento"],
    }


@pytest.mark.asyncio
async def test_snapshot_automatico_nasce_documento_nao_aprovado_e_ligado_ao_ai_log(
    monkeypatch,
):
    chamadas: list[dict] = []

    async def fake_gravar(db, **kwargs):
        chamadas.append(kwargs)
        return None

    import app.services.case_intelligence_service as cis

    monkeypatch.setattr(cis, "gravar_snapshot_seguro", fake_gravar)
    monkeypatch.setattr(cis, "compactar_payload", lambda payload: payload)

    await _gravar_snapshot_documento(
        object(),
        case_id="caso-ficticio-1",
        doc_id="doc-ficticio-1",
        resultado=_PARECER,
        ai_log_id="log-ficticio-1",
    )

    assert len(chamadas) == 1
    chamada = chamadas[0]
    assert chamada["case_id"] == "caso-ficticio-1"
    assert chamada["origem"] == "documento"
    assert chamada["criado_por"] is None
    assert chamada["ai_log_ids"] == ["log-ficticio-1"]
    # congelado/aprovado não são parâmetros de criação automática: o service
    # canônico garante congelado=False e aprovado_por/aprovado_em=None.
    assert "congelado" not in chamada
    assert "aprovado_por" not in chamada


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resultado",
    [
        None,
        "texto inesperado",
        {},
        {"erro": "Falha ao parsear resposta da IA"},
        {"_fontes_rag": [{"fonte": "sem parecer"}]},
    ],
)
async def test_resultado_sem_conteudo_juridico_nao_gera_snapshot(monkeypatch, resultado):
    chamadas: list[dict] = []

    async def fake_gravar(db, **kwargs):
        chamadas.append(kwargs)
        return None

    import app.services.case_intelligence_service as cis

    monkeypatch.setattr(cis, "gravar_snapshot_seguro", fake_gravar)
    await _gravar_snapshot_documento(
        object(),
        case_id="caso-ficticio-1",
        doc_id="doc-ficticio-1",
        resultado=resultado,
        ai_log_id="log-ficticio-1",
    )
    assert chamadas == []


def test_origem_documento_e_aditiva_sem_migration():
    assert "documento" in ORIGENS_SNAPSHOT
