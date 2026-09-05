"""Veredito IA — reescrito com motores REAIS (auditoria 04/07/2026).

Prova que o módulo deixou de ser fake:
  - probabilidade vem da jurimetria interna (taxa real) ou é None (amostra
    insuficiente) — nunca número inventado;
  - jurisprudência vem do RAG interno — nunca a lista hardcoded antiga
    (link1.com);
  - verificador de citações (citation_check) está acoplado ao retorno;
  - AILog é registrado na chamada de IA;
  - shape da resposta permanece compatível com o frontend.
"""
import json


class _FakeUser:
    id = "u-1"


class _FakeDB:
    """Placeholder — todo acesso a banco é monkeypatchado nos testes."""


_GW_JSON = '{"sugestoes": [{"tipo": "Melhoria", "descricao": "Ancorar a tese no REsp do contexto."}]}'

_RAG_CHUNKS = [
    {"chunk_id": "c1",
     "conteudo": "Ementa real ingerida: responsabilidade civil objetiva do fornecedor.",
     "titulo": "STJ — REsp 1.234.567", "categoria": "jurisprudencia",
     "fonte": "https://scon.stj.jus.br/exemplo"},
    {"chunk_id": "c2",
     "conteudo": "Ementa real ingerida: dano moral em relação de consumo.",
     "titulo": "Acórdão TJMG apelação cível", "categoria": "jurisprudencia",
     "fonte": "ingestao interna"},
]


def _jurimetria(n, taxa_com_acordo, suficiente, grupo="civil"):
    return {
        "global": {"n": n},
        "grupos": [{
            "grupo": grupo, "n": n,
            "taxa_exito": taxa_com_acordo, "taxa_exito_com_acordo": taxa_com_acordo,
            "amostra_suficiente": suficiente,
        }],
    }


def _setup(monkeypatch, *, jurimetria_data, rag_chunks, gw_texto=_GW_JSON,
           relatorio_citacoes=None):
    calls = {}

    async def fake_jurimetria(db, user, dimensao=None):
        calls["jurimetria_dimensao"] = dimensao
        return jurimetria_data

    async def fake_rag(db, consulta, limite=6, categorias=None,
                       modo_or=False, scope_client_id=None):
        calls["rag"] = {"consulta": consulta, "categorias": categorias,
                        "scope": scope_client_id, "modo_or": modo_or}
        return rag_chunks

    async def fake_escopo(db, case_id):
        calls["escopo_case_id"] = case_id
        return "cli-1" if case_id else None

    async def fake_verificar(db, texto, **kw):
        calls["verificador_texto"] = texto
        return relatorio_citacoes or {
            "score": 80, "avisos": ["confirme o inteiro teor antes do protocolo"],
        }

    async def fake_log(db, **kw):
        calls["ai_log"] = kw
        return "log-1"

    async def fake_chat(*, messages, **kw):
        calls["gw"] = {"messages": messages, **kw}
        class _R:
            texto = gw_texto
            provedor = "ollama"
            modelo = "modelo-teste"
            input_tokens = 10
            output_tokens = 20
        return _R()

    monkeypatch.setattr("app.core.veredito_ia.calcular_jurimetria", fake_jurimetria)
    monkeypatch.setattr("app.core.veredito_ia.buscar_contexto_rag", fake_rag)
    monkeypatch.setattr("app.core.veredito_ia._escopo_cliente_do_caso", fake_escopo)
    monkeypatch.setattr("app.core.veredito_ia.verificar_citacoes", fake_verificar)
    monkeypatch.setattr("app.core.veredito_ia.registrar_ai_log", fake_log)
    # gw_chat é importado em runtime dentro do método → patch no módulo fonte.
    monkeypatch.setattr("app.services.ai_gateway.chat", fake_chat)
    return calls


async def _analisar(area="Civel", case_id=None):
    from app.core.veredito_ia import VereditoIA
    return await VereditoIA().predict_success(
        "Tese de responsabilidade civil do fornecedor por vício do produto.",
        area, ["STJ", "TJMG"], db=_FakeDB(), user=_FakeUser(), case_id=case_id)


async def test_probabilidade_null_com_amostra_insuficiente(monkeypatch):
    _setup(monkeypatch, jurimetria_data=_jurimetria(2, 50.0, False),
           rag_chunks=_RAG_CHUNKS)
    r = await _analisar()
    assert r.probabilidade_exito is None          # nunca número inventado
    assert r.fonte_probabilidade is None
    assert r.n_amostra == 2
    assert any("insuficiente" in a.lower() for a in r.avisos)


