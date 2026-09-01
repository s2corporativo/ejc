from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.case import Case, CaseMovimento
from app.services.datajud_cognitive_feed import (
    AVISO_JURIDICO,
    _conteudo_movimento,
    _conteudo_timeline,
    classificar_movimento,
    hash_movimento,
    limpar_descricao,
)


@pytest.fixture
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


def movimento(descricao="Sentença proferida [dj:0123456789abcdef]") -> CaseMovimento:
    return CaseMovimento(
        id="mov-feed-1",
        case_id="caso-feed-1",
        tipo="andamento_oficial",
        descricao=descricao,
        data_evento=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
        created_by=None,
    )


def test_marcador_e_limpeza():
    descricao = "Juntada de petição [dj:0123456789abcdef]"
    assert hash_movimento(descricao) == "0123456789abcdef"
    assert limpar_descricao(descricao) == "Juntada de petição"
    assert hash_movimento("nota manual") is None


def test_classificacao_conservadora():
    assert classificar_movimento("Sentença proferida")["tipo_evento"] == "sentenca"
    intimacao = classificar_movimento("Intimação para manifestação")
    assert intimacao["tipo_evento"] == "possivel_comunicacao"
    assert "não calcular prazo" in intimacao["providencia_sugerida"].lower()


def test_documento_tem_escopo_e_limite_juridico(caso):
    texto, extra = _conteudo_movimento(caso, movimento())
    assert AVISO_JURIDICO in texto
    assert extra["client_id"] == "cliente-feed-1"
    assert extra["case_id"] == "caso-feed-1"
    assert extra["deadline_source"] is False
    assert extra["requires_human_review"] is True
    assert extra["movement_hash"] == "0123456789abcdef"


def test_timeline_cronologica(caso):
    antigo = movimento("Distribuição [dj:1111111111111111]")
    antigo.id = "a"
    antigo.data_evento = datetime(2025, 1, 1, tzinfo=timezone.utc)
    recente = movimento("Sentença proferida [dj:2222222222222222]")
    recente.id = "b"
    recente.data_evento = datetime(2026, 7, 18, tzinfo=timezone.utc)
    texto, extra = _conteudo_timeline(caso, [antigo, recente])
    assert texto.index("Distribuição") < texto.index("Sentença proferida")
    assert extra["movement_count"] == 2
    assert extra["max_operational_severity"] == "alta"


@pytest.mark.asyncio
async def test_consulta_exata_descarta_hit_errado(monkeypatch):
    from app.core.config import get_settings
    from app.services import datajud_service
    from app.services.datajud_cognitive_patch import _consultar_movimentos_exatos

    settings = get_settings()
    monkeypatch.setattr(settings, "DATAJUD_ENABLED", True)
    monkeypatch.setattr(settings, "DATAJUD_API_KEY", "teste")
    numero = "00000010220208130000"

    async def fake_search(alias, payload, headers):
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "numeroProcesso": "99999999999999999999",
                            "movimentos": [],
                        }
                    },
                    {
                        "_source": {
                            "numeroProcesso": numero,
                            "movimentos": [
                                {
                                    "codigo": 26,
                                    "nome": "Distribuição",
                                    "dataHora": "2020-03-01",
                                }
                            ],
                        }
                    },
                ]
            }
        }

    monkeypatch.setattr(datajud_service, "_datajud_search", fake_search)
    resultado = await _consultar_movimentos_exatos(
        "0000001-02.2020.8.13.0000"
    )
    assert resultado == [
        {"data": "2020-03-01", "codigo": 26, "descricao": "Distribuição"}
    ]


def test_startup_registra_rotas_e_bloqueia_prazo_automatico():
    from app.main import app
    from app.services import datajud_service

    paths = {getattr(route, "path", "") for route in app.routes}
    assert any(
        path.endswith("/casos/{case_id}/andamentos/inteligencia")
        for path in paths
    )
    # Saneamento 30/08/2026: o endereço antigo /casos/{case_id}/andamentos/
    # alimentar-ia (redirect 308) foi removido — o canônico é o registrado
    # explicitamente em app/main.py sob /datajud/intelligence.
    assert any(
        path.endswith(
            "/datajud/intelligence/{case_id}/andamentos/alimentar-ia"
        )
        for path in paths
    )
    assert datajud_service._detectar_prazos_criticos(
        "Intimação para manifestação",
        datetime(2026, 7, 18, tzinfo=timezone.utc),
    ) == []


@pytest.mark.asyncio
async def test_startup_bloqueia_tambem_criador_e_sync_de_prazos():
    """Anti-vácuo #1336: não basta o detector retornar []; os dois caminhos de
    escrita precisam estar explicitamente bloqueados no runtime.
    """
    from app.main import app  # noqa: F401 — força instalação dos subscribers
    from app.services import datajud_service

    # O criador legado vira no-op, mesmo se for chamado diretamente por código
    # que contorne o detector.
    assert await datajud_service._criar_deadline_automatico(
        None,
        None,
        {"titulo": "x", "data_prazo": "2026-09-10"},
        "movimento",
    ) is None

    resultado = await datajud_service.sincronizar_prazos_datajud(
        "caso-1",
        "0000001-02.2020.8.13.0000",
        None,
    )
    assert resultado["criados"] == 0
    assert resultado["bloqueado"] is True
    assert resultado["motivo"] == "revisao_humana_obrigatoria_ate_motor_auditavel"
