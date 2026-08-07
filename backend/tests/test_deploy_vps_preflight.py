"""Contrato do pré-voo do workflow `Deploy VPS`.

O deploy automático morreu em 2026-08-06 e ficou morto por um dia inteiro sem
que o sintoma dissesse o porquê. Duas causas, e este arquivo trava as duas:

1. **`dubious ownership`.** O `actions/checkout` registra `safe.directory` num
   HOME temporário que ele desfaz no post-cleanup; as etapas `run:` seguintes
   voltam a ver um repositório de outro dono e qualquer comando git morre. O
   pré-voo começa por `git rev-parse HEAD` — reprovava no primeiro comando, sem
   chegar a checar nada.

2. **Falha muda.** As pré-condições eram `test` puros, que não imprimem nada ao
   falhar. O resumo do job saía com campos vazios e aparência de sucesso.

A suíte lê o YAML fonte (sem depender de PyYAML), no mesmo padrão de
`test_governanca_workflow.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "deploy-vps.yml"

PASSO_SAFE_DIRECTORY = "Confiar no workspace do runner para comandos git"
PASSO_PRE_VOO = "Confirmar SHA e runtime de produção"

# As seis pré-condições que o pré-voo verifica. Cada uma precisa de mensagem
# própria: uma reprovação sem nome custa uma rodada de deploy para diagnosticar.
PRE_CONDICOES = (
    "rev-parse",
    "/opt/ejc",
    "/opt/ejc/.env",
    "ejc_db",
    "python3",
    "rsync",
)


def _passos() -> dict[str, str]:
    """Mapa nome do step → corpo bruto, na ordem de declaração."""
    texto = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "\n    steps:" in texto, "deploy-vps.yml não declara `steps:` no job"
    corpo = texto.split("\n    steps:", 1)[1]
    blocos = re.split(r"\n      - name: ", corpo)[1:]
    passos: dict[str, str] = {}
    for bloco in blocos:
        nome, _, resto = bloco.partition("\n")
        passos[nome.strip()] = resto
    return passos


def _comandos(corpo: str) -> list[str]:
    """Linhas executáveis do step — sem comentários de YAML nem de shell.

    Os comentários deste workflow explicam por que o git morria; procurar `git`
    no texto bruto acharia a explicação e não o comando.
    """
    return [
        linha for linha in corpo.splitlines() if not linha.lstrip().startswith("#")
    ]


def test_workspace_e_marcado_como_safe_directory_antes_de_qualquer_git():
    """A exceção de propriedade precisa vir ANTES do primeiro comando git."""
    passos = _passos()
    assert PASSO_SAFE_DIRECTORY in passos, (
        "o passo que registra safe.directory sumiu — sem ele o pré-voo volta a "
        "morrer em 'detected dubious ownership' no primeiro `git rev-parse`"
    )
    corpo = passos[PASSO_SAFE_DIRECTORY]
    assert "safe.directory" in corpo and "$GITHUB_WORKSPACE" in corpo

    primeiro_git = next(
        (
            nome
            for nome, texto in passos.items()
            if any(re.match(r"\s*git\s+\w", linha) for linha in _comandos(texto))
        ),
        None,
    )
    assert primeiro_git == PASSO_SAFE_DIRECTORY, (
        f"o primeiro passo que executa git é '{primeiro_git}', e não o que "
        "registra safe.directory — a ordem é o que faz a correção valer"
    )


def test_cada_pre_condicao_do_pre_voo_se_identifica_ao_reprovar():
    """`test` puro não imprime nada; a falha precisa dizer qual checagem caiu."""
    corpo = _passos()[PASSO_PRE_VOO]
    assert "::error::" in corpo, (
        "o pré-voo não emite nenhum ::error:: — a falha volta a ser muda"
    )

    for marcador in PRE_CONDICOES:
        assert marcador in corpo, f"pré-condição '{marcador}' sumiu do pré-voo"

    # Uma chamada a `reprovar` por pré-condição, mais a do rev-parse que falha
    # por completo — 7 no total. Contar `::error::` não serve: ele aparece uma
    # única vez, dentro do helper.
    mensagens = re.findall(r'reprovar "([^"]+)"', corpo)
    assert len(mensagens) > len(PRE_CONDICOES), (
        f"{len(mensagens)} mensagens para {len(PRE_CONDICOES)} pré-condições — "
        "alguma reprova sem se identificar"
    )
    assert len(set(mensagens)) == len(mensagens), (
        "duas pré-condições compartilham a mesma mensagem — a reprovação deixa "
        "de dizer qual delas caiu"
    )


def test_pre_voo_verifica_todas_as_condicoes_antes_de_desistir():
    """Sem `set -e`: parar na primeira custa uma rodada de deploy por defeito."""
    corpo = _passos()[PASSO_PRE_VOO]
    assert "set -euo pipefail" not in corpo, (
        "`set -e` faz o pré-voo parar na primeira reprovação e esconder as "
        "demais; a correção depende de acumular os erros"
    )
    assert "set -uo pipefail" in corpo
    assert re.search(r"exit 1", corpo), "o pré-voo precisa reprovar o job ao fim"


def test_resumo_distingue_deploy_realizado_de_deploy_abortado():
    """Um sumário de campos vazios se parece com um sumário de sucesso."""
    corpo = _passos()["Resumo da implantação"]
    assert "job.status" in corpo, (
        "o resumo não consulta o status do job — volta a imprimir o mesmo texto "
        "tendo havido deploy ou não"
    )
    assert re.search(r"ABORTADO|não .*implantado|nada foi implantado", corpo, re.I)
