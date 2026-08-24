"""Todo workflow do GitHub Actions precisa ser CARREGÁVEL, não só ter o texto certo.

Auditoria de 22/08/2026 (Issue #1237), achado 28.

`.github/workflows/governanca.yml` estava com YAML inválido desde o commit
`bb04246a` (19/08). A linha era:

    run: echo "Autor: $AUTOR"

Escalar simples (o valor começa em `echo`, não em aspas), e um escalar simples
não pode conter `": "` — o parser lê `Autor:` como abertura de mapa e recusa o
arquivo inteiro. O GitHub confirmava: a API devolvia
`"name": ".github/workflows/governanca.yml"` — exibindo o CAMINHO no lugar do
nome, porque não conseguia ler nem a chave `name:`.

O que torna isso digno de trava: **já existia** um guarda desse arquivo,
`test_governanca_workflow.py`, que valida o conteúdo por regex e diz de
propósito "sem dependência de PyYAML". Ele conferia se os steps certos estavam
lá — e todos estavam. Um workflow que o GitHub se recusa a iniciar passava na
suíte inteira. Guarda que lê o texto sem nunca carregar o arquivo não sabe
dizer se o arquivo carrega.

Estratégia deliberada em duas camadas, para o teste nunca virar decorativo:

1. `test_nenhum_escalar_simples_com_dois_pontos` não depende de nada e pega
   exatamente a classe de erro que ocorreu. Roda sempre.
2. `test_todo_workflow_carrega` faz o parse completo (muito mais amplo) quando
   o PyYAML estiver importável. PyYAML hoje está presente por dependência
   transitiva, sem declaração em `requirements.txt` — por isso ele NÃO é o
   único guarda: se sumir, a camada 1 continua de pé.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted(
    p
    for p in (REPO_ROOT / ".github" / "workflows").iterdir()
    if p.suffix in (".yml", ".yaml")
)

# Uma linha `chave: valor` cujo valor NÃO começa por aspas, `|`, `>` ou `&`/`*`
# e que contém `": "` no meio. É o formato que o YAML recusa.
_CHAVE_VALOR = re.compile(r"^\s*[\w.-]+:\s+(?P<valor>\S.*)$")


def _valor_e_escalar_simples(valor: str) -> bool:
    return not valor.startswith(('"', "'", "|", ">", "&", "*", "{", "[", "#"))


def test_ha_workflows_para_conferir():
    """Sem isto, um glob vazio faria os dois testes abaixo passarem sozinhos."""
    assert len(WORKFLOWS) >= 10, f"esperava a pasta de workflows povoada, vi {len(WORKFLOWS)}"


def test_nenhum_escalar_simples_com_dois_pontos():
    """Camada 1 — sem dependência: a classe de erro exata do achado 28."""
    problemas: list[str] = []
    for arquivo in WORKFLOWS:
        for numero, linha in enumerate(
            arquivo.read_text(encoding="utf-8").splitlines(), start=1
        ):
            casou = _CHAVE_VALOR.match(linha)
            if not casou:
                continue
            valor = casou.group("valor")
            if not _valor_e_escalar_simples(valor):
                continue
            # `${{ ... }}` do GitHub pode conter ':' dentro da expressão sem
            # quebrar o parser, porque o YAML só vê o escalar completo; o que
            # quebra é ': ' (dois-pontos + espaço) fora de aspas.
            sem_expressao = re.sub(r"\$\{\{.*?\}\}", "", valor)
            if ": " in sem_expressao:
                problemas.append(
                    f"{arquivo.name}:{numero} escalar simples com ': ' — "
                    f"use bloco `|` ou aspas: {linha.strip()[:90]}"
                )
    assert not problemas, "YAML que o GitHub recusa:\n" + "\n".join(problemas)


def test_todo_workflow_carrega():
    """Camada 2 — parse completo; mais amplo, porém depende do PyYAML."""
    yaml = pytest.importorskip(
        "yaml", reason="PyYAML ausente; a camada 1 acima segue guardando"
    )
    falhas: list[str] = []
    for arquivo in WORKFLOWS:
        try:
            conteudo = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
        except Exception as erro:  # noqa: BLE001 — qualquer erro de parse conta
            falhas.append(f"{arquivo.name}: {str(erro).splitlines()[0]}")
            continue
        if not isinstance(conteudo, dict) or "jobs" not in conteudo:
            falhas.append(f"{arquivo.name}: carregou, mas sem a chave 'jobs'")
    assert not falhas, "workflow que não carrega:\n" + "\n".join(falhas)


def test_governanca_declara_nome_e_gatilho_de_pull_request():
    """O sintoma pelo qual o defeito apareceu: o GitHub exibia o CAMINHO como
    nome do workflow, sinal de que não lia a chave `name:`."""
    yaml = pytest.importorskip("yaml")
    caminho = REPO_ROOT / ".github" / "workflows" / "governanca.yml"
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))

    assert dados.get("name"), "governanca.yml precisa declarar `name:`"
    assert not str(dados["name"]).startswith(".github/"), (
        "nome igual ao caminho é o que o GitHub mostra quando o arquivo não carrega"
    )
    # `on:` sem aspas vira o booleano True em YAML 1.1 — os dois são aceitos.
    gatilhos = dados.get("on", dados.get(True)) or {}
    assert "pull_request" in gatilhos, (
        "a trava de governança só serve se disparar em pull_request"
    )
