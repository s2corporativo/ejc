from types import SimpleNamespace

from app.services.raio_x_service import consolidar_relatorio


def _documento(doc_id: str, resultado: dict):
    return SimpleNamespace(
        id=doc_id,
        nome_original=f"{doc_id}.pdf",
        tipo_documento="processo",
        sha256=f"hash-{doc_id}",
        resultado_analise=resultado,
    )


def test_consolidacao_mantem_prazos_como_potenciais_e_nao_confirmados():
    relatorio = consolidar_relatorio([
        _documento(
            "doc-1",
            {
                "intake_result": {
                    "cliente": "Cliente teste",
                    "numero_processo": "0000000-00.2026.8.00.0000",
                    "resumo_fatos": "Relato extraído do documento.",
                    "prazos": [
                        {
                            "titulo": "Prazo informado na peça",
                            "data": "21/07/2026",
                        }
                    ],
                }
            },
        )
    ])

    assert relatorio["confianca_global"] == "insuficiente_para_automatizacao"
    assert relatorio["prazos_potenciais"][0]["titulo"] == "Prazo informado na peça"
    assert relatorio["cronologia"][0]["data"] == "2026-07-21"
    assert relatorio["cronologia"][0]["confirmado"] is False
    assert "confirmação humana" in relatorio["aviso"]


def test_consolidacao_remove_repeticoes_e_preserva_fontes():
    resultado = {
        "intake_result": {
            "partes": ["Maria", "maria", "Empresa X"],
            "pedidos": ["Tutela", "Tutela"],
            "provas": ["Contrato"],
        }
    }
    relatorio = consolidar_relatorio([
        _documento("doc-1", resultado),
        _documento("doc-2", resultado),
    ])

    assert relatorio["partes"] == ["Maria", "Empresa X"]
    assert relatorio["pedidos"] == ["Tutela"]
    assert relatorio["provas"] == ["Contrato"]
    assert [fonte["documento_id"] for fonte in relatorio["fontes"]] == [
        "doc-1",
        "doc-2",
    ]


# ── Onda 4 — separar status técnico (pipeline) de mérito jurídico ───────────

def test_falha_de_identificacao_vai_para_lacunas_nao_para_pontos_fracos():
    """Achado da auditoria: 'não achei o número do processo' NÃO pode chegar
    ao advogado como fraqueza jurídica do caso — é status do pipeline."""
    relatorio = consolidar_relatorio([
        _documento("doc-1", {"intake_result": {"resumo_fatos": "Relato qualquer."}})
    ])

    assert "Número do processo não identificado" in relatorio["lacunas_da_analise"]
    assert "Partes não identificadas com segurança" in relatorio["lacunas_da_analise"]
    assert "Provas ainda não classificadas" in relatorio["lacunas_da_analise"]
    # Nenhum diagnóstico técnico contamina o mérito.
    for lacuna in relatorio["lacunas_da_analise"]:
        assert lacuna not in relatorio["pontos_fracos"]


def test_pontos_fracos_so_recebe_fraqueza_juridica_substantiva():
    """pontos_fracos nasce vazio e só é preenchido por achado substantivo
    (fato sem prova correlacionada, contradição) — nunca por lacuna técnica."""
    relatorio = consolidar_relatorio([
        _documento(
            "doc-1",
            {
                "intake_result": {
                    "numero_processo": "0000000-00.2026.8.00.0000",
                    "partes": ["Maria"],
                    "provas": ["Contrato de prestação de serviço"],
                    # Sem resumo_fatos: nenhum "fato" entra na matriz, então
                    # nenhuma fraqueza SUBSTANTIVA é gerada — caso de controle.
                }
            },
        )
    ])
    assert relatorio["pontos_fracos"] == []
    # As 3 lacunas técnicas não existem aqui (identificação completa) — a
    # ausência de contaminação é confirmada no teste seguinte, com fato real.


def test_fato_sem_prova_e_fraqueza_substantiva_nao_lacuna_tecnica():
    """Um fato relatado sem prova correlacionada É mérito (fraqueza real do
    caso) — corretamente vai para pontos_fracos, não para lacunas_da_analise."""
    relatorio = consolidar_relatorio([
        _documento(
            "doc-1",
            {
                "intake_result": {
                    "numero_processo": "0000000-00.2026.8.00.0000",
                    "partes": ["Maria"],
                    "provas": ["Contrato de prestação de serviço"],
                    "resumo_fatos": "O cliente alega ter sofrido dano moral em decorrência de negativação indevida.",
                }
            },
        )
    ])
    assert relatorio["lacunas_da_analise"] == []
    assert any("sem prova correlacionada" in item for item in relatorio["pontos_fracos"])


def test_pontos_fortes_nao_fica_vazio_quando_ha_teses():
    relatorio = consolidar_relatorio([
        _documento(
            "doc-1",
            {
                "intake_result": {
                    "teses": ["Prescrição intercorrente", "Nulidade da citação"],
                    "resumo_fatos": "Relato qualquer.",
                }
            },
        )
    ])
    assert relatorio["pontos_fortes"], "teses identificadas mas pontos_fortes vazio"
    assert "Prescrição intercorrente" in relatorio["pontos_fortes"][0]


def test_pontos_fortes_permanece_vazio_sem_teses_nem_correlacao():
    relatorio = consolidar_relatorio([
        _documento("doc-1", {"intake_result": {"resumo_fatos": "Relato qualquer."}})
    ])
    assert relatorio["pontos_fortes"] == []


def test_proximos_passos_sao_acao_nao_diagnostico():
    relatorio = consolidar_relatorio([
        _documento("doc-1", {"intake_result": {"resumo_fatos": "Relato qualquer."}})
    ])
    passos = relatorio["proximos_passos"]
    # O diagnóstico bruto não aparece mais como próximo passo — vira ação.
    assert "Número do processo não identificado" not in passos
    assert any("Informar o número do processo" in p for p in passos)
    assert any("Confirmar" in p and "partes" in p for p in passos)


def test_documentos_pendentes_preserva_lacunas_e_pendencias():
    """Compatibilidade: documentos_pendentes segue combinando o que faltou
    identificar com as pendências extraídas pela IA."""
    relatorio = consolidar_relatorio([
        _documento(
            "doc-1",
            {"intake_result": {"pendencias": ["Juntar procuração"], "resumo_fatos": "x"}},
        )
    ])
    assert "Número do processo não identificado" in relatorio["documentos_pendentes"]
    assert "Juntar procuração" in relatorio["documentos_pendentes"]


def test_analise_completa_sem_lacunas_tecnicas():
    """Caso com identificação, partes e provas completas não gera nenhuma
    lacuna técnica — o pipeline não inventa problema que não existe."""
    relatorio = consolidar_relatorio([
        _documento(
            "doc-1",
            {
                "intake_result": {
                    "numero_processo": "0000000-00.2026.8.00.0000",
                    "partes": ["Maria", "Empresa X"],
                    "provas": ["Contrato"],
                    "resumo_fatos": "Relato completo.",
                }
            },
        )
    ])
    assert relatorio["lacunas_da_analise"] == []
