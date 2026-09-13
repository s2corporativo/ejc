"""Gate de acesso à peça de admissão dentro de `_enforce_client_legal_doc_scope`
(#1460): o mesmo LegalDoc não pode ser negado por
`/clients/{id}/pecas-geradas` (advogado+) e liberado por `/legal-docs/*` para
papéis com visão ampla de CRM (ex.: secretaria).

Corrigido embutindo a regra na função em vez de monkeypatch do Dependant
compilado (achado 2026-09-06: `fastapi.params.Depends` é dataclass frozen —
reatribuir `.dependency` quebra o boot; e a troca do atributo do módulo
invalidava silenciosamente `app.dependency_overrides` registrados por outros
testes que capturaram a referência original antes do monkeypatch instalar)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.legal_docs import _enforce_client_legal_doc_scope


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _DB:
    def __init__(self, row):
        self.row = row

    async def execute(self, _stmt):
        return _Result(self.row)


def _request(doc_id: str = "doc-admissao"):
    return SimpleNamespace(path_params={"doc_id": doc_id})


async def _visivel_true(*_a, **_k):
    return True


@pytest.mark.asyncio
async def test_secretaria_nao_le_documento_de_admissao(monkeypatch):
    import app.routers.legal_docs as mod

    monkeypatch.setattr(mod, "cliente_id_visivel", _visivel_true)
    db = _DB(("client-1", "procuracao"))
    cu = SimpleNamespace(id="sec-1", role="secretaria")

    with pytest.raises(HTTPException) as exc:
        await _enforce_client_legal_doc_scope(_request(), db=db, cu=cu)

    assert exc.value.status_code == 403
    assert "equipe jurídica" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_advogado_le_documento_de_admissao(monkeypatch):
    import app.routers.legal_docs as mod

    monkeypatch.setattr(mod, "cliente_id_visivel", _visivel_true)
    db = _DB(("client-1", "contrato_honorarios"))
    cu = SimpleNamespace(id="adv-1", role="advogado")

    await _enforce_client_legal_doc_scope(_request(), db=db, cu=cu)  # não levanta


@pytest.mark.asyncio
async def test_secretaria_le_documento_sem_kind_de_admissao(monkeypatch):
    import app.routers.legal_docs as mod

    monkeypatch.setattr(mod, "cliente_id_visivel", _visivel_true)
    db = _DB(("client-1", None))
    cu = SimpleNamespace(id="sec-1", role="secretaria")

    await _enforce_client_legal_doc_scope(_request(), db=db, cu=cu)  # não levanta


@pytest.mark.asyncio
async def test_ownership_precede_o_gate_de_admissao(monkeypatch):
    """404 anti-enumeração continua vencendo antes do piso advogado+."""
    import app.routers.legal_docs as mod

    async def _nao_visivel(*_a, **_k):
        return False

    monkeypatch.setattr(mod, "cliente_id_visivel", _nao_visivel)
    db = _DB(("client-outro", "procuracao"))
    cu = SimpleNamespace(id="sec-1", role="secretaria")

    with pytest.raises(HTTPException) as exc:
        await _enforce_client_legal_doc_scope(_request(), db=db, cu=cu)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_sem_doc_id_no_path_nao_consulta_nada():
    db = _DB(None)
    cu = SimpleNamespace(id="sec-1", role="secretaria")
    await _enforce_client_legal_doc_scope(
        _request(doc_id=""), db=db, cu=cu
    )  # retorna cedo, não levanta
