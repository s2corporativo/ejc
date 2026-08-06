"""Regressão Issue #695 — mass assignment no PATCH do Raio-X.

`PATCH /raio-x/{analise_id}` aceitava um dict LIVRE em
`revisao_humana.identificacao` e chamava `setattr(analise, key, value)` em
qualquer atributo existente no model `RaioXAnalise`, sem allowlist — só
filtrava `value not in (None, "")`. Isso permitia ao cliente escrever
`status`, `deleted_at`, `created_by`, `id` e qualquer outra coluna, incl.
travar permanentemente o registro como "convertido_em_caso" sem nunca ter
sido convertido de verdade (`convertido_case_id` continuava NULL).

A correção restringe as chaves aceitas em `identificacao` ao conjunto
explícito que `_aplicar_identificacao` (raio_x.py:78-85) já trata:
numero_processo, area, subarea, rito, fase, tribunal, orgao, unidade,
posicao_cliente. Qualquer chave fora disso -> 422 nomeando o que foi
rejeitado.

Estilo: sem DB real — `atualizar()` é chamado diretamente com uma sessão
fake e `_obter()` monkeypatchado para devolver um `RaioXAnalise` transiente
(nunca persistido), como em test_raio_x_advogado.py.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.raio_x import RaioXAnalise
from app.routers import raio_x as router_mod
from app.schemas.raio_x import RaioXUpdate


class _FakeDB:
    """Sessão fake: `criar_audit_log` só faz `db.add(...)`; o router só
    chama `commit()`/`refresh()` depois. Nenhum acesso real a Postgres."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass


def _user(user_id: str = "user-1", role: str = "advogado"):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(value=role))


def _analise(**overrides) -> RaioXAnalise:
    defaults = dict(
        id="analise-1",
        titulo="Análise fictícia",
        status="em_analise",
        numero_processo=None,
        area=None,
        subarea=None,
        rito=None,
        fase=None,
        tribunal=None,
        orgao=None,
        unidade=None,
        posicao_cliente=None,
        relatorio={},
        revisao_humana={},
        dados_extraidos={},
        alertas_conflito=[],
        custo_ia={},
        created_by="user-1",
        prazo_urgente=False,
        deleted_at=None,
        convertido_case_id=None,
    )
    defaults.update(overrides)
    return RaioXAnalise(**defaults)


@pytest.fixture
def db():
    return _FakeDB()


async def _patch(monkeypatch, db, analise, review_identificacao: dict, user=None):
    """Chama atualizar() com revisao_humana.identificacao=review_identificacao."""

    async def fake_obter(_db, _analise_id, _user):
        return analise

    monkeypatch.setattr(router_mod, "_obter", fake_obter)
    payload = RaioXUpdate(revisao_humana={"identificacao": review_identificacao})
    return await router_mod.atualizar(
        analise_id=analise.id, payload=payload, db=db, user=user or _user()
    )


class TestMassAssignmentBloqueado:
    """Critérios de aceite 1-2 da Issue #695 — todos por negação."""

    async def test_status_via_identificacao_e_rejeitado(self, monkeypatch, db):
        analise = _analise(status="em_analise")
        with pytest.raises(HTTPException) as exc:
            await _patch(
                monkeypatch, db, analise, {"status": "convertido_em_caso"}
            )
        assert exc.value.status_code == 422
        assert exc.value.detail == (
            "Campos não permitidos em revisao_humana.identificacao: status"
        )
        # O ataque não deixou nenhum rastro no objeto: nem 409 de conversão
        # fantasma em um PATCH futuro.
        assert analise.status == "em_analise"

    async def test_deleted_at_via_identificacao_e_rejeitado(self, monkeypatch, db):
        analise = _analise()
        with pytest.raises(HTTPException) as exc:
            await _patch(
                monkeypatch, db, analise, {"deleted_at": "2026-01-01T00:00:00Z"}
            )
        assert exc.value.status_code == 422
        assert exc.value.detail == (
            "Campos não permitidos em revisao_humana.identificacao: deleted_at"
        )
        assert analise.deleted_at is None

    async def test_created_by_via_identificacao_e_rejeitado(self, monkeypatch, db):
        analise = _analise(created_by="dono-legitimo")
        with pytest.raises(HTTPException) as exc:
            await _patch(monkeypatch, db, analise, {"created_by": ""})
        assert exc.value.status_code == 422
        assert exc.value.detail == (
            "Campos não permitidos em revisao_humana.identificacao: created_by"
        )
        # Autor legítimo preservado — não perde ownership (raio_x.py:73).
        assert analise.created_by == "dono-legitimo"

    async def test_id_via_identificacao_e_rejeitado(self, monkeypatch, db):
        analise = _analise(id="analise-original")
        with pytest.raises(HTTPException) as exc:
            await _patch(monkeypatch, db, analise, {"id": "outro-id-qualquer"})
        assert exc.value.status_code == 422
        assert exc.value.detail == (
            "Campos não permitidos em revisao_humana.identificacao: id"
        )
        assert analise.id == "analise-original"

    async def test_mistura_de_campo_valido_e_invalido_e_toda_rejeitada(
        self, monkeypatch, db
    ):
        """Fail-closed: um único campo fora da allowlist derruba o PATCH
        inteiro (nada é aplicado parcialmente em silêncio)."""
        analise = _analise(area=None)
        with pytest.raises(HTTPException) as exc:
            await _patch(
                monkeypatch,
                db,
                analise,
                {"area": "civil", "status": "convertido_em_caso"},
            )
        assert exc.value.status_code == 422
        # "area" é campo válido; só "status" cai fora da allowlist — mas o
        # PATCH inteiro é rejeitado, nada é aplicado parcialmente.
        assert exc.value.detail == (
            "Campos não permitidos em revisao_humana.identificacao: status"
        )
        assert analise.area is None
        assert analise.status == "em_analise"

    async def test_titulo_gigante_via_identificacao_e_rejeitado(self, monkeypatch, db):
        """`titulo` não é campo de identificação processual — cai fora da
        allowlist antes mesmo de chegar ao validador de max_length."""
        analise = _analise(titulo="Título original")
        with pytest.raises(HTTPException) as exc:
            await _patch(monkeypatch, db, analise, {"titulo": "x" * 8000})
        assert exc.value.status_code == 422
        assert exc.value.detail == (
            "Campos não permitidos em revisao_humana.identificacao: titulo"
        )
        assert analise.titulo == "Título original"


