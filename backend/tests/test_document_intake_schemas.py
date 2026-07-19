"""#83 Gap A — contrato TIPADO da extração de importação de documentos.

Trava o comportamento de `DocumentoIntakeResult` + `_montar_intake_result`:
  • JSON do LLM válido → resultado populado corretamente.
  • Lacuna (nulls) → None/lista vazia; nunca KeyError.
  • LLM inválido/None/parcial → coerção fail-safe, necessita_revisao_humana=True,
    sem exceção.
  • Campo determinístico (CPF/CNJ de extrair_estruturas) aparece com
    trecho_origem literal e confiança 1.0.
"""
from app.schemas.document_intake import (
    CampoExtraido, DocumentoIntakeResult,
)
from app.services.documento_service import _montar_intake_result
from app.services.extracao_estruturada import extrair_estruturas


_DADOS_ESTRUTURADOS_VAZIO = {
    "processos_cnj": [], "cpfs": [], "cnpjs": [], "datas": [],
    "valores": [], "emails": [], "telefones": [], "total": 0,
}


def _llm_valido() -> dict:
    return {
        "identificacao_processual": {
            "numero_processo": "1234567-89.2020.8.13.0024",
            "vara": "2ª Vara Cível", "tribunal": "TJMG", "comarca": "Belo Horizonte",
        },
        "partes": {
            "autor": "Maria Souza", "reu": "Banco XPTO S.A.",
            "terceiros": ["João Terceiro"],
        },
        "dados_pessoais": {"nome": "Maria Souza", "email": "maria@ex.com",
                           "telefone": "(31) 99999-8888"},
        "classificacao": {"area": "civil", "subarea": "contratos", "materia": "revisional"},
        "resumo_executivo": {"fatos": "Discussão contratual bancária.",
                             "pedidos": "Revisão de cláusulas e repetição de indébito."},
        "diagnostico": {"riscos": ["Prescrição parcial", "Prova documental frágil"]},
        "brechas_processuais": {"teses_defensivas": ["Onerosidade excessiva"]},
        "valor_causa_estimado": 50000,
        "campos_v2": {
            "valor_causa": {"valor": 50000, "trecho_origem": "valor da causa R$ 50.000",
                            "confianca": 0.8},
        },
    }


def test_llm_valido_popula_result():
    r = _montar_intake_result(_llm_valido(), _DADOS_ESTRUTURADOS_VAZIO)
    assert isinstance(r, DocumentoIntakeResult)

    assert r.caso is not None
    assert r.caso.area == "civil"
    assert r.caso.subramo == "contratos"
    assert r.caso.vara == "2ª Vara Cível"
    assert r.caso.tribunal == "TJMG"
    assert r.caso.orgao == "Belo Horizonte"
    # Sem determinístico, o nº CNJ vem do LLM (trecho_origem None).
    assert r.caso.numero_cnj.valor == "1234567-89.2020.8.13.0024"
    assert r.caso.valor_causa.valor == 50000
    assert r.caso.valor_causa.confianca == 0.8
    assert r.caso.resumo_fatos == "Discussão contratual bancária."

    papeis = {(p.nome, p.papel) for p in r.partes}
    assert ("Maria Souza", "autor") in papeis
    assert ("Banco XPTO S.A.", "reu") in papeis
    assert ("João Terceiro", "terceiro") in papeis

    assert r.cliente is not None
    assert r.cliente.nome == "Maria Souza"
    assert r.cliente.email == "maria@ex.com"

    assert [p.descricao for p in r.pedidos] == \
        ["Revisão de cláusulas e repetição de indébito."]
    assert {x.descricao for x in r.riscos} == \
        {"Prescrição parcial", "Prova documental frágil"}
    assert [t.titulo for t in r.teses] == ["Onerosidade excessiva"]

    # Minuta: revisão humana sempre obrigatória.
    assert r.necessita_revisao_humana is True


