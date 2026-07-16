from datetime import date, timedelta
from types import SimpleNamespace

from app.services.raio_x_enrichment import enriquecer_relatorio


def _doc(doc_id: str, intake: dict):
    return SimpleNamespace(
        id=doc_id,
        nome_original=f"{doc_id}.pdf",
        tipo_documento="processo",
        sha256=f"hash-{doc_id}",
        resultado_analise={"intake_result": intake},
    )


def _base():
    return {
        "fontes": [],
        "identificacao": {"area": "civil", "numero_processo": "0000000-00.2026.8.00.0000"},
        "sintese_executiva": "Cobrança discutida no processo.",
        "partes": ["Maria", "Banco X"],
        "pedidos": ["declarar inexigibilidade"],
        "provas": ["contrato bancário", "extrato da cobrança"],
        "prazos_potenciais": [],
        "riscos": [],
        "pontos_fortes": [],
        "pontos_fracos": [],
        "proximos_passos": [],
        "documentos_pendentes": [],
    }


def test_constroi_cronologia_decisoes_e_matriz_fato_prova():
    docs = [
        _doc(
            "doc-1",
            {
                "resumo_fatos": "Banco realizou cobrança fundada em contrato bancário.",
                "fatos": [{"descricao": "Banco realizou cobrança contratual", "pagina": 2}],
                "provas": [{"descricao": "Contrato bancário e extrato da cobrança", "pagina": 10}],
                "eventos": [{"data": "10/07/2026", "descricao": "Distribuição da ação"}],
                "decisoes": [{"data": "12/07/2026", "tipo": "decisão", "dispositivo": "Intime-se a parte autora"}],
            },
        )
    ]
    report = enriquecer_relatorio(docs, _base())

    assert report["cronologia"][0]["data"] == "2026-07-10"
    assert report["decisoes"][0]["comando"] == "Intime-se a parte autora"
    assert report["fatos_provas"][0]["estado"] == "correlacao_localizada"
    assert report["fatos_provas"][0]["provas_relacionadas"]
    assert report["rito_jornada"]["metodo"] == "motor_ritos_deterministico_v1"


def test_detecta_divergencia_de_numero_e_valor():
    docs = [
        _doc("doc-1", {"numero_processo": "111", "valor_causa": "1000", "resumo_fatos": "Fato A"}),
        _doc("doc-2", {"numero_processo": "222", "valor_causa": "2000", "resumo_fatos": "Fato A"}),
    ]
    report = enriquecer_relatorio(docs, _base())
    fields = {item.get("campo") for item in report["contradicoes"]}
    assert "numero_processo" in fields
    assert "valor_causa" in fields
    assert any("contradição" in step.lower() or "diverg" in step.lower() for step in report["proximos_passos"])


def test_prazo_proximo_marca_urgencia_e_risco():
    deadline = (date.today() + timedelta(days=2)).isoformat()
    base = _base()
    base["prazos_potenciais"] = [{"titulo": "Manifestação", "data": deadline}]
    report = enriquecer_relatorio([], base)

    assert report["prazo_urgente"] is True
    assert report["risco_nivel"] in {"elevado", "critico"}
    assert report["avaliacao_risco"]["score_interno"] >= 4


def test_nao_confunde_correlacao_com_confirmacao_juridica():
    docs = [_doc("doc-1", {"fatos": ["alegação sem suporte"], "provas": []})]
    report = enriquecer_relatorio(docs, _base())
    assert report["fatos_provas"][0]["confirmado"] is False
    assert report["fatos_provas"][0]["estado"] == "sem_prova_correlacionada"
    assert report["confianca_global"] in {
        "moderada_com_revisao_obrigatoria",
        "insuficiente_para_automatizacao",
    }
