# ── tests/test_pecas_rag_modelos.py ──────────────────────────────────────────
# RAG-augmented na geração de peças: recuperar os MODELOS da "Bíblia de
# Conhecimento" (categoria "modelo_documento_juridico") como referência de
# estrutura/tese na montagem final. Cobre o helper gated/fail-safe, a função
# pura que monta o bloco e o contrato de auditoria (fontes_rag "modelo:<id>").
#
# Sem Postgres: buscar_contexto_rag é monkeypatchado e get_settings é
# substituído por um fake de flags, mantendo o teste em unidade.
from __future__ import annotations

from types import SimpleNamespace


import app.services.peca_service as ps


def _fake_settings(enabled: bool = True, topk: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        PECAS_RAG_MODELOS_ENABLED=enabled,
        PECAS_RAG_MODELOS_TOPK=topk,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Filtro por categoria — a query dedicada NÃO afoga os modelos
# ══════════════════════════════════════════════════════════════════════════

async def test_helper_filtra_por_categoria_modelo(monkeypatch):
    chamadas: list[dict] = []

    async def fake_buscar(db, consulta, **kw):
        chamadas.append({"consulta": consulta, **kw})
        return [{"chunk_id": "c1", "titulo": "Modelo X", "conteudo": "corpo"}]

    monkeypatch.setattr(ps, "get_settings", lambda: _fake_settings(topk=3))
    monkeypatch.setattr(ps, "buscar_contexto_rag", fake_buscar)

    out = await ps._recuperar_modelos_referencia(
        db=object(),
        area_direito="civil",
        tipo_peca_final="peticao_inicial",
        pedidos_limpos="indenização por danos morais",
        tese_txt="culpa presumida",
    )

    assert len(chamadas) == 1
    c = chamadas[0]
    assert c["categorias"] == ["modelo_documento_juridico"]
    assert c["modo_or"] is True
    assert c["limite"] == 3
    # a query dedicada carrega o nome legível do tipo + área + pedidos + tese
    assert "Petição Inicial" in c["consulta"]
    assert "civil" in c["consulta"]
    assert "danos morais" in c["consulta"]
    assert "culpa presumida" in c["consulta"]
    assert out and out[0]["chunk_id"] == "c1"


# ══════════════════════════════════════════════════════════════════════════
# 2. Degradação graciosa — exceção NÃO propaga
# ══════════════════════════════════════════════════════════════════════════

async def test_helper_degradacao_graciosa_em_excecao(monkeypatch):
    async def fake_boom(db, consulta, **kw):
        raise RuntimeError("pgvector indisponível")

    monkeypatch.setattr(ps, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(ps, "buscar_contexto_rag", fake_boom)

    out = await ps._recuperar_modelos_referencia(
        db=object(), area_direito="civil", tipo_peca_final="contestacao",
        pedidos_limpos="x", tese_txt="y",
    )
    assert out == []


async def test_helper_resultado_vazio_retorna_lista_vazia(monkeypatch):
    async def fake_vazio(db, consulta, **kw):
        return []

    monkeypatch.setattr(ps, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(ps, "buscar_contexto_rag", fake_vazio)

    out = await ps._recuperar_modelos_referencia(
        db=object(), area_direito="civil", tipo_peca_final="contestacao",
        pedidos_limpos="x", tese_txt="y",
    )
    assert out == []


# ══════════════════════════════════════════════════════════════════════════
# 3. Flag OFF — comportamento atual idêntico (RAG nem é chamado)
# ══════════════════════════════════════════════════════════════════════════

async def test_flag_off_nao_chama_rag(monkeypatch):
    chamou = {"count": 0}

    async def fake_buscar(db, consulta, **kw):
        chamou["count"] += 1
        return [{"chunk_id": "c1", "titulo": "t", "conteudo": "x"}]

    monkeypatch.setattr(ps, "get_settings", lambda: _fake_settings(enabled=False))
    monkeypatch.setattr(ps, "buscar_contexto_rag", fake_buscar)

    out = await ps._recuperar_modelos_referencia(
        db=object(), area_direito="civil", tipo_peca_final="peticao_inicial",
        pedidos_limpos="x", tese_txt="y",
    )
    assert out == []
    assert chamou["count"] == 0


# ══════════════════════════════════════════════════════════════════════════
# 4. Bloco de modelos — função pura, testável isoladamente
# ══════════════════════════════════════════════════════════════════════════

def test_formatar_bloco_modelos_vazio_retorna_string_vazia():
    assert ps._formatar_bloco_modelos([]) == ""


def test_formatar_bloco_modelos_estrutura_e_truncamento():
    modelos = [
        {"chunk_id": "c1", "titulo": "Ação de Cobrança", "conteudo": "A" * 5000},
        {"chunk_id": "c2", "titulo": "Contestação Modelo", "conteudo": "corpo curto"},
    ]
    bloco = ps._formatar_bloco_modelos(modelos)

    assert "MODELOS DE REFERÊNCIA (uso interno — NÃO copiar literalmente):" in bloco
    assert "FICTÍCIO" in bloco  # aviso de material fictício
    assert "[Modelo 1] Ação de Cobrança" in bloco
    assert "[Modelo 2] Contestação Modelo" in bloco
    # conteúdo do 1º modelo truncado em 1200 chars (não vaza os 5000)
    assert "A" * 1200 in bloco
    assert "A" * 1201 not in bloco


def test_formatar_bloco_modelos_titulo_ausente_usa_fallback():
    bloco = ps._formatar_bloco_modelos([{"chunk_id": "c1", "conteudo": "x"}])
    assert "[Modelo 1] Modelo 1" in bloco


# ══════════════════════════════════════════════════════════════════════════
# 5. Auditoria — os ids dos modelos entram em fontes_rag como "modelo:<id>"
# ══════════════════════════════════════════════════════════════════════════

def test_fontes_rag_marca_modelos_com_prefixo():
    # Reproduz a expressão de montagem de AILog.fontes_rag do pipeline (Etapa 7).
    fontes = [{"chunk_id": "leg1"}, {"chunk_id": "juris2"}]
    modelos_referencia = [{"chunk_id": "mod9"}, {"chunk_id": "mod10"}]

    fontes_rag = (
        "; ".join(
            [f["chunk_id"] for f in fontes]
            + [f"modelo:{m['chunk_id']}" for m in modelos_referencia]
        )
        or None
    ) if (fontes or modelos_referencia) else None

    assert fontes_rag == "leg1; juris2; modelo:mod9; modelo:mod10"


def test_fontes_rag_none_sem_fontes_nem_modelos():
    fontes: list[dict] = []
    modelos_referencia: list[dict] = []
    fontes_rag = (
        "; ".join(
            [f["chunk_id"] for f in fontes]
            + [f"modelo:{m['chunk_id']}" for m in modelos_referencia]
        )
        or None
    ) if (fontes or modelos_referencia) else None
    assert fontes_rag is None