async def test_probabilidade_e_taxa_real_da_jurimetria(monkeypatch):
    calls = _setup(monkeypatch, jurimetria_data=_jurimetria(12, 66.7, True),
                   rag_chunks=_RAG_CHUNKS)
    r = await _analisar(area="Civel")   # "Civel" → grupo "civil" (sinônimo)
    assert r.probabilidade_exito == 0.667          # 66.7% real, não heurística
    assert r.n_amostra == 12
    assert "12" in r.fonte_probabilidade
    assert "jurimetria" in r.fonte_probabilidade.lower()
    assert calls["jurimetria_dimensao"] == "area"


async def test_jurisprudencia_vem_do_rag_e_nunca_do_mock_antigo(monkeypatch):
    calls = _setup(monkeypatch, jurimetria_data=_jurimetria(12, 66.7, True),
                   rag_chunks=_RAG_CHUNKS)
    r = await _analisar(case_id="case-1")
    dump = json.dumps(r.model_dump(), ensure_ascii=False)
    # zero resquício da lista fake antiga
    assert "link1.com" not in dump and "link2.com" not in dump
    assert "Jurisprudência relevante" not in dump
    # conteúdo veio dos chunks do RAG
    assert len(r.jurisprudencia_suporte) == 2
    assert "responsabilidade civil objetiva" in r.jurisprudencia_suporte[0].ementa
    assert r.jurisprudencia_suporte[0].tribunal == "STJ"
    assert r.jurisprudencia_suporte[0].link == "https://scon.stj.jus.br/exemplo"
    assert r.jurisprudencia_suporte[1].link is None   # fonte não-URL → sem link
    # busca escopada e nas categorias públicas de jurisprudência
    assert calls["escopo_case_id"] == "case-1"
    assert calls["rag"]["scope"] == "cli-1"
    assert "jurisprudencia" in calls["rag"]["categorias"]


async def test_rag_vazio_devolve_lista_vazia_com_aviso(monkeypatch):
    _setup(monkeypatch, jurimetria_data=_jurimetria(12, 66.7, True), rag_chunks=[])
    r = await _analisar()
    assert r.jurisprudencia_suporte == []          # sem resultado = vazio, não fake
    assert any("nenhuma jurisprud" in a.lower() for a in r.avisos)


async def test_verificador_de_citacoes_acoplado(monkeypatch):
    calls = _setup(monkeypatch, jurimetria_data=_jurimetria(12, 66.7, True),
                   rag_chunks=_RAG_CHUNKS,
                   relatorio_citacoes={"score": 55, "avisos": ["1 citação suspeita"]})
    r = await _analisar()
    assert r.score_citacoes == 55
    assert "1 citação suspeita" in r.avisos
    # o material verificado inclui as ementas retornadas e a resposta da IA
    assert "responsabilidade civil objetiva" in calls["verificador_texto"]


async def test_ai_log_registrado_na_chamada_de_ia(monkeypatch):
    calls = _setup(monkeypatch, jurimetria_data=_jurimetria(12, 66.7, True),
                   rag_chunks=_RAG_CHUNKS)
    await _analisar(case_id="case-1")
    log = calls["ai_log"]
    assert log["user_id"] == "u-1"
    assert log["case_id"] == "case-1"
    assert log["resposta"] == _GW_JSON
    assert log["modelo"] == "ollama/modelo-teste"


async def test_shape_compativel_com_frontend_e_hitl(monkeypatch):
    _setup(monkeypatch, jurimetria_data=_jurimetria(12, 66.7, True),
           rag_chunks=_RAG_CHUNKS)
    r = await _analisar()
    dump = r.model_dump()
    # chaves que o componente VeredutoIAWithVictoryVault consome
    for chave in ("probabilidade_exito", "teses_vitoriosas_similares",
                  "jurisprudencia_suporte", "sugestoes_contextualizadas",
                  "score_citacoes", "avisos", "fonte_probabilidade",
                  "n_amostra", "status_hitl"):
        assert chave in dump
    # sugestões parseadas do JSON da IA
    assert r.sugestoes_contextualizadas[0].tipo == "Melhoria"
    # HITL: rascunho com aviso padrão de revisão obrigatória
    assert r.status_hitl == "rascunho"
    assert any("revisão humana" in a.lower() for a in r.avisos)


async def test_ia_indisponivel_degrada_sem_inventar(monkeypatch):
    _setup(monkeypatch, jurimetria_data=_jurimetria(12, 66.7, True),
           rag_chunks=_RAG_CHUNKS)

    async def gw_quebrado(*a, **k):
        raise RuntimeError("ollama down")
    monkeypatch.setattr("app.services.ai_gateway.chat", gw_quebrado)

    r = await _analisar()
    assert r.sugestoes_contextualizadas == []      # nada inventado
    assert r.probabilidade_exito == 0.667          # jurimetria continua real
    assert any("indisponível" in a.lower() for a in r.avisos)
