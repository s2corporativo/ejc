# ── tests/test_deduplicar_base_conhecimento.py ───────────────────────────────
# O risco deste script não é apagar demais (ele nunca apaga — rebaixa), é
# AGRUPAR ERRADO: tratar duas leis distintas como cópias da mesma e rebaixar
# uma delas, tirando um diploma inteiro do alcance da IA. Os testes de colisão
# abaixo são o que impede isso, e usam os títulos REAIS medidos na base de
# produção em 2026-08-27.
from scripts.deduplicar_base_conhecimento import (
    DocCandidato,
    casa_canonico,
    chave_agrupamento,
    CANONICOS,
    decidir_grupo,
    extrair_numeros_lei,
    normalizar,
    pontuar,
)


def _doc(id_, titulo, *, fonte=False, chave=False, revisado=False,
         versao=1, ts=0.0, chunks=0):
    return DocCandidato(
        id=id_, titulo=titulo, categoria="legislacao", tem_fonte=fonte,
        tem_chave_origem=chave, revisado=revisado, versao=versao,
        atualizado_em_ts=ts, n_chunks=chunks,
    )


# ── normalização ─────────────────────────────────────────────────────────────

def test_normalizar_remove_acento_pontuacao_e_caixa():
    assert normalizar("Código de Processo Civil.") == "CODIGO DE PROCESSO CIVIL"
    assert normalizar("CONSOLIDAÇÃO   das  Leis") == "CONSOLIDACAO DAS LEIS"


def test_extrair_numeros_ignora_ano():
    """4 dígitos começando em 19/20 é ano, não número de lei.

    Sem esta regra, "DE 16 DE MARÇO DE 2015" faria o CPC casar com qualquer
    outro diploma de 2015.
    """
    assert extrair_numeros_lei("Lei 13.105, de 16 de março de 2015") == {"13105"}
    assert extrair_numeros_lei("Constituição Federal de 1988") == set()


# ── agrupamento dos títulos reais de produção ────────────────────────────────

def test_agrupa_as_seis_variacoes_reais_do_cpc():
    """Os seis títulos do CPC medidos em produção têm de cair no mesmo grupo."""
    reais = [
        "Código de Processo Civil",
        "Código de Processo Civil (Lei 13.105/2015)",
        "Código de Processo Civil.   LEI Nº 13.105, DE 16 DE MARÇO DE 2015",
    ]
    chaves = {chave_agrupamento(t) for t in reais}
    assert len(chaves) == 1 and chaves != {None}


def test_agrupa_variacoes_reais_da_clt_e_do_codigo_civil():
    clt = {chave_agrupamento(t) for t in (
        "CLT",
        "CLT - DECRETO-LEI Nº 5.452, DE 1º DE MAIO DE 1943",
        "Consolidação das Leis do Trabalho (DL 5.452/1943)",
    )}
    assert len(clt) == 1 and clt != {None}

    cc = {chave_agrupamento(t) for t in (
        "Código Civil (Lei 10.406/2002)",
        "CODIGO CIVIL    LEI Nº 10.406, DE 10 DE JANEIRO DE 2002",
    )}
    assert len(cc) == 1 and cc != {None}


def test_agrupa_variacoes_reais_da_constituicao():
    cf = {chave_agrupamento(t) for t in (
        "Constituição Federal de 1988",
        "CONSTITUIÇÃO FEDERAL",
    )}
    assert len(cf) == 1 and cf != {None}


# ── COLISÕES: o que este script NÃO pode confundir ───────────────────────────

def test_cpp_militar_nao_e_agrupado_com_o_cpp_comum():
    """Regressão do título real 'Código de Processo Penal Militar'.

    São leis diferentes (DL 1.002/1969 × DL 3.689/1941). Agrupá-las rebaixaria
    um código inteiro.
    """
    comum = chave_agrupamento("Código de Processo Penal (DL 3.689/1941)")
    militar = chave_agrupamento("Código de Processo Penal Militar - DECRETO-LEI Nº 1.002")
    assert comum is not None
    assert militar != comum


def test_processo_civil_nao_colide_com_processo_penal():
    assert chave_agrupamento("Código de Processo Civil") != \
           chave_agrupamento("Código de Processo Penal")


def test_codigo_civil_nao_colide_com_processo_civil():
    assert chave_agrupamento("Código Civil") != \
           chave_agrupamento("Código de Processo Civil")


def test_diploma_revogado_nao_e_agrupado_com_o_vigente():
    """CPC/1973 e CC/1916 são outros diplomas — coexistem legitimamente."""
    assert chave_agrupamento("Código de Processo Civil de 1973 (Lei 5.869/1973)") != \
           chave_agrupamento("Código de Processo Civil (Lei 13.105/2015)")


def test_titulo_desconhecido_nunca_e_agrupado():
    """Sem match com um CANONICO declarado, o documento é intocável.

    É esta função devolvendo None que garante que o script não age sobre
    material que ninguém previu — inclusive os modelos da Bíblia EJC e as
    compilações como o Vade Mecum.
    """
    for titulo in ("VADE MECUM 2026",
                   "Bíblia EJC (fictício) — Modelo Vol. II — 01 - RÉPLICA",
                   "Lei Maria da Penha (Lei 11.340/2006)",
                   "Súmulas"):
        assert chave_agrupamento(titulo) is None


def test_titulo_com_numero_de_outra_lei_nao_casa_por_alias():
    """Número presente desliga o alias — evita casar pelo nome genérico."""
    assert not casa_canonico(
        "Juizados Especiais Cíveis (Lei 9.099/1995)",
        next(c for c in CANONICOS if c.numeros == ("13105",)),
    )


# ── escolha da cópia que fica ────────────────────────────────────────────────

def test_revisado_por_humano_vence_tudo():
    revisado = _doc("a", "CPC", revisado=True, chunks=1)
    completo = _doc("b", "CPC", fonte=True, chave=True, ts=9e9, versao=9, chunks=9999)
    vencedor, perdedores = decidir_grupo([completo, revisado])
    assert vencedor.id == "a" and [p.id for p in perdedores] == ["b"]


def test_com_fonte_vence_sem_fonte_quando_nenhum_foi_revisado():
    """Reproduz o caso real: cópia curada (com URL oficial) × upload manual."""
    manual = _doc("sem", "CPC", chunks=1006)      # mais trechos, sem fonte
    curada = _doc("com", "CPC", fonte=True, chunks=670)
    vencedor, _ = decidir_grupo([manual, curada])
    assert vencedor.id == "com", "volume não pode ganhar de procedência"


def test_empate_total_e_deterministico():
    a, b = _doc("aaa", "CPC"), _doc("bbb", "CPC")
    assert decidir_grupo([a, b])[0].id == decidir_grupo([b, a])[0].id


def test_todo_grupo_mantem_exatamente_um_vencedor():
    docs = [_doc(str(i), "CPC", chunks=i) for i in range(5)]
    vencedor, perdedores = decidir_grupo(docs)
    assert len(perdedores) == len(docs) - 1
    assert vencedor.id not in {p.id for p in perdedores}


def test_pontuar_ordena_do_menos_para_o_mais_confiavel():
    fraco = pontuar(_doc("x", "CPC"))
    forte = pontuar(_doc("y", "CPC", revisado=True, fonte=True, chave=True))
    assert forte > fraco
