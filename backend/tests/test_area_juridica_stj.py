"""Onda 3 — área do direito nos acórdãos do STJ.

A auditoria registrou "lacuna de cobertura" em áreas onde o acervo do STJ na
verdade tinha conteúdo: o que faltava era o RÓTULO. `detectar_area`
(knowledge_governance) lê `extra["area_juridica"]` e, na ausência, cai num
match textual sobre título/categoria que termina em "Geral" — e nenhum dos
dois caminhos de ingestão do STJ gravava a chave, ao contrário do TJMG.

Estes testes travam a correção nos dois caminhos (job agendado e importação
sob demanda), sem rede nem banco: o upsert é substituído por um espião.
"""
from __future__ import annotations

from app.services.ingestors import stj as ingestor_stj
from app.services.juris_import import stj as conector_stj

# Ementa fictícia, com o vocabulário que o inferidor reconhece.
_EMENTA_CONSUMIDOR = (
    "RECURSO ESPECIAL. DIREITO DO CONSUMIDOR. INSCRICAO INDEVIDA EM CADASTRO "
    "DE INADIMPLENTES. DANO MORAL IN RE IPSA. RELACAO DE CONSUMO CONFIGURADA."
)


def test_inferidor_de_area_e_o_mesmo_do_tjmg():
    """Um vocabulário só: o STJ reusa a função do TJMG, não uma cópia."""
    from app.services.jurisprudencia_externa import _inferir_area

    assert ingestor_stj._inferir_area is _inferir_area
    assert conector_stj._inferir_area is _inferir_area
    assert _inferir_area(_EMENTA_CONSUMIDOR)  # reconhece a área, não devolve ""


async def test_ingestor_agendado_grava_area_no_extra(monkeypatch):
    capturado: dict = {}

    async def fake_upsert(db, **kwargs):
        capturado.update(kwargs)
        return "novo"

    async def fake_ultimo_json(orgao):
        return {"url": "https://exemplo.invalido/espelho.json"} if orgao == ingestor_stj.ORGAOS[0] else None

    class _Resp:
        def json(self):
            return [{
                "numeroRegistro": "2024/0000001-0",
                "numeroProcesso": "1234567",
                "siglaClasse": "REsp",
                "ementa": _EMENTA_CONSUMIDOR,
                "nomeOrgaoJulgador": "Terceira Turma",
                "ministroRelator": "Fulano de Tal",
            }]

    class _FakeDB:
        async def commit(self):
            pass

    monkeypatch.setattr(ingestor_stj, "_ultimo_json", fake_ultimo_json)
    monkeypatch.setattr(ingestor_stj, "fetch", lambda *a, **k: _resp())
    monkeypatch.setattr(ingestor_stj, "upsert_documento", fake_upsert)

    async def _resp():
        return _Resp()

    await ingestor_stj.ingerir(_FakeDB())

    assert capturado["extra"]["area_juridica"], (
        "acórdão do STJ ingerido sem área — volta a cair em 'Geral' na matriz"
    )
    # Sem regressão no resto do contrato de gravação.
    assert capturado["tribunal"] == "STJ"
    assert capturado["chave_origem"].startswith("stj:")


def test_conector_sob_demanda_normaliza_com_area():
    """A importação manual classifica igual ao job agendado — os dois caminhos
    compartilham keyspace de dedup, então não podem divergir no rótulo."""
    julgado = conector_stj.normalizar_registro(
        {
            "numeroRegistro": "2024/0000002-0",
            "numeroProcesso": "7654321",
            "siglaClasse": "AREsp",
            "ementa": _EMENTA_CONSUMIDOR,
            "dataDecisao": "2024-05-10",
        },
        "https://exemplo.invalido/acordao",
    )
    assert julgado is not None
    assert julgado.area_juridica, "julgado normalizado sem área"


def test_formato_normalizado_carrega_area_para_todos_os_conectores():
    """O campo vive no formato comum: TJMG e LexML herdam sem código novo."""
    from app.services.juris_import.base import JulgadoNormalizado

    assert "area_juridica" in JulgadoNormalizado.model_fields
    j = JulgadoNormalizado(
        tribunal="STJ", numero="1", ementa="x", url_fonte="https://exemplo.invalido",
    )
    assert j.area_juridica is None  # opcional: conector que não infere não quebra