def test_lacuna_vira_none_ou_lista_vazia():
    """Todos os campos null no LLM → None/listas vazias, sem KeyError."""
    dados = {
        "identificacao_processual": {"numero_processo": None, "vara": None,
                                     "tribunal": None, "comarca": None},
        "partes": {"autor": None, "reu": None, "terceiros": []},
        "dados_pessoais": {"nome": None, "email": None, "telefone": None},
        "classificacao": {"area": None, "subarea": None},
        "resumo_executivo": {"fatos": None, "pedidos": None},
        "diagnostico": {"riscos": []},
        "brechas_processuais": {"teses_defensivas": []},
        "valor_causa_estimado": None,
    }
    r = _montar_intake_result(dados, _DADOS_ESTRUTURADOS_VAZIO)
    assert r.caso.area is None
    assert r.caso.numero_cnj is None
    assert r.caso.valor_causa is None
    assert r.caso.resumo_fatos is None
    assert r.cliente is None            # nenhum sinal de cliente
    assert r.partes == []
    assert r.pedidos == []
    assert r.riscos == []
    assert r.teses == []
    assert r.pendencias == []
    assert r.necessita_revisao_humana is True


def test_llm_none_e_invalido_falha_safe():
    """LLM None / não-dict / lixo → contrato mínimo válido, sem exceção."""
    for entrada in (None, "resposta sem json", 42, [], {"partes": "isso não é dict"}):
        r = _montar_intake_result(entrada, _DADOS_ESTRUTURADOS_VAZIO)
        assert isinstance(r, DocumentoIntakeResult)
        assert r.necessita_revisao_humana is True
        assert r.partes == [] and r.riscos == [] and r.teses == []
        # model_dump JSON-serializável (o que o serviço devolve ao frontend).
        assert isinstance(r.model_dump(mode="json"), dict)


def test_llm_parcial_nao_quebra():
    """Só um pedaço do esquema presente → aproveita o que dá, resto None."""
    r = _montar_intake_result({"classificacao": {"area": "trabalhista"}},
                              _DADOS_ESTRUTURADOS_VAZIO)
    assert r.caso.area == "trabalhista"
    assert r.caso.numero_cnj is None
    assert r.partes == []


def test_dados_deterministicos_none_nao_quebra():
    """dados_estruturados None/inválido → sem exceção."""
    r = _montar_intake_result(_llm_valido(), None)
    assert isinstance(r, DocumentoIntakeResult)
    r2 = _montar_intake_result(None, None)
    assert isinstance(r2, DocumentoIntakeResult)


def test_campo_deterministico_traz_trecho_origem():
    """CPF/CNJ vindos de extrair_estruturas aparecem como CampoExtraido com
    trecho_origem = literal e confiança 1.0 (regex + DV local, sem IA)."""
    texto = ("Cliente Maria Souza, CPF 987.654.321-00, processo "
             "1234567-89.2020.8.13.0024, discussão contratual.")
    det = extrair_estruturas(texto)
    # Sanidade do determinístico.
    assert det["cpfs"][0]["valor"] == "987.654.321-00"
    assert det["processos_cnj"][0]["valor"] == "1234567-89.2020.8.13.0024"

    r = _montar_intake_result(_llm_valido(), det)

    # nº CNJ determinístico PREVALECE sobre o do LLM e carrega trecho_origem.
    assert r.caso.numero_cnj.valor == "1234567-89.2020.8.13.0024"
    assert r.caso.numero_cnj.trecho_origem == "1234567-89.2020.8.13.0024"
    assert r.caso.numero_cnj.confianca == 1.0

    # CPF determinístico chega no cliente com trecho_origem literal.
    assert r.cliente is not None
    assert isinstance(r.cliente.cpf, CampoExtraido)
    assert r.cliente.cpf.valor == "987.654.321-00"
    assert r.cliente.cpf.trecho_origem == "987.654.321-00"
    assert r.cliente.cpf.confianca == 1.0


def test_area_fora_do_canonico_vira_outro_com_bruto_preservado():
    """Contrato (auditoria item 6): caso.area é SEMPRE canônica — texto da IA
    fora da taxonomia vira 'outro' e o bruto fica em caso.area_bruta."""
    llm = _llm_valido()
    llm["classificacao"]["area"] = "direito dos drones"
    r = _montar_intake_result(llm, _DADOS_ESTRUTURADOS_VAZIO)
    assert r.caso.area == "outro"
    assert r.caso.area_bruta == "direito dos drones"


def test_area_canonica_nao_carrega_area_bruta():
    r = _montar_intake_result(_llm_valido(), _DADOS_ESTRUTURADOS_VAZIO)
    assert r.caso.area == "civil"
    assert r.caso.area_bruta is None
