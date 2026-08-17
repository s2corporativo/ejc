"""Contrato das travas de governança do EJC.

A suíte usa o YAML fonte, sem dependência de PyYAML, e protege a exceção fechada
do Dependabot, a classificação do escopo de governança e a exigência de revisão
de segurança em alterações sensíveis.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "governanca-v2.yml"
DOC_PATH = REPO_ROOT / "docs" / "GOVERNANCA_IA.md"

# Travas que precisam continuar valendo incondicionalmente, com ou sem bot.
STEPS_SEM_EXCECAO = (
    "Migration exige reserva registrada",
    "Ausencia de segredo versionado",
    "Revisao de seguranca registrada",
    "Alteracao de governanca isolada",
    "Branch nao e main",
)

STEP_COM_EXCECAO = "Descricao do PR preenchida"


def _steps() -> dict[str, str]:
    """Mapa nome do step → corpo bruto do step (regex sobre o YAML fonte)."""
    texto = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "\n    steps:" in texto, "governanca-v2.yml não declara `steps:` no job"
    job = texto.split("\n    steps:", 1)[1]
    blocos = re.split(r"\n      - name: ", job)[1:]
    passos: dict[str, str] = {}
    for bloco in blocos:
        nome, _, resto = bloco.partition("\n")
        passos[nome.strip()] = resto
    return passos


def _allowlist_workflow() -> list[str]:
    bloco = _steps()[STEP_COM_EXCECAO]
    achados = re.findall(r"fromJSON\('(\[[^']*\])'\)", bloco)
    assert achados, (
        f"step {STEP_COM_EXCECAO!r} não usa contains(fromJSON('[...]'), autor) "
        "na condição if: — isenção não implementada como allowlist fechada"
    )
    listas = [json.loads(bruto) for bruto in achados]
    assert all(lista == listas[0] for lista in listas), (
        "as allowlists da condição if: divergem entre si (autor do PR vs "
        f"github.actor): {listas!r}"
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
    esperados = set(STEPS_SEM_EXCECAO) | {STEP_COM_EXCECAO, "Autor do PR"}
    faltando = esperados - passos.keys()
    assert not faltando, f"steps ausentes em governanca-v2.yml: {faltando}"


def test_workflow_reexecuta_quando_review_e_submetida_no_head_exato():
    texto = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "pull_request_review:" in texto
    assert "types: [submitted]" in texto
    assert "ref: ${{ github.event.pull_request.head.sha }}" in texto
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha }}" in texto
    assert 'git diff --name-only "$BASE_SHA...HEAD"' in texto
    assert "HEAD_REF: ${{ github.event.pull_request.head.ref }}" in texto


def test_checkout_nao_persiste_credencial_do_github_token():
    texto = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "persist-credentials: false" in texto
    assert "git fetch --quiet origin" not in texto


# ── A isenção existe, é allowlist fechada, e só se aplica onde deve ──────────


def _condicao_if() -> str:
    """Corpo bruto da condição `if:` do step com exceção."""
    bloco = _steps()[STEP_COM_EXCECAO]
    m = re.search(r"\n        if:\s*(?:>-\s*\n(.*?)|\$\{\{(.*?)\}\})\n        env:", bloco, re.S)
    assert m, (
        f"step {STEP_COM_EXCECAO!r} não tem condição if: no formato esperado "
        "imediatamente antes de `env:`"
    )
    return m.group(1) or m.group(2)


def test_step_de_descricao_tem_condicao_if_com_dependabot():
    condicao = _condicao_if()
    assert "dependabot[bot]" in condicao
    assert "github.event.pull_request.user.login" in condicao


def test_condicao_tambem_checa_o_ator_que_disparou_o_evento():
    condicao = _condicao_if()
    assert "github.actor" in condicao, (
        "a condição não checa github.actor — um push humano numa branch do "
        "dependabot escaparia da trava de Issue/modelo"
    )
    assert condicao.count("&&") >= 1
    assert "||" not in condicao


def test_condicao_nao_usa_padrao_amplo_de_bot():
    condicao = _condicao_if()
    assert "endswith" not in condicao
    assert "fromJSON" in condicao and "contains" in condicao


def test_condicao_e_negada_para_nao_isentar_pr_humano():
    condicao = _condicao_if()
    assert re.search(r"!\s*\(", condicao), (
        "a condição if: não nega a allowlist — sem `!(...)` o step de descrição "
        "rodaria só para o bot"
    )


def test_isencao_nao_vaza_para_as_outras_travas():
    passos = _steps()
    for nome in STEPS_SEM_EXCECAO:
        bloco = passos[nome]
        cabecalho = bloco.split("\n        run:", 1)[0]
        assert "if:" not in cabecalho, (
            f"step {nome!r} ganhou condição if: — trava de segurança/integridade "
            "não pode ganhar exceção de bot"
        )
        assert "dependabot" not in bloco.lower(), (
            f"step {nome!r} referencia bot — a isenção é exclusiva do step "
            f"{STEP_COM_EXCECAO!r}"
        )


# ── Allowlist: workflow e documento canônico coincidem ───────────────────────


def test_allowlist_do_workflow_e_a_esperada():
    assert _allowlist_workflow() == ["dependabot[bot]"]


def test_allowlist_do_documento_e_a_esperada():
    assert _allowlist_doc() == ["dependabot[bot]"]


def test_allowlist_do_workflow_e_do_documento_coincidem_exatamente():
    allow_workflow = _allowlist_workflow()
    allow_doc = _allowlist_doc()
    assert allow_workflow == allow_doc, (
        "allowlist do workflow diverge da allowlist documentada em "
        f"docs/GOVERNANCA_IA.md, seção 12: workflow={allow_workflow!r} "
        f"doc={allow_doc!r}"
    )


# ── Classificação de governança e revisão de segurança ───────────────────────


def test_classificacao_governanca_cobre_workflow_e_documento_fase2():
    bloco = _steps()["Alteracao de governanca isolada"]
    m = re.search(r"PADRAO_GOV='([^']+)'", bloco)
    assert m, "step não declara PADRAO_GOV testável"
    padrao = re.compile(m.group(1))

    caminhos_governanca = (
        ".github/workflows/governanca.yml",
        ".github/workflows/governanca-v2.yml",
        "docs/GOVERNANCA_FASE2.md",
        "docs/GOVERNANCA_IA.md",
        "AGENTS.md",
        ".claude/settings.json",
    )
    for caminho in caminhos_governanca:
        assert padrao.search(caminho), f"arquivo de governança não classificado: {caminho}"

    assert "COD=$(grep -Ec '^(backend/app/|frontend/src/)'" in bloco


def test_mistura_governanca_codigo_emite_aviso_em_portugues():
    bloco = _steps()["Alteracao de governanca isolada"]
    assert "PR mistura governança e código funcional" in bloco
    assert "correção sistêmica" in bloco
    assert "harmonização" in bloco
    assert "implementação" in bloco
    assert "na revisão" in bloco
    assert "no review" not in bloco


def test_alteracao_sensivel_exige_atestacao_independente_no_head():
    bloco = _steps()["Revisao de seguranca registrada"]
    assert "PADRAO_SENSIVEL=" in bloco
    assert "\\.github/workflows/" in bloco
    assert "\\.claude/" in bloco
    assert "scripts/governanca/branch-protection-bootstrap\\.sh" in bloco
    assert "security-auditor: executado" not in bloco
    assert "github.event.pull_request.body" not in bloco
    assert "pulls/$PR_NUMBER/reviews?per_page=100" in bloco
    assert "| jq -s 'add'" in bloco
    assert 'select(.user.login == "coderabbitai[bot]")' in bloco
    assert "select(.commit_id == $sha)" in bloco
    assert '.state == "APPROVED" or .state == "COMMENTED"' in bloco
    assert "Actionable comments posted:[[:space:]]*0" in bloco
    assert 'test("Actionable comments posted:"; "i") | not' not in bloco
    assert "HEAD_SHA" in bloco
    assert "exit 1" in bloco


def test_atestacao_rejeita_marcador_ausente_ou_contagem_nao_zero():
    bloco = _steps()["Revisao de seguranca registrada"]
    assert "Actionable comments posted:[[:space:]]*0" in bloco
    assert "atestado explícita de zero findings" not in bloco
    assert "atestação explícita de zero findings" in bloco


# ── docs/GOVERNANCA_FASE2.md referencia o canônico, não duplica a regra ──────


def test_fase2_referencia_o_canonico_em_vez_de_ser_fonte_propria():
    fase2 = (REPO_ROOT / "docs" / "GOVERNANCA_FASE2.md").read_text(encoding="utf-8")
    assert "GOVERNANCA_IA.md" in fase2 and "seção 12" in fase2, (
        "docs/GOVERNANCA_FASE2.md precisa apontar para docs/GOVERNANCA_IA.md, "
        "seção 12, em vez de tentar ser fonte própria da exceção de bot"
    )
    assert "endswith" not in fase2
