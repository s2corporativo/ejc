"""Deduplicação de base processual (app/services/saneamento/dedup.py).

Contrato coberto (regras de negócio inegociáveis do módulo de saneamento):
  - duplicata real é colapsada mantendo o registro mais completo;
  - mesmo processo em graus distintos NUNCA é fundido, só relacionado;
  - número que falha no dígito verificador é ERRO DE DIGITAÇÃO — vai para a
    fila de exceção, nunca vira duplicata;
  - conexos de numeração distinta são só SUGERIDOS, nunca fundidos.

Portado do pacote de referência ejc-saneamento/tests/test_saneamento.py,
adaptado para usar validators_service.validar_cnj (fonte canônica única do
projeto para o DV — Res. CNJ 65/2008) em vez de uma reimplementação própria.
Sem chamada de rede.
"""
from __future__ import annotations

from app.services.saneamento.dedup import RegistroProcesso, deduplicar, sugerir_conexos
from app.services.validators_service import validar_cnj

# Número publicado pelo próprio CNJ no tutorial da API Pública — âncora de verdade.
NUM_CNJ_OFICIAL = "00008323520184013202"


def test_numero_oficial_do_cnj_valida():
    """Âncora: o número usado em todo o resto do arquivo é de fato válido."""
    assert validar_cnj(NUM_CNJ_OFICIAL)


def _reg(id_, numero, grau=None, **dados):
    return RegistroProcesso(id_interno=id_, numero=numero, grau=grau, dados=dados)


def test_duplicata_real_e_colapsada_mantendo_o_mais_completo():
    r = deduplicar([
        _reg("a", NUM_CNJ_OFICIAL, grau="G1"),
        _reg("b", "0000832-35.2018.4.01.3202", grau="G1", classe="Procedimento", uf="MG"),
    ])
    assert len(r.duplicatas) == 1
    grupo = r.duplicatas[0]
    assert grupo.principal.id_interno == "b"       # mais campos preenchidos
    assert [x.id_interno for x in grupo.absorvidos] == ["a"]
    assert not r.graus_relacionados


def test_mesmo_processo_em_graus_distintos_nao_e_duplicata():
    r = deduplicar([
        _reg("a", NUM_CNJ_OFICIAL, grau="G1"),
        _reg("b", NUM_CNJ_OFICIAL, grau="G2"),
    ])
    assert not r.duplicatas
    assert NUM_CNJ_OFICIAL in r.graus_relacionados
    assert len(r.graus_relacionados[NUM_CNJ_OFICIAL]) == 2


def test_numero_invalido_vai_para_excecao_e_nao_para_duplicata():
    r = deduplicar([
        _reg("a", NUM_CNJ_OFICIAL),
        _reg("b", "00008323520184013203"),  # DV errado
        _reg("c", ""),
    ])
    assert len(r.excecoes) == 2
    assert {e.registro.id_interno for e in r.excecoes} == {"b", "c"}
    assert len(r.unicos) == 1


def test_numero_com_quantidade_errada_de_digitos_vai_para_excecao():
    r = deduplicar([_reg("a", "0000832352018401320")])  # 19 dígitos
    assert len(r.excecoes) == 1
    assert "inválido" in r.excecoes[0].motivo


def test_lixo_com_digitos_validos_embutidos_vai_para_excecao_nao_para_grupo():
    """Achado de revisão de código: validar ANTES de normalizar. Uma string
    com lixo (letras) em volta de 20 dígitos que por acaso formam um CNJ
    válido não pode ser tratada como se fosse aquele número — validar_cnj
    rejeita porque o bruto não é só-dígitos nem a máscara oficial."""
    lixo = f"abc{NUM_CNJ_OFICIAL}"
    r = deduplicar([_reg("a", lixo), _reg("b", NUM_CNJ_OFICIAL)])
    assert {e.registro.id_interno for e in r.excecoes} == {"a"}
    assert len(r.unicos) == 1
    assert r.unicos[0].id_interno == "b"


def test_grau_desconhecido_ao_lado_de_grau_conhecido_nao_e_duplicata():
    """Achado de revisão de código: um registro sem grau informado ao lado
    de outro com grau conhecido pode ser, precisamente, o grau que falta
    descobrir — nunca funde, regra "multi-grau nunca funde"."""
    r = deduplicar([
        _reg("a", NUM_CNJ_OFICIAL, grau="G1"),
        _reg("b", NUM_CNJ_OFICIAL, grau=None),
    ])
    assert not r.duplicatas
    assert NUM_CNJ_OFICIAL in r.graus_relacionados


def test_dois_registros_ambos_sem_grau_informado_e_duplicata():
    """Sem NENHUM indício de graus distintos (os dois vieram sem grau), o
    caso conservador continua sendo duplicata real — não há sinal de
    multi-grau para justificar não fundir."""
    r = deduplicar([
        _reg("a", NUM_CNJ_OFICIAL, grau=None),
        _reg("b", NUM_CNJ_OFICIAL, grau=None, extra="x"),
    ])
    assert len(r.duplicatas) == 1
    assert not r.graus_relacionados


def test_desempate_e_deterministico():
    a = deduplicar([_reg("z", NUM_CNJ_OFICIAL), _reg("a", NUM_CNJ_OFICIAL)])
    b = deduplicar([_reg("a", NUM_CNJ_OFICIAL), _reg("z", NUM_CNJ_OFICIAL)])
    assert a.duplicatas[0].principal.id_interno == b.duplicatas[0].principal.id_interno


def test_conexos_sao_apenas_sugeridos():
    outro = "00009995220184013202"  # mesmo segmento/tribunal/origem, sequencial distinto
    assert validar_cnj(outro)  # DV correto — teste não usa número inválido por acidente
    pares = sugerir_conexos([
        _reg("a", NUM_CNJ_OFICIAL, orgao_julgador="1234", partes_hash="h1"),
        _reg("b", outro, orgao_julgador="1234", partes_hash="h1"),
    ])
    assert len(pares) == 1
    assert "mesmo órgão julgador" in pares[0][2]


def test_conexos_exigem_orgao_e_partes_preenchidos():
    pares = sugerir_conexos([
        _reg("a", NUM_CNJ_OFICIAL, orgao_julgador="1234"),  # sem partes_hash
        _reg("b", "00009995220184013202", orgao_julgador="1234"),
    ])
    assert pares == []


def test_conexos_nao_sugere_o_mesmo_numero_como_par_de_si_mesmo():
    pares = sugerir_conexos([
        _reg("a", NUM_CNJ_OFICIAL, orgao_julgador="1234", partes_hash="h1"),
        _reg("b", NUM_CNJ_OFICIAL, orgao_julgador="1234", partes_hash="h1"),
    ])
    assert pares == []


def test_resumo_conta_cada_categoria():
    r = deduplicar([
        _reg("a", NUM_CNJ_OFICIAL, grau="G1"),
        _reg("b", NUM_CNJ_OFICIAL, grau="G1"),  # duplicata de a
        _reg("c", "00009995220184013202", grau="G1"),  # único
        _reg("d", ""),  # exceção
    ])
    resumo = r.resumo()
    assert resumo["grupos_duplicados"] == 1
    assert resumo["registros_absorviveis"] == 1
    assert resumo["unicos"] == 1
    assert resumo["excecoes"] == 1
