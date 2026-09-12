#!/bin/bash
set -e

echo "🚀 Deploy do Frontend EJC"
echo "=========================="

# 1. Build do frontend
echo "📦 Building frontend..."
cd /workspace/frontend
npm run build

# 2. Sync para o servidor (se SSH estiver configurado)
if [ -n "$VPS_HOST" ]; then
  echo "🔄 Syncing para VPS..."
  cd /workspace
  node vps-tools/sync.js frontend
else
  echo "⚠️  VPS_HOST não configurado. Use:"
  echo "   export VPS_HOST=root@ejc.depaulateixeira.adv.br"
  echo "   export VPS_SSH_KEY=/path/to/key"
  echo ""
  echo "📁 Build disponível em: /workspace/frontend/dist"
fi

echo "✅ Deploy concluído!"
