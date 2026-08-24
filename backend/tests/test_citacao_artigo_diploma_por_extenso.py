# -*- coding: utf-8 -*-
"""O gate antialucinação só bloqueia a citação que o extrator ENXERGA.

Achado da auditoria funcional de 22/08/2026 (Issue #1237), na verificação das
proteções não negociáveis do CLAUDE.md (regra 4: "jamais remover HITL ou o
citation gate"). Um gate cego não precisa ser removido — ele já não age.

`_RE_ARTIGO` exigia SIGLA do diploma e número de até 4 dígitos sem separador.
Medido no HEAD anterior, 5 de 12 formas de citar passavam sem serem sequer
extraídas — e a forma cega é justamente a mais natural num texto jurídico:

    'artigo 927 do Código Civil'              -> []
    'artigo 300 do Código de Processo Civil'  -> []
    'artigo 5º da Constituição Federal'       -> []
    'art. 1.234 do CPC'                       -> []   (separador de milhar)
    'artigo 42.789 do Código Civil'           -> []   (FABRICADO — e passava)

O artigo 927 do CC é a cláusula geral de responsabilidade civil: se a forma
mais citada do direito brasileiro não é extraída, o gate não estava protegendo
peça nenhuma contra citação inventada por extenso.

Dois cuidados que estes testes travam junto com a correção:

1. **Normalização do diploma.** `citation_check._restringir_ao_diploma` procura
   a chave em `_SLUG_POR_DIPLOMA`, que só conhece siglas. Extrair "Código Civil"
   sem normalizar para "CC" faria o lookup falhar e a citação LEGÍTIMA virar
   inconfirmável — que, pela política P0.1 (fail-closed), BLOQUEIA a aprovação.
   Corrigir a cegueira criando bloqueio indevido seria trocar um defeito por
   outro.
2. **Janela sem ponto.** A janela entre número e diploma continua proibindo
   ponto de propósito: aceitá-lo faz o padrão atravessar fim de frase e parear
   artigo de uma frase com diploma de outra.
"""
from __future__ import annotations

import pytest

from app.services.verificador_jurisprudencia import analisar_texto


def _artigos(texto: str) -> list[tuple[str, str]]:
    return [
        (c.get("numero"), c.get("diploma"))
        for c in analisar_texto(texto)
        if c.get("tipo") == "artigo"
    ]


@pytest.mark.parametrize(
    "texto,numero,diploma",
    [
        # diploma por extenso — nenhum destes era extraído
        ("Conforme o artigo 927 do Código Civil.", "927", "CC"),
        ("Conforme o artigo 927 do Codigo Civil.", "927", "CC"),  # sem acento
        ("Conforme o artigo 300 do Código de Processo Civil.", "300", "CPC"),
        ("Conforme o artigo 5º da Constituição Federal.", "5", "CF"),
        ("Nos termos do artigo 5º da Constituição da República.", "5", "CF"),
        ("Conforme o artigo 477 da Consolidação das Leis do Trabalho.", "477", "CLT"),
        ("Conforme o artigo 14 do Código de Defesa do Consumidor.", "14", "CDC"),
        ("Responde pelo artigo 121 do Código Penal.", "121", "CP"),
        ("Conforme o artigo 155 do Código de Processo Penal.", "155", "CPP"),
        ("Nos termos do artigo 150 do Código Tributário Nacional.", "150", "CTN"),
        # separador de milhar — o número vive DENTRO do grupo, não na janela
        ("Aplica-se o art. 1.234 do CPC.", "1234", "CPC"),
        ("Conforme o artigo 2.035 do Código Civil.", "2035", "CC"),
        # o que já funcionava não pode ter regredido
        ("Aplica-se o art. 927 do CC.", "927", "CC"),
        ("Aplica-se o art. 1072 do CPC.", "1072", "CPC"),
        ("Art. 5º, inciso II, da CF.", "5", "CF"),
    ],
)
def test_artigo_e_extraido_e_diploma_normalizado(texto, numero, diploma):
    """Extraído E com a sigla que o lookup do RAG entende."""
    assert _artigos(texto) == [(numero, diploma)], f"não extraído/normalizado: {texto!r}"


def test_artigo_fabricado_por_extenso_e_extraido():
    """O ponto do gate: número inventado tem de CHEGAR à verificação.

    Antes ele nem era extraído — ou seja, uma peça citando 'artigo 42.789 do
    Código Civil' seguia adiante sem que o gate soubesse que havia uma citação
    ali para conferir.
    """
    assert _artigos("Conforme o artigo 42.789 do Código Civil.") == [("42789", "CC")]


def test_lei_numerada_continua_passando_crua():
    """`Lei 8.078/90` não vai para `_DIPLOMA_CANONICO`: quem a resolve é o ramo
    `startswith('lei')` de `_restringir_ao_diploma`, que faz `.lower()` antes."""
    assert _artigos("Nos termos do art. 20 da Lei 8.078/90.") == [("20", "LEI 8.078/90")]


@pytest.mark.parametrize(
    "texto",
    [
        "O contrato tem 927 clausulas.",
        "A parte juntou 300 documentos ao processo.",
        "A reuniao ficou marcada para as 14 horas.",
        "O artigo do jornal falava do caso.",
    ],
)
def test_nao_inventa_citacao_onde_nao_ha(texto):
    """Ampliar a extração não pode fabricar citação: cada falso positivo vira
    uma verificação que pode bloquear peça legítima (política P0.1)."""
    assert _artigos(texto) == []


@pytest.mark.parametrize(
    "texto",
    [
        "Vendeu o art. 42 ontem. O Codigo Civil regula a materia.",
        "Cumpriu o art. 15. O CPC exige intimacao previa.",
        "Revisamos o art. 88. A Constituição Federal garante o contraditorio.",
    ],
)
def test_nao_atravessa_fim_de_frase(texto):
    """A janela entre número e diploma proíbe ponto justamente para isto.

    Parear o artigo de uma frase com o diploma da seguinte produziria citação
    inexistente e, sendo inconfirmável, bloquearia a peça sem motivo real.
    """
    assert _artigos(texto) == []
