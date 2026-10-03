"""LB8: negação, área mista e confiança determinística no issue_engine."""

from app.services.legal_brain import identify_legal_issues


def _keys(issues):
    return {issue.key for issue in issues}


def test_negacao_simples_nao_conta_termo_negado_como_indicio():
    issues = identify_legal_issues("Não houve liminar nem protesto no caso.", area=None)
    assert issues[0].key == "saneamento_inicial"
    assert "liminar" in issues[0].negated_terms


def test_negacao_sem_e_nunca():
    assert _keys(identify_legal_issues("Sem liminar até agora.")) == {"saneamento_inicial"}
    assert _keys(identify_legal_issues("Nunca houve protesto.")) == {"saneamento_inicial"}


def test_negacao_nao_se_estende_alem_da_oracao_ou_de_adversativa():
    assert "tutela_urgencia" in _keys(identify_legal_issues("Não houve citação, há pedido de liminar."))
    assert "tutela_urgencia" in _keys(identify_legal_issues("Não houve citação mas há liminar."))


def test_termo_negado_e_afirmado_em_outro_trecho_continua_indicio():
    issues = identify_legal_issues("Não houve protesto. Pedido de liminar urgente.")
    tutela = next(issue for issue in issues if issue.key == "tutela_urgencia")
    assert "liminar" in tutela.matched_terms
    assert "protesto" in tutela.negated_terms


def test_ausencia_de_prova_continua_sendo_lacuna_probatoria():
    assert "prova_onus_lacunas" in _keys(identify_legal_issues("Cliente está sem prova do pagamento."))


def test_area_mista_mantem_a_de_maior_pontuacao_e_adiciona_outra_area():
    texto = "Consumidor questiona serviço e defeito do produto; há cobrança de juros e tarifa do banco."
    # Área informada (familia) não cobre nenhuma das duas: antes ambas sumiam.
    issues = identify_legal_issues(texto, area="familia")
    by_key = {issue.key: issue for issue in issues}
    assert by_key["relacao_consumo_responsabilidade"].score >= 4
    assert by_key["relacao_consumo_responsabilidade"].area == "consumidor"
    assert by_key["bancario_contrato_encargos"].area == "bancario"
    assert by_key["relacao_consumo_responsabilidade"].confidence <= 0.5
    # Dentro da área informada, a confiança não é reduzida.
    dentro = identify_legal_issues(texto, area="consumidor")
    assert {i.key: i for i in dentro}["relacao_consumo_responsabilidade"].confidence > 0.5


def test_termo_isolado_de_outra_area_nao_cria_questao():
    issues = identify_legal_issues("Cliente comprou um produto.", area="bancario")
    assert _keys(issues) == {"saneamento_inicial"}


def test_confianca_deterministica_e_crescente_com_indicios():
    um = identify_legal_issues("Pedido de liminar.")[0]
    dois = identify_legal_issues("Pedido de liminar com urgência.")[0]
    assert (um.score, dois.score) == (1, 2)
    assert 0 < um.confidence < dois.confidence < 1
    assert identify_legal_issues("Pedido de liminar.")[0] == um


def test_saneamento_tem_confianca_zero():
    saneamento = identify_legal_issues("Relato ainda incompleto")[0]
    assert (saneamento.key, saneamento.score, saneamento.confidence) == ("saneamento_inicial", 0, 0.0)


def test_limite_preserva_a_questao_de_maior_pontuacao():
    texto = "Pedido de liminar, urgência, tutela, bloqueio e prazo."
    issues = identify_legal_issues(texto, limit=1)
    assert [issue.key for issue in issues] == ["tutela_urgencia"]
