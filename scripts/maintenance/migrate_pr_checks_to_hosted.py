#!/usr/bin/env python3
"""Move checks isolados para runners GitHub-hosted.

A VPS permanece reservada a workflows que dependem do ambiente oficial:
deploy, backup real, ativação de RAG e provas operacionais de produção.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = [
    ".github/workflows/ci.yml",
    ".github/workflows/governanca.yml",
    ".github/workflows/ejc-release-gate.yml",
    ".github/workflows/continuity-ui-gates.yml",
    ".github/workflows/architecture-inventory.yml",
    ".github/workflows/main-provenance.yml",
]


def replace_exact(text: str, old: str, new: str, path: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: âncora inesperada ({count} ocorrências)")
    return text.replace(old, new, 1)


def patch_ci(text: str) -> str:
    path = WORKFLOWS[0]
    text = replace_exact(
        text,
        "# CI no runner SELF-HOSTED: roda no VPS do escritório, mantendo checks auditáveis\n"
        "# sem consumo de minutos hospedados. Requer o runner registrado e online com os\n"
        "# labels `self-hosted` e `ejc-vps` (docs/RUNNER_SELFHOSTED.md).",
        "# CI em runners GitHub-hosted, efêmeros e isolados da produção. Os jobs\n"
        "# independentes executam em paralelo; o runner `ejc-vps` fica reservado a\n"
        "# deploy, backup real e demais operações do ambiente oficial.",
        path,
    )
    text = text.replace(
        "          # Porta ALTA no host: o runner é self-hosted e divide o VPS com o\n"
        "          # Postgres de produção, que ocupa a 5432 — mapear 5432:5432 falhava com\n"
        "          # \"Bind for 0.0.0.0:5432 failed: port is already allocated\" e o job\n"
        "          # morria antes do checkout. Dentro do container segue 5432.\n",
        "          # Porta dedicada do serviço efêmero deste job. O valor alto mantém\n"
        "          # compatibilidade com os scripts existentes e evita acoplamento.\n",
    )
    text = text.replace(
        "          # -p obrigatório: o serviço é exposto em 55432 no host (a 5432 é do\n"
        "          # Postgres de produção). Sem a porta, o psql usa 5432 e falha com\n"
        "          # \"Connection refused\".\n",
        "          # -p obrigatório porque o serviço efêmero foi publicado em 55432.\n",
    )
    return text


def patch_governanca(text: str) -> str:
    path = WORKFLOWS[1]
    text = replace_exact(
        text,
        "# Runner SELF-HOSTED `ejc-vps`, como os demais workflows do repositório\n"
        "# (docs/RUNNER_SELFHOSTED.md).",
        "# Executa em runner GitHub-hosted: não depende da disponibilidade da VPS e\n"
        "# não acessa produção, secrets operacionais ou dados reais.",
        path,
    )
    text = text.replace(
        "          # $RUNNER_TEMP, nao /tmp: o runner e self-hosted e divide o VPS. Um\n"
        "          # /tmp/alterados.txt deixado por outra execucao (ou por outro usuario)\n"
        "          # nao pode ser sobrescrito por causa do sticky bit do /tmp, e o job\n"
        "          # morre com \"Permission denied\". $RUNNER_TEMP e isolado por job.\n",
        "          # $RUNNER_TEMP é isolado por job e evita colisões entre execuções.\n",
    )
    return text


def patch_release(text: str) -> str:
    return replace_exact(
        text,
        "# Gate P0 no runner SELF-HOSTED. Impede conflitos, segredos, CORS inseguro,\n"
        "# resíduos críticos, reintrodução de backup em claro e rollback não comprovado.",
        "# Gate P0 em runner GitHub-hosted e isolado da produção. Impede conflitos,\n"
        "# segredos, CORS inseguro, backup em claro e rollback não comprovado.",
        WORKFLOWS[2],
    )


def patch_continuity(text: str) -> str:
    text = text.replace(
        "          # Porta ALTA e DISTINTA da usada pelo ci.yml (55432): o runner é\n"
        "          # self-hosted e divide o VPS com o Postgres de produção, que ocupa a\n"
        "          # 5432. Portas diferentes por workflow também evitam que dois jobs\n"
        "          # concorrentes no mesmo host colidam entre si.\n",
        "          # Porta dedicada do PostgreSQL efêmero usado exclusivamente por este job.\n",
    )
    text = text.replace(
        "          # -p obrigatório: o serviço é exposto em 55433 no host (a 5432 é do\n"
        "          # Postgres de produção). Sem a porta, o psql usa 5432 e falha com\n"
        "          # \"Connection refused\".\n",
        "          # -p obrigatório porque o serviço efêmero foi publicado em 55433.\n",
    )
    return text


def main() -> None:
    for relative in WORKFLOWS:
        file = ROOT / relative
        text = file.read_text(encoding="utf-8")
        if relative.endswith("ci.yml"):
            text = patch_ci(text)
        elif relative.endswith("governanca.yml"):
            text = patch_governanca(text)
        elif relative.endswith("ejc-release-gate.yml"):
            text = patch_release(text)
        elif relative.endswith("continuity-ui-gates.yml"):
            text = patch_continuity(text)

        occurrences = text.count("runs-on: [self-hosted, ejc-vps]")
        if occurrences == 0:
            raise RuntimeError(f"{relative}: nenhum job self-hosted encontrado")
        text = text.replace("runs-on: [self-hosted, ejc-vps]", "runs-on: ubuntu-latest")
        file.write_text(text, encoding="utf-8")

    remaining = [
        relative
        for relative in WORKFLOWS
        if "runs-on: [self-hosted, ejc-vps]"
        in (ROOT / relative).read_text(encoding="utf-8")
    ]
    if remaining:
        raise RuntimeError(f"workflows ainda presos à VPS: {remaining}")

    print(f"Migrados {len(WORKFLOWS)} workflows para runners GitHub-hosted")


if __name__ == "__main__":
    main()
