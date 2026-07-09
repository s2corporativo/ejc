#!/usr/bin/env python3
"""
Pente-fino estático do EJC.

Objetivo: detectar regressões estruturais introduzidas por múltiplas ondas de IA,
sem acessar segredos e sem alterar código. O script roda localmente no repositório
ou dentro do container backend montando o projeto.

Uso recomendado:
    python scripts/ejc_static_audit.py --root .

Saídas:
    audit_reports/ejc_static_audit.json
    audit_reports/ejc_static_audit.md

Critério de saída:
    exit 2 se houver achado P0;
    exit 1 se houver achado P1;
    exit 0 se somente P2/P3 ou nenhum achado.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "dist", "build",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "uploads", "backups", "audit_reports", ".next",
}

TEXT_EXTENSIONS = {
    ".py", ".txt", ".md", ".json", ".yml", ".yaml", ".toml",
    ".ini", ".env", ".example", ".tsx", ".ts", ".jsx", ".js",
    ".css", ".html", ".sh", ".sql",
}

SECRET_ASSIGN_RE = re.compile(
    r"(?i)(secret|token|api[_-]?key|password|senha|client[_-]?secret|jwt|private[_-]?key)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"
)
PLACEHOLDER_RE = re.compile(
    r"(?i)(trocar|change|example|exemplo|placeholder|seu_|your_|localhost|127\.0\.0\.1|dummy|fake|test|dev|none|null|^$)"
)

MERGE_START_RE = re.compile(r"^<<<<<<<\s+")
MERGE_END_RE = re.compile(r"^>>>>>>>\s+")

RISKY_DEMO_TERMS = (
    "indestrutivel", "indestrutível", "quartel-general", "soberania tecnológica",
    "elite", "mock_db", "dados fictícios", "dados ficticios", "demo",
    "radar de poder", "victory vault", "sala de guerra v3", "diplomacia_v3",
)

STALE_AI_POLICY_TERMS = (
    "toda saída é rascunho",
    "saida é rascunho",
    "saída é rascunho",
    "rascunho sujeito",
    "hitl obrigatório",
    "aviso_hitl",
    "is_rascunho",
)

VERSIONED_OR_SIDE_MODULE_RE = re.compile(r"(_v\d+|_extra|_router)$")

@dataclass
class Finding:
    severity: str
    category: str
    path: str
    line: int | None
    message: str
    recommendation: str


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS or path.name in {"Dockerfile", ".env.example"}:
            yield path


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None
    except Exception:
        return None


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(path)


def add(findings: list[Finding], severity: str, category: str, path: str, line: int | None, message: str, recommendation: str) -> None:
    findings.append(Finding(severity, category, path, line, message, recommendation))


def scan_conflicts(root: Path, findings: list[Finding]) -> None:
    for path in iter_files(root):
        text = read_text(path)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if MERGE_START_RE.match(line) or MERGE_END_RE.match(line):
                add(findings, "P0", "merge_conflict", rel(root, path), i,
                    "Marcador de conflito de merge encontrado.",
                    "Resolver manualmente o conflito antes de qualquer build/deploy.")


def scan_secrets(root: Path, findings: list[Finding]) -> None:
    for path in iter_files(root):
        rpath = rel(root, path)
        if ".env" in path.name and path.name != ".env.example":
            add(findings, "P0", "secret_file", rpath, None,
                "Arquivo de ambiente real pode estar versionado.",
                "Remover do Git, rotacionar segredos e manter apenas .env.example sem valores reais.")
            continue
        text = read_text(path)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            m = SECRET_ASSIGN_RE.search(stripped)
            if not m:
                continue
            value = m.group(2).strip()
            if PLACEHOLDER_RE.search(value) or value.startswith("${") or value in {'""', "''"}:
                continue
            add(findings, "P0", "possible_secret", rpath, i,
                "Possível segredo hardcoded detectado por padrão textual.",
                "Confirmar manualmente. Se for segredo real, remover do histórico e rotacionar imediatamente.")


def scan_python_imports(root: Path, findings: list[Finding]) -> None:
    app_dir = root / "backend" / "app"
    for path in app_dir.rglob("*.py") if app_dir.exists() else []:
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        text = read_text(path)
        if not text:
            continue
        try:
            ast.parse(text)
        except SyntaxError as e:
            add(findings, "P0", "python_syntax", rel(root, path), e.lineno,
                f"Erro de sintaxe Python: {e.msg}.",
                "Corrigir antes de iniciar backend ou rodar migrations.")


def scan_router_import_coupling(root: Path, findings: list[Finding]) -> None:
    main_py = root / "backend" / "app" / "main.py"
    text = read_text(main_py)
    if not text:
        return
    routers = set(re.findall(r"from app\.routers import ([A-Za-z0-9_]+)", text))
    includes = re.findall(r"app\.include_router\(([^.\s]+)\.router", text)
    if len(routers) >= 40:
        add(findings, "P1", "architecture", rel(root, main_py), None,
            f"main.py importa {len(routers)} routers diretamente; qualquer import quebrado derruba o boot inteiro.",
            "Migrar para registro modular com allowlist, health por módulo e feature flags para módulos beta/legados.")
    duplicates = sorted({name for name in includes if includes.count(name) > 1})
    for name in duplicates:
        add(findings, "P1", "router_duplicate", rel(root, main_py), None,
            f"Router '{name}' aparece registrado mais de uma vez.",
            "Manter apenas um include_router por router ou justificar prefixos diferentes.")
    for name in sorted(routers):
        if VERSIONED_OR_SIDE_MODULE_RE.search(name):
            add(findings, "P2", "versioned_or_side_router", rel(root, main_py), None,
                f"Router '{name}' aparenta ser versão paralela, extra ou wrapper.",
                "Classificar como ativo/beta/legado; ocultar por feature flag se não for caminho canônico.")


def scan_public_routers(root: Path, findings: list[Finding]) -> None:
    routers_dir = root / "backend" / "app" / "routers"
    if not routers_dir.exists():
        return
    for path in routers_dir.glob("*.py"):
        text = read_text(path)
        if not text:
            continue
        rpath = rel(root, path)
        if "APIRouter" not in text:
            continue
        has_global_dep = "APIRouter(" in text and "Depends(get_current_user" in text.split("APIRouter(", 1)[1].split(")", 1)[0]
        has_require_roles = "require_roles(" in text or "Depends(require_roles" in text
        has_current_user = "Depends(get_current_user" in text
        has_public_comment = "públic" in text.lower() or "public" in text.lower()
        has_write = re.search(r"@router\.(post|put|patch|delete)\(", text) is not None
        if has_write and not (has_global_dep or has_require_roles or has_current_user) and not has_public_comment:
            add(findings, "P1", "auth_review", rpath, None,
                "Router com método de escrita sem dependência de autenticação/RBAC claramente detectável.",
                "Revisar manualmente; exigir get_current_user/require_roles ou justificar explicitamente rota pública.")


def scan_orm_inside_routers(root: Path, findings: list[Finding]) -> None:
    routers_dir = root / "backend" / "app" / "routers"
    if not routers_dir.exists():
        return
    for path in routers_dir.glob("*.py"):
        text = read_text(path)
        if not text:
            continue
        if "Base" in text and "__tablename__" in text and "Column(" in text:
            add(findings, "P1", "orm_model_inside_router", rel(root, path), None,
                "Modelo ORM declarado dentro de router.",
                "Mover model para app/models e schema para app/schemas; confirmar migration antes de manter em produção.")


def scan_manual_ai_log(root: Path, findings: list[Finding]) -> None:
    app_dir = root / "backend" / "app"
    if not app_dir.exists():
        return
    for path in app_dir.rglob("*.py"):
        rpath = rel(root, path)
        if rpath.endswith("models/ai_log.py") or rpath.endswith("services/ai_guard.py"):
            continue
        text = read_text(path)
        if not text:
            continue
        if "AILog(" in text:
            add(findings, "P2", "manual_ai_log", rpath, None,
                "Arquivo cria AILog manualmente fora do ai_guard.",
                "Migrar gradualmente para app.services.ai_guard.registrar_ai_log para padronizar auditoria, PII e erros.")


def scan_module_registry(root: Path, findings: list[Finding]) -> None:
    registry = root / "backend" / "app" / "services" / "module_registry.py"
    text = read_text(registry)
    if not text:
        return
    if "/api/victory-vault" in text:
        add(findings, "P2", "module_registry", rel(root, registry), None,
            "Registry usa prefixo '/api/victory-vault', mas o router confirmado usa '/api/victory_vault' com underscore.",
            "Adicionar '/api/victory_vault' aos backend_prefixes para o Mapa de Módulos não marcar falso negativo.")
    if "status=\"legado\"" not in text and "status='legado'" not in text:
        add(findings, "P2", "governance", rel(root, registry), None,
            "Nenhum módulo aparece classificado como legado, apesar do histórico de várias ondas de funcionalidades.",
            "Classificar beta/legado/descontinuar por valor operacional, risco LGPD, manutenção e uso real.")


def scan_demo_language(root: Path, findings: list[Finding]) -> None:
    for path in iter_files(root):
        text = read_text(path)
        if text is None:
            continue
        low = text.lower()
        for term in RISKY_DEMO_TERMS:
            if term in low:
                add(findings, "P2", "demo_or_hype_language", rel(root, path), None,
                    f"Termo de demonstração/marketing encontrado: '{term}'.",
                    "Remover linguagem promocional de runtime/documentação técnica ou isolar em material comercial.")
                break


def scan_stale_ai_policy_language(root: Path, findings: list[Finding]) -> None:
    for path in iter_files(root):
        text = read_text(path)
        if text is None:
            continue
        low = text.lower()
        for term in STALE_AI_POLICY_TERMS:
            if term in low:
                add(findings, "P2", "stale_ai_policy_language", rel(root, path), None,
                    f"Resíduo de política antiga encontrado: '{term}'.",
                    "Trocar por padrão de apresentação jurídico-profissional, mantendo apenas a vedação de inventar fatos/fontes.")
                break


def build_summary(findings: list[Finding]) -> dict[str, int]:
    summary = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for f in findings:
        summary[f.severity] = summary.get(f.severity, 0) + 1
    return summary


def write_reports(root: Path, findings: list[Finding]) -> None:
    out = root / "audit_reports"
    out.mkdir(exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "generated_at": generated_at,
        "summary": build_summary(findings),
        "findings": [asdict(f) for f in findings],
    }
    (out / "ejc_static_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Pente-fino estático do EJC", "", f"Gerado em: `{generated_at}`", "", "## Resumo", ""]
    for sev, count in payload["summary"].items():
        lines.append(f"- {sev}: {count}")
    lines += ["", "## Achados", ""]
    if not findings:
        lines.append("Nenhum achado detectado pelos checks estáticos atuais.")
    else:
        for f in findings:
            loc = f"{f.path}:{f.line}" if f.line else f.path
            lines += [
                f"### {f.severity} — {f.category}",
                f"- Local: `{loc}`",
                f"- Achado: {f.message}",
                f"- Recomendação: {f.recommendation}",
                "",
            ]
    (out / "ejc_static_audit.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="raiz do repositório")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    findings: list[Finding] = []
    scan_conflicts(root, findings)
    scan_secrets(root, findings)
    scan_python_imports(root, findings)
    scan_router_import_coupling(root, findings)
    scan_public_routers(root, findings)
    scan_orm_inside_routers(root, findings)
    scan_manual_ai_log(root, findings)
    scan_module_registry(root, findings)
    scan_demo_language(root, findings)
    scan_stale_ai_policy_language(root, findings)
    write_reports(root, findings)

    summary = build_summary(findings)
    print(json.dumps(summary, ensure_ascii=False))
    if summary.get("P0", 0):
        return 2
    if summary.get("P1", 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
