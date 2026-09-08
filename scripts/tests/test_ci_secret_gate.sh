#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIPE="$ROOT/.woodpecker.yml"

grep -Fq "gitleaks dir . --redact --verbose --exit-code 1" "$PIPE" 
grep -Fq "useDefault = true" "$ROOT/.gitleaks.toml"
grep -Fq "moduleRegistry-[^/]+\\.js" "$ROOT/.gitleaks.toml"
grep -Fq "dpt360-subroutes" "$ROOT/.gitleaks.toml"
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
grep -Fq '    key: "dpt360-subroutes", // gitleaks:allow -- chave semântica do registry, não credencial' "$ROOT/frontend/src/config/moduleRegistry.tsx"

printf 'Secret gate: árvore atual, sem baseline por SHA e com exceções locais verificadas.\n'
