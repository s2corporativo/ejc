"""Feed DataJud → inteligência nativa do EJC (sem rede e sem banco real)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.case import Case, CaseMovimento
from app.services.datajud_cognitive_feed import (
    AVISO_JURIDICO,
    CATEGORIA_RAG,
    _conteudo_movimento,
    _conteudo_timeline,
    classificar_movimento,
    hash_movimento,
    limpar_descricao,
)
from app.services import datajud_cognitive_patch


@pytest.fixture()
def caso() -> Case:
    return Case(
        id="caso-feed-1",
        client_id="cliente-feed-1",
        titulo="Ação de teste",
        numero_interno="EJC-2026-001",
        numero_processo="0000001-02.2020.8.13.0000",
        tribunal="TJMG",
        area="civil",
    )


def movimento(descricao: str = "Sentença proferida [dj:0123456789abcdef]") -> CaseMovimento:
    return CaseMovimento(
        id="mov-feed-1",
        case_id="caso-feed-1",
        tipo="andamento_oficial",
        descricao=descricao,
        data_evento=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        created_by=None,
    )


def test_marcador_datajud_e_texto_original():
    descricao = "Juntada de petição [dj:0123456789abcdef]"
    assert hash_movimento(descricao) == "0123456789abcdef"
    assert limpar_descricao(descricao) == "Juntada de petição"
    assert hash_movimento("nota manual") is None


def test_classificacao_e_conservadora():
    sentenca = classificar_movimento("Sentença proferida")
    assert sentenca["tipo_evento"] == "sentenca"
    assert sentenca["severidade"] == "alta"

    intimacao = classificar_movimento("Intimação para manifestação")
    assert intimacao["tipo_evento"] == "possivel_comunicacao"
    assert "não calcular prazo" in intimacao["providencia_sugerida"].lower()

    comum = classificar_movimento("Conclusos para análise")
    assert comum["tipo_evento"] == "movimentacao"
    assert comum["severidade"] == "informativa"


def test_documento_movimento_tem_escopo_proveniencia_e_limite_juridico(caso):
    texto, extra = _conteudo_movimento(caso, movimento())
    assert AVISO_JURIDICO in texto
    assert "Sentença proferida" in texto
    assert extra["client_id"] == "cliente-feed-1"
    assert extra["case_id"] == "caso-feed-1"
    assert extra["source_system"] == "datajud"
    assert extra["official_source"] is True
    assert extra["deadline_source"] is False
    assert extra["requires_human_review"] is True
    assert extra["document_type"] == "process_movement"
    assert extra["movement_hash"] == "0123456789abcdef"


def test_timeline_consolidada_e_cronologica(caso):
    antigo = movimento("Distribuição [dj:1111111111111111]")
    antigo.id = "mov-antigo"
    antigo.data_evento = datetime(2025, 1, 1, tzinfo=timezone.utc)
    recente = movimento("Sentença proferida [dj:2222222222222222]")
    recente.id = "mov-recente"
    recente.data_evento = datetime(2026, 7, 18, tzinfo=timezone.utc)

    texto, extra = _conteudo_timeline(caso, [antigo, recente])
    assert texto.index("Distribuição") < texto.index("Sentença proferida")
    assert extra["movement_count"] == 2
    assert extra["max_operational_severity"] == "alta"
    assert extra["deadline_source"] is False


@pytest.mark.asyncio
async def test_consulta_exata_descarta_hit_de_outro_processo(monkeypatch):
    from app.core.config import get_settings
    from app.services import datajud_service

    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "teste")
    numero = "00000010220208130000"

    async def fake_search(alias, payload, headers):
        return {
            "hits": {
                "hits": [
                    {"_source": {
                        "numeroProcesso": "99999999999999999999",
                        "movimentos": [{"nome": "Movimento errado", "dataHora": "2026-01-01"}],
                    }},
                    {"_source": {
                        "numeroProcesso": numero,
                        "movimentos": [{"codigo": 26, "nome": "Distribuição", "dataHora": "2020-03-01"}],
                    }},
                ]
            }
        }

    monkeypatch.setattr(datajud_service, "_datajud_search", fake_search)
    resultado = await datajud_cognitive_patch._consultar_movimentos_exatos(
        "0000001-02.2020.8.13.0000"
    )
    assert resultado == [{
        "data": "2020-03-01",
        "codigo": 26,
        "descricao": "Distribuição",
    }]


def test_integracao_esta_montada_no_app_e_restrita_por_cliente():
    from app.main import app
    from app.services import ai_service, datajud_service
    from app.routers import cases as cases_router

    paths = {getattr(route, "path", "") for route in app.routes}
    assert any(path.endswith("/casos/{case_id}/andamentos/inteligencia") for path in paths)
    assert any(path.endswith("/casos/{case_id}/andamentos/alimentar-ia") for path in paths)
    assert any(path.endswith("/casos/inteligencia/datajud/reconstruir-lote") for path in paths)
    assert CATEGORIA_RAG in ai_service._RESTRICTED_CATS
    assert cases_router._dj_sync is datajud_service.sincronizar_caso


def test_datajud_nao_cria_prazo_automatico_apos_startup():
    # Importar app instala o patch por event_subscribers.
    from app.main import app  # noqa: F401
    from app.services import datajud_service

    encontrados = datajud_service._detectar_prazos_criticos(
        "Intimação para manifestação",
        datetime(2026, 7, 18, tzinfo=timezone.utc),
    )
    assert encontrados == []
