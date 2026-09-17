"""Tools de LEITURA PROFUNDA DOS AUTOS do agente (2026-09-05).

Cobre o que não depende de banco: registro/visibilidade/sem-HITL, helpers puros
de busca (escape de LIKE, tokenização, recorte de trechos), e os handlers com
`db`/serviços falsos — RBAC re-checado em cada tool (fail-closed) e degradação
graciosa do DataJud em `consultar_movimentacao`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.ai.agent.tools import leitura
from app.services.ai.agent.tools.context import AgentContext
from app.services.ai.agent.tools.registry import REGISTRY

_NOVAS = {"listar_documentos", "ler_documento", "buscar_nos_autos",
          "verificar_citacoes", "consultar_movimentacao"}


def _ctx(db=None, role="advogado"):
    return AgentContext(db=db, user=SimpleNamespace(id="u1", role=role),
                        case_id="c1", client_id="cli1", role=role)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Devolve `rows` para qualquer select; guarda a query para inspeção."""
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    async def execute(self, q):
        self.queries.append(q)
        return _Result(self.rows)


# ── registro ──────────────────────────────────────────────────────────────────

def test_novas_tools_registradas_como_leitura_para_todos_os_papeis():
    for nome in _NOVAS:
        assert REGISTRY.get(nome) is not None, nome
        assert REGISTRY.requer_confirmacao(nome) is False, nome
    for papel in ("advogado", "auxiliar", "estagiario", "socio"):
        assert _NOVAS <= REGISTRY.nomes_visiveis(papel), papel


# ── helpers puros ─────────────────────────────────────────────────────────────

def test_like_escape_neutraliza_curingas():
    assert leitura._like_escape("100%_x\\") == "100\\%\\_x\\\\"


def test_palavras_busca_filtra_curtas_e_duplicatas():
    assert leitura._palavras_busca("a de Multa, multa CLÁUSULA penal!") == ["multa", "cláusula", "penal"]
    assert leitura._palavras_busca("   ") == []


def test_trechos_recorta_contexto_em_torno_das_palavras():
    texto = "x" * 500 + " CLÁUSULA 7 prevê multa de 10% " + "y" * 500
    tr = leitura._trechos(texto, ["cláusula", "multa"], janela=20)
    assert tr and tr[0].startswith("…") and "CLÁUSULA 7" in tr[0]
    assert leitura._trechos(texto, ["inexistente"]) == []
    assert leitura._trechos("", ["x"]) == []


# ── handlers ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rbac_fail_closed_em_todas_as_tools(monkeypatch):
    async def nega(db, user, case_id):
        raise HTTPException(status_code=404, detail="não encontrado")
    monkeypatch.setattr(leitura, "verificar_acesso_caso", nega)
    for nome, args in (("listar_documentos", {}), ("buscar_nos_autos", {"consulta": "multa"}),
                       ("verificar_citacoes", {"texto": "art. 5"}), ("consultar_movimentacao", {})):
        with pytest.raises(HTTPException):
            await REGISTRY.get(nome).handler(args, _ctx(_FakeDB([])))


