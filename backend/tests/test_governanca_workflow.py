"""Contrato das travas de governança do EJC.

A suíte usa o YAML fonte, sem dependência de PyYAML, e protege:
- a exceção fechada do Dependabot apenas nos steps que dependem do corpo do PR;
- as travas incondicionais de integridade (migration, segredo e branch);
- a Definition of Done mínima;
- a revisão de segurança documentada para superfícies sensíveis;
- a classificação do escopo de governança.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "governanca.yml"
DOC_PATH = REPO_ROOT / "docs" / "GOVERNANCA_IA.md"

# Travas que precisam continuar valendo para qualquer PR, inclusive Dependabot.
STEPS_SEM_EXCECAO = (
    "Migration exige reserva registrada",
    "Ausencia de segredo versionado",
    "Alteracao de governanca isolada",
    "Branch nao e main",
)

# Dependabot não preenche o template humano; apenas estes steps podem usar a
# exceção fechada e dupla (autor do PR + ator do evento).
STEPS_COM_EXCECAO_DEPENDABOT = (
    "Descricao do PR preenchida",
    "Definition of Done minima marcada",
    "Revisao de seguranca documentada para superficie sensivel",
)


def _steps() -> dict[str, str]:
    """Mapa nome do step → corpo bruto do step (regex sobre o YAML fonte)."""
    texto = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "\n    steps:" in texto, "governanca.yml não declara `steps:` no job"
    job = texto.split("\n    steps:", 1)[1]
    blocos = re.split(r"\n      - name: ", job)[1:]
    passos: dict[str, str] = {}
    for bloco in blocos:
        nome, _, resto = bloco.partition("\n")
        passos[nome.strip()] = resto
    return passos


def _condicao_if(nome_step: str) -> str:
    """Extrai a condição `if:` do step humano indicado."""
    bloco = _steps()[nome_step]
    m = re.search(
        r"\n        if:\s*(?:>-\s*\n(.*?)|\$\{\{(.*?)\}\})\n        env:",
        bloco,
        re.S,
    )
    assert m, (
        f"step {nome_step!r} não tem condição if: no formato esperado "
        "imediatamente antes de `env:`"
    )
    return m.group(1) or m.group(2)


def _allowlist_workflow(nome_step: str) -> list[str]:
    condicao = _condicao_if(nome_step)
    achados = re.findall(r"fromJSON\('(\[[^']*\])'\)", condicao)
    assert achados, (
        f"step {nome_step!r} não usa contains(fromJSON('[...]'), autor) "
        "na condição if: — isenção não implementada como allowlist fechada"
    )
    listas = [json.loads(bruto) for bruto in achados]
    assert all(lista == listas[0] for lista in listas), (
        "as allowlists da condição if: divergem entre autor do PR e "
        f"github.actor: {listas!r}"
    )
    return listas[0]


def _allowlist_doc() -> list[str]:
    texto = DOC_PATH.read_text(encoding="utf-8")
    assert "## 12. Exceção de bot de manutenção de dependências" in texto, (
        "docs/GOVERNANCA_IA.md não tem a seção 12 com a exceção de bot"
    )
    secao = texto.split("## 12. Exceção de bot de manutenção de dependências", 1)[1]
    secao = secao.split("\n## 13.", 1)[0]
    m = re.search(r"```json\s*(\[.*?\])\s*```", secao, re.S)
    assert m, "seção 12 de docs/GOVERNANCA_IA.md não tem bloco ```json``` com a allowlist"
    return json.loads(m.group(1))


# ── Estrutura básica do workflow ──────────────────────────────────────────────


def test_workflow_tem_todos_os_steps_esperados():
    passos = _steps()
    esperados = set(STEPS_SEM_EXCECAO) | set(STEPS_COM_EXCECAO_DEPENDABOT) | {"Autor do PR"}
    faltando = esperados - passos.keys()
    assert not faltando, f"steps ausentes em governanca.yml: {faltando}"


# ── Isenção fechada do Dependabot ─────────────────────────────────────────────


def test_steps_humanos_usam_a_mesma_excecao_fechada_do_dependabot():
    for nome in STEPS_COM_EXCECAO_DEPENDABOT:
        condicao = _condicao_if(nome)
        assert "dependabot[bot]" in condicao
        assert "github.event.pull_request.user.login" in condicao
        assert "github.actor" in condicao
        assert condicao.count("&&") >= 1
        assert "||" not in condicao
        assert "endswith" not in condicao
        assert "fromJSON" in condicao and "contains" in condicao
        assert re.search(r"!\s*\(", condicao), (
            f"a condição if: de {nome!r} precisa negar a allowlist — sem `!(...)` "
            "o step rodaria somente para o bot"
        )
        assert _allowlist_workflow(nome) == ["dependabot[bot]"]


def test_isencao_nao_vaza_para_travas_incondicionais():
    passos = _steps()
    for nome in STEPS_SEM_EXCECAO:
        bloco = passos[nome]
        cabecalho = bloco.split("\n        run:", 1)[0]
        assert "if:" not in cabecalho, (
            f"step {nome!r} ganhou condição if: — trava de integridade "
            "não pode receber exceção de bot"
        )
        assert "dependabot" not in bloco.lower(), (
            f"step {nome!r} referencia bot — a exceção deve ficar restrita "
            "aos steps dependentes do corpo humano do PR"
        )


def test_allowlist_do_documento_e_a_esperada():
    assert _allowlist_doc() == ["dependabot[bot]"]


def test_allowlists_do_workflow_e_do_documento_coincidem():
    esperada = _allowlist_doc()
    for nome in STEPS_COM_EXCECAO_DEPENDABOT:
        assert _allowlist_workflow(nome) == esperada


# ── Definition of Done ────────────────────────────────────────────────────────


def test_definition_of_done_minima_e_bloqueante():
    bloco = _steps()["Definition of Done minima marcada"]
    itens = (
        "DoD revisada para o escopo deste PR",
        "Testes compatíveis com o escopo executados",
        "Riscos jurídicos/LGPD avaliados",
        "Rollback definido",
        "Sem quebra conhecida de módulo existente",
    )
    for item in itens:
        assert item in bloco
    assert 'grep -Fqi -- "- [x] $ITEM"' in bloco
    assert "exit 1" in bloco


# ── Classificação de governança e revisão de segurança ───────────────────────


def test_classificacao_governanca_cobre_workflow_documentos_e_engineering():
    bloco = _steps()["Alteracao de governanca isolada"]
    m = re.search(r"PADRAO_GOV='([^']+)'", bloco)
    assert m, "step não declara PADRAO_GOV testável"
    padrao = re.compile(m.group(1))

    caminhos_governanca = (
        ".github/workflows/governanca.yml",
        "docs/GOVERNANCA_FASE2.md",
        "docs/GOVERNANCA_IA.md",
        "docs/engineering/DEFINITION_OF_DONE.md",
        "AGENTS.md",
        ".claude/settings.json",
    )
    for caminho in caminhos_governanca:
        assert padrao.search(caminho), f"arquivo de governança não classificado: {caminho}"

    assert "COD=$(grep -Ec '^(backend/app/|frontend/src/)'" in bloco


def test_mistura_governanca_codigo_emite_aviso_acionavel():
    bloco = _steps()["Alteracao de governanca isolada"]
    assert "PR mistura governança e código funcional" in bloco
    assert "correção sistêmica" in bloco
    assert "harmonização" in bloco
    assert "revise escopo, testes e rollback" in bloco


def test_alteracao_sensivel_exige_revisao_documentada_sem_marcador_ficticio():
    bloco = _steps()["Revisao de seguranca documentada para superficie sensivel"]
    assert "PADRAO_SENSIVEL=" in bloco
    assert "\\.github/workflows/" in bloco
    assert "\\.claude/" in bloco
    for item in (
        "Ownership/RBAC/ABAC revisados quando aplicável",
        "Logs e erros não revelam segredos ou PII",
        "Nenhum segredo, `.env`, credencial ou documento real foi versionado",
    ):
        assert item in bloco
    assert 'grep -Fqi -- "- [x] $ITEM"' in bloco
    assert "exit 1" in bloco
    assert "security-auditor: executado" not in bloco


# ── docs/GOVERNANCA_FASE2.md referencia o canônico, não duplica a regra ──────


def test_fase2_referencia_o_canonico_em_vez_de_ser_fonte_propria():
    fase2 = (REPO_ROOT / "docs" / "GOVERNANCA_FASE2.md").read_text(encoding="utf-8")
    assert "GOVERNANCA_IA.md" in fase2 and "seção 12" in fase2, (
        "docs/GOVERNANCA_FASE2.md precisa apontar para docs/GOVERNANCA_IA.md, "
        "seção 12, em vez de tentar ser fonte própria da exceção de bot"
    )
    assert "endswith" not in fase2
