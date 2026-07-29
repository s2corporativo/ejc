"""Regressão do gate de governança (.github/workflows/governanca.yml).

O workflow é um check obrigatório de merge: uma regressão no predicado `if:`
ou na estrutura dos steps não quebra nenhum teste de aplicação, passa pelo
YAML válido e só aparece quando um PR real é reprovado — ou, pior, quando um
PR que deveria ser reprovado passa. Estes testes fixam o contrato.

Contexto (PR #533): a trava de descrição reprovava todos os PRs do dependabot,
cuja descrição é gerada pela ferramenta e não traz as seções do template. A
correção isenta bots de uma allowlist fechada. Os dois caminhos críticos
verificados aqui são:

  1. a isenção existe e é restrita — bot fora da allowlist continua cobrado;
  2. a isenção é cirúrgica — nenhuma outra trava ganhou condicional.

Sem dependência de PyYAML: o pacote não está declarado em requirements.txt
(vem transitivo) e nenhum outro teste do repositório o importa. O parsing é
por indentação, determinístico para a estrutura deste arquivo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "governanca.yml"
)

STEP_DESCRICAO = "Descricao do PR preenchida"

# Travas que valem para TODO PR, bot inclusive. Nenhuma pode ganhar `if:`.
STEPS_INCONDICIONAIS = (
    "Arquivos alterados no PR",
    "Migration exige reserva registrada",
    "Ausencia de segredo versionado",
    "Alteracao de governanca isolada",
    "Branch nao e main",
)


def _steps() -> dict[str, str]:
    """Mapeia nome do step -> corpo bruto, fatiando por `- name:` em 6 espaços."""
    texto = WORKFLOW.read_text(encoding="utf-8")
    marcador = re.compile(r"^      - name: (.+)$", re.MULTILINE)
    achados = list(marcador.finditer(texto))
    assert achados, "nenhum step nomeado encontrado — estrutura do workflow mudou"

    blocos: dict[str, str] = {}
    for i, m in enumerate(achados):
        fim = achados[i + 1].start() if i + 1 < len(achados) else len(texto)
        blocos[m.group(1).strip()] = texto[m.start() : fim]
    return blocos


def _condicao(corpo: str) -> str:
    """Extrai o `if:` do step (8 espaços de indentação), vazio se não houver."""
    m = re.search(r"^        if:(.*?)(?=^        [a-z_-]+:|\Z)", corpo, re.M | re.S)
    return " ".join(m.group(1).split()) if m else ""


def test_workflow_existe():
    assert WORKFLOW.is_file(), f"workflow ausente: {WORKFLOW}"


def test_todos_os_steps_esperados_estao_presentes():
    presentes = _steps()
    for nome in (STEP_DESCRICAO, *STEPS_INCONDICIONAIS):
        assert nome in presentes, f"step removido ou renomeado: {nome!r}"


@pytest.mark.parametrize("nome", STEPS_INCONDICIONAIS)
def test_travas_universais_nao_tem_condicional(nome: str):
    """Migration, segredo, escopo e branch valem para bot como para humano.

    Se alguma ganhar `if:`, um PR automatizado poderá versionar segredo ou
    criar migration sem reserva sem que nada reaja.
    """
    condicao = _condicao(_steps()[nome])
    assert not condicao, f"step {nome!r} passou a ser condicional: {condicao!r}"


def test_trava_de_descricao_isenta_bot():
    """O caminho que motivou a correção: bot da allowlist não é cobrado."""
    condicao = _condicao(_steps()[STEP_DESCRICAO])
    assert condicao, "a trava de descrição perdeu a isenção de bot"
    assert "dependabot[bot]" in condicao, (
        "dependabot saiu da allowlist — seus PRs voltarão a ser reprovados por "
        "não preencherem um template que a ferramenta não sabe preencher"
    )
    assert "github.event.pull_request.user.login" in condicao, (
        "a isenção deixou de olhar o autor do PR"
    )


def test_isencao_e_allowlist_fechada_e_nao_qualquer_bot():
    """Impede o alargamento para `qualquer bot`.

    Um GitHub App arbitrário instalado no repositório não pode abrir PR que
    escapa do gate de Issue vinculada. A isenção precisa nomear quem isenta.
    """
    condicao = _condicao(_steps()[STEP_DESCRICAO])
    assert "contains(" in condicao and "fromJSON(" in condicao, (
        "a isenção deixou de ser allowlist explícita"
    )
    for aberto in ("user.type != 'Bot'", "endsWith(", "'[bot]')"):
        assert aberto not in condicao, (
            f"isenção alargada para qualquer bot via {aberto!r}: "
            "qualquer App instalado escaparia do gate de Issue vinculada"
        )


def test_trava_de_descricao_cobra_issue_e_secoes_do_template():
    """As exigências em si continuam no corpo do step."""
    corpo = _steps()[STEP_DESCRICAO]
    assert "#[0-9]+" in corpo, "exigência de Issue vinculada removida"
    for secao in (
        "Issue vinculada",
        "Solução",
        "Testes executados",
        "Riscos residuais",
        "Rollback",
    ):
        assert secao in corpo, f"seção deixou de ser exigida: {secao!r}"


def test_arquivo_temporario_nao_usa_tmp_compartilhado():
    """Regressão do defeito corrigido em b44128db.

    O runner é self-hosted e divide o VPS: `/tmp/alterados.txt` deixado por
    outra execução não pode ser sobrescrito (sticky bit) e o job morre com
    "Permission denied" a partir da segunda execução.
    """
    # Só o código conta: o comentário que documenta o defeito cita o caminho
    # antigo de propósito, e não é uso.
    codigo = "\n".join(
        linha
        for linha in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not linha.lstrip().startswith("#")
    )
    assert "/tmp/alterados.txt" not in codigo, (
        "voltou a usar /tmp compartilhado; use $RUNNER_TEMP"
    )
    assert "$RUNNER_TEMP/alterados.txt" in codigo
