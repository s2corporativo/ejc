"""Contratos da Wave 5 para binding trabalhista e router regulatório."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.user import UserRole
from app.routers import regulatorio, trabalhista_liquidacao
from app.services import visual_law_files as vlf


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.params = None

    async def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return _Rows(self.rows)


def _user(user_id: str, role: UserRole = UserRole.advogado):
    return SimpleNamespace(id=user_id, role=role, full_name="Advogado Teste")


@pytest.mark.asyncio
async def test_sec03_download_exige_binding_do_criador(tmp_path, monkeypatch):
    arquivo_id = str(uuid4())
    pdf = Path(tmp_path) / f"liquidacao_{arquivo_id}.pdf"
    pdf.write_bytes(b"pdf")
    vlf.registrar_origem(str(tmp_path), arquivo_id, criado_por="adv-1")
    monkeypatch.setattr(trabalhista_liquidacao, "_pdf_dir", lambda: str(tmp_path))

    resposta = await trabalhista_liquidacao.download_planilha(
        arquivo_id, _user("adv-1")
    )
    assert resposta.path == str(pdf)
    assert resposta.filename == "planilha_liquidacao_sentenca.pdf"

    with pytest.raises(HTTPException) as exc:
        await trabalhista_liquidacao.download_planilha(arquivo_id, _user("adv-2"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_sec03_arquivo_sem_sidecar_falha_fechado(tmp_path, monkeypatch):
    arquivo_id = str(uuid4())
    (Path(tmp_path) / f"liquidacao_{arquivo_id}.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(trabalhista_liquidacao, "_pdf_dir", lambda: str(tmp_path))

    with pytest.raises(HTTPException) as exc:
        await trabalhista_liquidacao.download_planilha(arquivo_id, _user("adv-1"))
    assert exc.value.status_code == 403
    assert "vínculo" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_be04_digest_regulatorio_agrega_alertas_e_limita_itens():
    rows = [
        {
            "fonte": "DOU",
            "keyword_match": "licitação",
            "titulo": "Alerta 1",
            "resumo": "resumo curto",
            "link": "https://example.test/1",
            "data_publicacao": None,
            "lido": False,
            "created_at": None,
        },
        {
            "fonte": "DOU",
            "keyword_match": "licitação",
            "titulo": "Alerta 2",
            "resumo": "x" * 400,
            "link": "https://example.test/2",
            "data_publicacao": None,
            "lido": True,
            "created_at": None,
        },
    ]
    db = _DB(rows)

    resposta = await regulatorio.digest_semanal(dias=7, db=db)

    assert resposta["periodo_dias"] == 7
    assert resposta["total_alertas"] == 2
    assert resposta["nao_lidos"] == 1
    assert resposta["por_fonte"] == {"DOU": 2}
    assert resposta["top_keywords"] == [{"keyword": "licitação", "qtd": 2}]
    assert len(resposta["itens_recentes"]) == 2
    assert resposta["itens_recentes"][1]["resumo"].endswith("...")
    assert "created_at" in str(db.statement)


def test_be04_router_mantem_prefixo_e_dependencia_de_usuario():
    assert regulatorio.router.prefix == "/regulatorio"
    rota = next(route for route in regulatorio.router.routes if route.path.endswith("/digest-semanal"))
    assert "GET" in rota.methods
    assert regulatorio.router.dependencies