class TestRevisaoHumanaLegitima:
    """Critério de aceite 3 — sem regressão no fluxo real."""

    async def test_campos_de_identificacao_processual_sao_aplicados(
        self, monkeypatch, db
    ):
        analise = _analise()
        resultado = await _patch(
            monkeypatch,
            db,
            analise,
            {
                "numero_processo": "0001234-56.2024.8.13.0001",
                "area": "civil",
                "subarea": "contratos",
                "rito": "comum",
                "fase": "conhecimento",
                "tribunal": "TJMG",
                "orgao": "1ª Vara Cível",
                "unidade": "Comarca de BH",
                "posicao_cliente": "autor",
            },
        )
        assert analise.numero_processo == "0001234-56.2024.8.13.0001"
        assert analise.area == "civil"
        assert analise.subarea == "contratos"
        assert analise.rito == "comum"
        assert analise.fase == "conhecimento"
        assert analise.tribunal == "TJMG"
        assert analise.orgao == "1ª Vara Cível"
        assert analise.unidade == "Comarca de BH"
        assert analise.posicao_cliente == "autor"
        assert analise.relatorio["revisao_humana_aplicada"] is True
        assert analise.relatorio["identificacao"]["numero_processo"] == (
            "0001234-56.2024.8.13.0001"
        )
        assert resultado["area"] == "civil"

    async def test_max_length_de_rai_ox_update_continua_valendo(self, monkeypatch, db):
        """Valores dentro da allowlist ainda passam pelos mesmos limites de
        RaioXUpdate (ex.: tribunal max_length=50)."""
        analise = _analise()
        with pytest.raises(HTTPException) as exc:
            await _patch(monkeypatch, db, analise, {"tribunal": "x" * 51})
        assert exc.value.status_code == 422
        assert analise.tribunal is None

    async def test_valores_vazios_sao_ignorados_como_antes(self, monkeypatch, db):
        analise = _analise(area="trabalhista")
        await _patch(monkeypatch, db, analise, {"area": "", "subarea": None})
        # Comportamento preservado: string vazia/None não sobrescreve.
        assert analise.area == "trabalhista"
        assert analise.subarea is None


class TestCongelamentoPorConversao:
    """Critério de aceite 4 — o 409 de conversão REAL continua funcionando."""

    async def test_analise_ja_convertida_bloqueia_qualquer_patch(
        self, monkeypatch, db
    ):
        analise = _analise(status="convertido_em_caso", convertido_case_id="caso-1")

        async def fake_obter(_db, _analise_id, _user):
            return analise

        monkeypatch.setattr(router_mod, "_obter", fake_obter)
        payload = RaioXUpdate(titulo="Tentativa de editar após conversão")
        with pytest.raises(HTTPException) as exc:
            await router_mod.atualizar(
                analise_id=analise.id, payload=payload, db=db, user=_user()
            )
        assert exc.value.status_code == 409
        assert "congelado" in exc.value.detail
