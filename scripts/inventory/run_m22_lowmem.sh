#!/bin/bash
# Executa a bateria M22 com EMBEDDINGS_ENABLED=false no .env (modelo e5-large
# ~2,3GB excede a memória do sandbox de QA — limitação de ambiente, não do
# sistema). Restaura o .env ao final. Não comitar o .env alterado.
set -e
cd /home/ubuntu/ejc_repo
if ! grep -q "^EMBEDDINGS_ENABLED=true$" .env; then
  echo "ERRO: .env não tem EMBEDDINGS_ENABLED=true" >&2
  exit 1
fi
sed -i 's/^EMBEDDINGS_ENABLED=true$/EMBEDDINGS_ENABLED=false/' .env
PYTHONPATH=/home/ubuntu/ejc_repo/backend \
  bash scripts/inventory/env_shell.sh python3 -u \
  scripts/inventory/m22_retrieval_acl_tests.py
RC=$?
git checkout -- .env
exit $RC
