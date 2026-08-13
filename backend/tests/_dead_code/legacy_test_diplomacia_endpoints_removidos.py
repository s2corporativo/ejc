"""Bloco 4 — os dois endpoints removidos por decisão do escritório não voltam.

`/diplomacia-v3/dossie-pressao` e `/diplomacia-v3/analisar-magistrado` foram
removidos por RISCO, não por defeito técnico: um "dossiê de pressão" e uma
"análise de magistrado" num sistema de escritório de advocacia são indefensáveis
se expostos numa perícia ou numa representação — independentemente do que o
código faça. Nenhuma tela do sistema os chamava.

Código removido tende a voltar: alguém acha a função órfã, acha útil, e
reintroduz sem conhecer a decisão. Estes testes existem para que a
reintrodução seja uma escolha consciente, e não um acidente de refactor.

O que NÃO foi removido: `/diplomacia-v3/calcular-acordo`. É matemática
financeira legítima (ponto de equilíbrio de acordo com Selic real do BCB) e
está em uso pela tela `CalculadoraAcordo`. O plano nomeava só os outros dois.
"""
from pathlib import Path


def _fonte(caminho: str) -> str:
    return (Path(__file__).parents[1] / caminho).read_text(encoding="utf-8")


def test_endpoints_de_risco_nao_existem_mais_no_router():
    src = _fonte("app/routers/diplomacia_v3.py")
    assert '@router.post("/dossie-pressao"' not in src
    assert '@router.post("/analisar-magistrado"' not in src
    assert "async def dossie_pressao(" not in src
    assert "async def analisar_magistrado(" not in src


def test_calculadora_de_acordo_permanece():
    """A remoção não podia levar junto o que está em uso."""
    src = _fonte("app/routers/diplomacia_v3.py")
    assert '@router.post("/calcular-acordo")' in src
    assert "calcular_ponto_equilibrio" in src


def test_decisao_esta_registrada_no_proprio_arquivo():
    """Quem abrir o arquivo precisa encontrar o porquê, não só a ausência."""
    src = _fonte("app/routers/diplomacia_v3.py")
    assert "REMOÇÃO" in src
    assert "decisão do escritório" in src
    assert "decisão escrita do titular" in src


def test_o_shim_de_sentimento_de_magistrado_ficou_sem_chamador_no_router():
    """O serviço continua no repositório, mas nenhuma ROTA o expõe.

    Deixá-lo importado seria manter a porta fechada com a chave na fechadura.
    """
    src = _fonte("app/routers/diplomacia_v3.py")
    assert "sentimento_magistrado" not in src
    assert "sentimento_ia" not in src


def test_a_trava_de_rotas_declara_a_remocao():
    """Sumiço de rota tem de ser explícito, igual ao surgimento."""
    src = _fonte("tests/test_rotas_registro_explicito.py")
    assert "REMOCOES_INTENCIONAIS" in src
    assert '("/api/diplomacia-v3/dossie-pressao", "POST")' in src
    assert '("/api/diplomacia-v3/analisar-magistrado", "POST")' in src
