#!/usr/bin/env bash
# Instala o pre-push do EJC (symlink em .git/hooks). Uma vez por clone.
set -euo pipefail
RAIZ="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOKS_DIR"
chmod +x "$RAIZ/scripts/hooks/pre-push"
ln -sf "$RAIZ/scripts/hooks/pre-push" "$HOOKS_DIR/pre-push"
echo "pre-push instalado em $HOOKS_DIR/pre-push → scripts/hooks/pre-push"
