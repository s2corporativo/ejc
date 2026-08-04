"""Fixa o contrato da exceção de bot na trava de governança (Issue #534).

Contexto (2026-08-04): a Issue #534 pedia para *documentar* uma isenção de
dependabot que, segundo ela, já estaria implementada pelo PR #533. Investigação
mostrou que a premissa era falsa: `.github/workflows/governanca.yml` não tinha
nenhuma lógica de isenção — o step "Descricao do PR preenchida" rodava
incondicionalmente para todo PR, o PR #533 foi fechado SEM merge, e este arquivo
não existia. Na prática, todo PR do dependabot (inclusive atualização de
dependência de segurança) reprovava a trava de governança por não ter Issue
vinculada nem preencher o template — confirmado empiricamente no PR #671
(2026-08-03).

Esta suíte cobre a implementação real feita para corrigir isso:

  1. o step "Descricao do PR preenchida" ganha uma condição `if:` que isenta
     PR aberto por autor de uma allowlist FECHADA (hoje só `dependabot[bot]`);
  2. a condição usa `contains(fromJSON(allowlist), autor)` — allowlist
     explícita, não um padrão amplo tipo `endswith('[bot]')` sozinho, que
     isentaria qualquer bot;
  3. NENHUM outro step da trava (migration, segredo, escopo, branch de
     origem) ganha exceção nenhuma — continuam bloqueando PR de bot como
     bloqueiam PR humano;
  4. a allowlist do workflow e a allowlist documentada em
     `docs/GOVERNANCA_IA.md`, seção 12, coincidem EXATAMENTE.

Sem PyYAML: o pacote não está em `backend/requirements.txt` (o `pyyaml`
disponível neste ambiente de desenvolvimento é dependência transitiva de
`conan`, não do EJC) e o repositório não usa parsing de YAML em teste — o
padrão já estabelecido é ler o arquivo fonte e conferir por regex, como
`test_migration_numbering_guard.py` faz para as migrations do Alembic. Esta
suíte segue o mesmo padrão para não introduzir uma dependência nova sem
autorização (`CLAUDE.md`, "Regras de decisão").
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "governanca.yml"
DOC_PATH = REPO_ROOT / "docs" / "GOVERNANCA_IA.md"

# Travas que precisam continuar valendo incondicionalmente, com ou sem bot.
STEPS_SEM_EXCECAO = (
    "Migration exige reserva registrada",
    "Ausencia de segredo versionado",
    "Alteracao de governanca isolada",
    "Branch nao e main",
)

STEP_COM_EXCECAO = "Descricao do PR preenchida"


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


def _allowlist_workflow() -> list[str]:
    bloco = _steps()[STEP_COM_EXCECAO]
    m = re.search(r"fromJSON\('(\[[^']*\])'\)", bloco)
    assert m, (
        f"step {STEP_COM_EXCECAO!r} não usa contains(fromJSON('[...]'), autor) "
        "na condição if: — isenção não implementada como allowlist fechada"
    )
    return json.loads(m.group(1))


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
    assert not faltando, f"steps ausentes em governanca.yml: {faltando}"


# ── A isenção existe, é allowlist fechada, e só se aplica onde deve ──────────

def test_step_de_descricao_tem_condicao_if_com_dependabot():
    bloco = _steps()[STEP_COM_EXCECAO]
    m = re.search(r"if:\s*\$\{\{(.*?)\}\}", bloco)
    assert m, (
        f"step {STEP_COM_EXCECAO!r} não tem condição if: — PR do dependabot "
        "continuaria sendo reprovado por falta de Issue vinculada/template"
    )
    condicao = m.group(1)
    assert "dependabot[bot]" in condicao
    assert "github.event.pull_request.user.login" in condicao


def test_condicao_nao_usa_padrao_amplo_de_bot():
    bloco = _steps()[STEP_COM_EXCECAO]
    m = re.search(r"if:\s*\$\{\{(.*?)\}\}", bloco)
    assert m
    condicao = m.group(1)
    # Um padrao tipo endswith('[bot]') isentaria QUALQUER bot, nao so o
    # dependabot — exatamente o que a Issue e o CLAUDE.md pedem para evitar.
    assert "endswith" not in condicao
    assert "fromJSON" in condicao and "contains" in condicao


def test_isencao_nao_vaza_para_as_outras_travas():
    """As travas de migration, segredo, escopo e branch de origem continuam
    valendo integralmente para PR de bot — só o step de descrição é pulado."""
    passos = _steps()
    for nome in STEPS_SEM_EXCECAO:
        bloco = passos[nome]
        cabecalho = bloco.split("\n        run:", 1)[0]
        assert "if:" not in cabecalho, (
            f"step {nome!r} ganhou uma condição if: — as travas de segurança/"
            "integridade não podem ganhar exceção de bot"
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


# ── docs/GOVERNANCA_FASE2.md referencia o canônico, não duplica a regra ──────

def test_fase2_referencia_o_canonico_em_vez_de_ser_fonte_propria():
    fase2 = (REPO_ROOT / "docs" / "GOVERNANCA_FASE2.md").read_text(encoding="utf-8")
    assert "GOVERNANCA_IA.md" in fase2 and "seção 12" in fase2, (
        "docs/GOVERNANCA_FASE2.md precisa apontar para docs/GOVERNANCA_IA.md, "
        "seção 12, em vez de tentar ser fonte própria da exceção de bot"
    )
    # Não pode ter uma allowlist DIFERENTE da canônica escondida em prosa.
    assert "endswith" not in fase2
