# Invariantes da liberação do acervo RAG (achado C-1 da auditoria de
# 04/09/2026). A liberação preenche o metadado que o gate de recuperação
# exige — ela NUNCA pode virar um caminho para contornar o gate.
#
# Os testes abaixo não precisam de banco: aferem as CONDIÇÕES SQL e as
# constantes de política, que é onde um erro se tornaria perigoso.
from scripts import liberar_acervo_rag as lib


def test_proposicao_legislativa_nunca_recebe_vigencia():
    """Proposta em tramitação não é norma vigente e não fundamenta peça.

    O gate alcança `proposicao_legislativa` por acidente de substring
    (`LIKE '%legisl%'`); a liberação NÃO pode desfazer esse bloqueio."""
    assert "proposicao_legislativa" not in lib.CATS_VIGENCIA
    assert "legislacao" in lib.CATS_VIGENCIA


def test_liberacao_de_vigencia_nunca_sobrepoe_revogacao():
    """Norma revogada/suspensa jamais volta a valer por liberação em lote."""
    for status in ("revogada", "revogado", "parcialmente_revogada", "suspensa"):
        assert status in lib.STATUS_INTOCAVEIS
    assert "lower(btrim(COALESCE(extra->>'legal_status','')))" in lib._COND_VIGENCIA
    assert "<> ALL(:intocaveis)" in lib._COND_VIGENCIA


def test_aprovacao_nunca_sobrepoe_decisao_humana():
    """Só documento SEM status ou 'pendente' é promovido.

    'recusado' e 'bloqueado' são decisão humana explícita; quarentena e
    `requires_human_review` são exigência de revisão. Nenhum dos quatro pode
    ser alcançado pelo UPDATE."""
    cond = lib._COND_APROVAR
    assert "IN ('', 'pendente')" in cond
    assert "quarantine_active" in cond and "= false" in cond
    assert "requires_human_review" in cond


def test_liberacao_exige_origem_oficial():
    """Documento de origem não oficial nunca é tocado — vai para curadoria."""
    assert lib._COND_ORIGEM in lib._COND_APROVAR
    assert lib._COND_ORIGEM in lib._COND_VIGENCIA
    assert "fonte ILIKE ANY(:origens)" in lib._COND_ORIGEM
    assert "chave_origem ILIKE ANY(:origens)" in lib._COND_ORIGEM


def test_liberacao_e_reversivel_por_marcador():
    """A trilha tem de distinguir o liberado por origem do conferido a mão."""
    assert lib.MARCADOR.startswith("liberacao_lote:")


def test_so_toca_versao_vigente_e_nao_excluida():
    for cond in (lib._COND_APROVAR, lib._COND_VIGENCIA):
        assert "deleted_at IS NULL" in cond
        assert "vigente = TRUE" in cond