@pytest.mark.asyncio
async def test_listar_documentos_filtra_confidencialidade_e_resume(monkeypatch):
    async def ok(db, user, case_id):
        return SimpleNamespace(id=case_id)
    monkeypatch.setattr(leitura, "verificar_acesso_caso", ok)
    docs = [SimpleNamespace(id="d1", titulo="Contrato", tipo="contrato", versao=2,
                            ocr_text="texto", created_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
            SimpleNamespace(id="d2", titulo="Foto", tipo="prova", versao=1, ocr_text=None, created_at=None)]
    out = await leitura.listar_documentos({}, _ctx(_FakeDB(docs)))
    assert out["total"] == 2
    assert out["documentos"][0]["tem_texto"] is True and out["documentos"][1]["tem_texto"] is False
    assert all("texto" not in d for d in out["documentos"])  # lista não vaza conteúdo


@pytest.mark.asyncio
async def test_ler_documento_devolve_texto_truncado_e_erro_generico(monkeypatch):
    doc = SimpleNamespace(id="d1", titulo="Laudo", tipo="prova", versao=1,
                          ocr_text="A" * (leitura._MAX_TEXTO_DOCUMENTO + 10))

    async def acessivel(db, user, *, document_id, case_id):
        if document_id == "d1":
            return doc
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    monkeypatch.setattr("app.services.document_access_policy.exigir_documento_acessivel_no_caso", acessivel)

    out = await leitura.ler_documento({"documento_id": "d1"}, _ctx())
    assert out["truncado"] is True and len(out["texto"]) == leitura._MAX_TEXTO_DOCUMENTO
    neg = await leitura.ler_documento({"documento_id": "outro"}, _ctx())
    assert neg == {"erro": "documento_inacessivel", "status": 404}
    assert (await leitura.ler_documento({}, _ctx()))["erro"] == "documento_id vazio"


@pytest.mark.asyncio
async def test_buscar_nos_autos_devolve_trechos_por_documento(monkeypatch):
    async def ok(db, user, case_id):
        return SimpleNamespace(id=case_id)
    monkeypatch.setattr(leitura, "verificar_acesso_caso", ok)
    docs = [SimpleNamespace(id="d1", titulo="Contrato", tipo="contrato",
                            ocr_text="Cláusula 9. Em caso de atraso incide multa de 2%.")]
    out = await leitura.buscar_nos_autos({"consulta": "multa atraso"}, _ctx(_FakeDB(docs)))
    assert out["palavras"] == ["multa", "atraso"] and out["total"] == 1
    assert any("multa" in t.lower() for t in out["resultados"][0]["trechos"])
    vazio = await leitura.buscar_nos_autos({"consulta": "a b"}, _ctx(_FakeDB(docs)))
    assert vazio["total"] == 0 and "erro" in vazio


@pytest.mark.asyncio
async def test_verificar_citacoes_delega_ao_verificador_local(monkeypatch):
    async def ok(db, user, case_id):
        return SimpleNamespace(id=case_id)
    monkeypatch.setattr(leitura, "verificar_acesso_caso", ok)
    chamadas = {}

    async def fake_vj(db, texto, *, consultar_datajud):
        chamadas["texto"], chamadas["datajud"] = texto, consultar_datajud
        return {"total": 1, "resultados": [{"status": "confirmada"}]}
    monkeypatch.setattr("app.services.verificador_jurisprudencia.verificar_jurisprudencia", fake_vj)
    out = await leitura.verificar_citacoes({"texto": "Súmula 7 do STJ"}, _ctx())
    assert out["total"] == 1 and chamadas == {"texto": "Súmula 7 do STJ", "datajud": False}
    assert (await leitura.verificar_citacoes({"texto": " "}, _ctx()))["erro"] == "texto vazio"


@pytest.mark.asyncio
async def test_consultar_movimentacao_local_e_degradacao_datajud(monkeypatch):
    async def ok(db, user, case_id):
        return SimpleNamespace(id=case_id, numero_processo="0000000-00.2026.8.13.0024", tribunal="TJMG")
    monkeypatch.setattr(leitura, "verificar_acesso_caso", ok)
    movs = [SimpleNamespace(tipo="decisao", descricao="Sentença de procedência",
                            data_evento=datetime(2026, 8, 30, tzinfo=timezone.utc))]
    ctx = _ctx(_FakeDB(movs))

    out = await leitura.consultar_movimentacao({}, ctx)
    assert out["total_local"] == 1 and out["movimentos"][0]["tipo"] == "decisao"
    assert "tribunal_publico" not in out

    from app.services import datajud_service as dj

    async def desligado(numero):
        raise dj.DataJudDesabilitadoError("off")
    monkeypatch.setattr(dj, "consultar_movimentos", desligado)
    out = await leitura.consultar_movimentacao({"incluir_tribunal": True}, ctx)
    assert out["tribunal_publico"]["indisponivel"] is True

    async def ligado(numero):
        return [{"data": "2026-08-30T00:00:00", "codigo": 219, "descricao": "Procedência"}]
    monkeypatch.setattr(dj, "consultar_movimentos", ligado)
    out = await leitura.consultar_movimentacao({"incluir_tribunal": True}, ctx)
    assert out["tribunal_publico"]["total"] == 1 and out["tribunal_publico"]["fonte"] == "DataJud/CNJ"
