"""Colisão de `name` entre os seeds do catálogo de skills.

Achado do pente fino de 03/09. `seed_all` roda SEIS seeds de skill em ordem
fixa, e todos são idempotentes por `name` — quem chega primeiro vence e os
seguintes PULAM em silêncio, a menos que o nome esteja numa lista de
sobrescrita forçada.

`skills_ferramentas_seed` roda ANTES de `skills_expansion_seed` e sete nomes
colidiam. Nas sete, a versão do `expansion` é melhor por dois critérios
objetivos e verificáveis no próprio texto:

  • cita autoridade por FAMÍLIA com `[VALIDAR FONTE]` (7/7), em vez de CONGELAR
    número de artigo/súmula no prompt (`CPC art. 1.022`, `Súmula 479 STJ`,
    `CPP art. 396-A`, `CDC art. 42`), sem nada que force conferir vigência;
  • usa a ÁREA canônica (7/7), não o `juridico` genérico — e a área é o que
    alimenta `_AREA_SKILLS` (roteamento contextual) e `_AREA_TASK`.

Este teste não escolhe qual prompt é melhor: ele impede que a escolha seja
feita por ORDEM DE EXECUÇÃO, em silêncio. Colisão nova falha até que alguém
decida explicitamente — registrando em `_COLISOES_CONHECIDAS` (mantém o atual,
mas o seed passa a AVISAR), pondo em `_NOMES_FORCAR_ATUALIZACAO` (o expansion
vence, com backup do prompt anterior) ou renomeando uma das duas.

As sete NÃO foram forçadas de propósito. `_NOMES_FORCAR_ATUALIZACAO` está
restrito às duas skills da Issue #554 justamente "para não reescrever o prompt
de nenhuma outra skill que um administrador possa ter customizado" — trocar
prompt jurídico em produção é decisão do titular, não julgamento de qualidade
de quem escreve o seed.
"""
from __future__ import annotations

import re
from pathlib import Path

_SEEDS = Path(__file__).parents[1] / "app" / "seeds"


def _nomes_ferramentas() -> set[str]:
    texto = (_SEEDS / "skills_ferramentas_seed.py").read_text(encoding="utf-8")
    return set(re.findall(r'"name":\s*"([^"]+)"', texto))


def _nomes_expansion() -> set[str]:
    """Nomes do expansion: primeiro argumento posicional de cada `_skill(...)`."""
    texto = (_SEEDS / "skills_expansion_seed.py").read_text(encoding="utf-8")
    return set(re.findall(r"_skill\(\s*\n\s+\"([a-z0-9-]+)\"", texto))


def _decididas() -> set[str]:
    """Nomes com decisão EXPLÍCITA: forçados a atualizar OU registrados como
    colisão conhecida (mantém o atual, mas o seed avisa)."""
    texto = (_SEEDS / "skills_expansion_seed.py").read_text(encoding="utf-8")
    saida: set[str] = set()
    for marcador in ("_NOMES_FORCAR_ATUALIZACAO = {", "_COLISOES_CONHECIDAS = {"):
        bloco = texto.split(marcador, 1)[1].split("}", 1)[0]
        saida |= set(re.findall(r'"([a-z0-9-]+)"', bloco))
    return saida


def test_toda_colisao_entre_seeds_e_uma_decisao_explicita():
    colisoes = _nomes_ferramentas() & _nomes_expansion()
    nao_decididas = sorted(colisoes - _decididas())
    assert not nao_decididas, (
        "Nome(s) presente(s) em skills_ferramentas_seed E skills_expansion_seed "
        "sem decisão explícita:\n  " + "\n  ".join(nao_decididas)
        + "\n\nComo `ferramentas` roda ANTES em seed_all e ambos são "
        "idempotentes por `name`, a versão do expansion seria DESCARTADA em "
        "silêncio. Decida: registre em _COLISOES_CONHECIDAS (mantém o atual e o "
        "seed avisa), ponha em _NOMES_FORCAR_ATUALIZACAO (o expansion vence, "
        "com backup) ou renomeie uma delas."
    )


def test_as_sete_colisoes_conhecidas_estao_decididas():
    """Guarda do próprio teste: se a extração de nomes quebrar (mudou o formato
    do seed), o teste acima passaria VAZIO e daria falsa cobertura."""
    esperadas = {
        "consumidor-bancario", "contraponto-penal", "detector-contradicoes",
        "embargos-declaracao", "raio-x-cnis", "raio-x-processual",
        "resposta-acusacao",
    }
    colisoes = _nomes_ferramentas() & _nomes_expansion()
    assert esperadas <= colisoes, (
        "A extração de nomes parou de enxergar as colisões conhecidas — o "
        "formato de algum seed mudou e este contrato virou letra morta."
    )
    assert esperadas <= _decididas()
    # E NÃO foram forçadas: a proteção da Issue #554 continua valendo.
    texto = (_SEEDS / "skills_expansion_seed.py").read_text(encoding="utf-8")
    forcados = set(re.findall(
        r'"([a-z0-9-]+)"',
        texto.split("_NOMES_FORCAR_ATUALIZACAO = {", 1)[1].split("}", 1)[0]))
    assert not (esperadas & forcados), (
        "As sete colisões NÃO devem ser forçadas: sobrescrever prompt jurídico "
        "de produção, possivelmente customizado, é decisão do titular."
    )


def test_o_expansion_nao_congela_autoridade_nas_colisoes():
    """O critério que justificou a decisão: nas sete, o expansion pede
    validação de fonte em vez de fixar número de artigo/súmula."""
    texto = (_SEEDS / "skills_expansion_seed.py").read_text(encoding="utf-8")
    for nome in ("consumidor-bancario", "embargos-declaracao", "resposta-acusacao"):
        i = texto.index(f'"{nome}",')
        bloco = texto[i:i + 1400].split("    _skill(")[0]
        assert "VALIDAR FONTE" in bloco, (
            f"{nome}: o prompt do expansion perdeu o marcador [VALIDAR FONTE] — "
            "sem ele, a razão para preferi-lo ao de ferramentas deixa de valer."
        )
