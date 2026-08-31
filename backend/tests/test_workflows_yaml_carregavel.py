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
_DIR_WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# O GitHub Actions foi ARQUIVADO em 31/08 (commit `b77ff4c`): os workflows saíram
# para `docs/arquivo/ci/github-actions-legacy/` e o Woodpecker virou o CI oficial.
# O `.iterdir()` acima rodava no IMPORT do módulo, então a pasta ausente virava
# FileNotFoundError na COLETA — e erro de coleta aborta a suíte inteira, não só
# este arquivo. Era a `main` reprovando por um guarda cujo objeto o próprio
# repositório removeu de propósito.
#
# Não aponto para a pasta arquivada: workflow arquivado não é executado pelo
# GitHub, então "carrega ou não" deixou de ser uma pergunta com consequência.
# O guarda fica DORMENTE, não deletado — se o Actions voltar, a pasta reaparece
# e os três testes voltam a valer sozinhos, sem ninguém precisar lembrar.
WORKFLOWS = sorted(
    p for p in _DIR_WORKFLOWS.iterdir() if p.suffix in (".yml", ".yaml")
) if _DIR_WORKFLOWS.is_dir() else []

# O piso é "NÃO VAZIO", não um número: o README do arquivamento
# (docs/arquivo/ci/github-actions-legacy/2026-08-31/) manda restaurar "apenas um
# workflow mínimo" e depois migrar os demais "um a um". Um piso de 10 reprovaria
# a suíte exatamente durante esse experimento — o guarda bloquearia a
# recuperação que ele deveria acompanhar (achado do review do Codex no PR #1328).
pytestmark = pytest.mark.skipif(
    not WORKFLOWS,
    reason=("GitHub Actions arquivado em 31/08 (b77ff4c); Woodpecker é o CI "
            "oficial. Restaurado ao menos um workflow, estes testes revivem."),
)

# Uma linha `chave: valor` cujo valor NÃO começa por aspas, `|`, `>` ou `&`/`*`
# e que contém `": "` no meio. É o formato que o YAML recusa.
_CHAVE_VALOR = re.compile(r"^\s*[\w.-]+:\s+(?P<valor>\S.*)$")


def _valor_e_escalar_simples(valor: str) -> bool:
    return not valor.startswith(('"', "'", "|", ">", "&", "*", "{", "[", "#"))


def test_ha_workflows_para_conferir():
    """Sem isto, um glob vazio faria os dois testes abaixo passarem sozinhos.

    O propósito é anti-vácuo, e para isso basta NÃO ESTAR VAZIO — o piso de 10
    que existia aqui media outra coisa (o tamanho da pasta) e colidia com a
    restauração gradual prevista no README do arquivamento.
    """
    assert WORKFLOWS, "pasta de workflows existe mas está vazia"


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


@pytest.mark.skipif(
    not (_DIR_WORKFLOWS / "governanca.yml").is_file(),
    reason=("governanca.yml ainda não restaurado — a recuperação prevê voltar "
            "um workflow por vez, e este teste espera especificamente este"),
)
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
