#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIPE="$ROOT/.woodpecker.yml"

grep -Fq "gitleaks dir . --redact --verbose --exit-code 1" "$PIPE"
grep -Fq "useDefault = true" "$ROOT/.gitleaks.toml"
grep -Fq 'description = "pytest cache gerado no CI — não é fonte versionável"' "$ROOT/.gitleaks.toml"
grep -Fq "paths = ['''^backend/\\.pytest_cache/''']" "$ROOT/.gitleaks.toml"
if grep -Fq "gitleaks git ." "$PIPE"; then
  echo "secret gate voltou ao modo git SHA-dependente" >&2
  exit 1
fi

grep -Fq 'EVOLUTION_API_KEY=""' "$ROOT/.env.example"
if grep -Fq 'admin:senha' "$ROOT/.claude/skills/arquiteto-automacao-n8n/SKILL.md"; then
  echo "exemplo n8n voltou a conter credencial literal" >&2
  exit 1
fi

grep -Fq 'DATAJUD_TOKEN = os.getenv("DATAJUD_API_KEY")' "$ROOT/.claude/skills/integrador-apis-externas-ejc/SKILL.md"
grep -Fq 'DATAJUD_KEY = os.getenv("DATAJUD_API_KEY", "")' "$ROOT/scripts/probe_apis.py"
grep -Fq '        "module_key": "ramos/previdenciario",  # gitleaks:allow -- chave semântica de módulo, não credencial' "$ROOT/backend/app/seeds/redesign_seed.py"
# Consolidação do DPT360 (auditoria §2.6 #7): a chave dpt360-subroutes sumiu
# do registry e com ela a exceção no .gitleaks.toml; o gate passa a travar a
# linha consolidada das sub-rotas do workspace.
grep -Fq '    subPaths: ["/dpt360/*"],' "$ROOT/frontend/src/config/moduleRegistry.tsx"

printf 'Secret gate: árvore atual, sem baseline por SHA e com exceções locais verificadas.\n'
