#!/usr/bin/env bash
# =============================================================================
#  inventario-repo.sh
#  Gera, a partir do CODIGO REAL, os documentos de inventario:
#    docs/MAPA_DE_MODULOS.md      estrutura efetiva do backend e frontend
#    docs/MATRIZ_DE_ROTAS.md      rotas FastAPI x chamadas do frontend
#    docs/ARQUITETURA_ATUAL.md    stack, dependencias e pontos de integracao
#
#  Principio: nada e inventado. Tudo e extraido por leitura do repositorio.
#  O que nao for extraivel fica marcado como "PREENCHIMENTO HUMANO".
#
#  Uso:  bash scripts/governanca/inventario-repo.sh
#  Somente leitura sobre o codigo; escreve apenas em docs/.
#
#  Regenerar apos alteracao estrutural. O grafo do graphify (graphify-out/)
#  cobre o detalhe de chamada; este inventario cobre a estrutura e o contrato
#  de rota, que a governanca cobra em revisao de PR.
# =============================================================================
# Sem `pipefail` por desenho: este script e extracao best-effort sobre o codigo.
# Um `grep` sem correspondencia (workflow sem job nomeado, diretorio sem model)
# e resultado valido — "nao ha" —, nao erro de execucao.
set -eu

falhar() { echo ""; echo "ABORTADO: $1"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || falhar "execute na raiz do repositorio."
cd "$(git rev-parse --show-toplevel)"
mkdir -p docs
DATA="$(date +%Y-%m-%d)"
# `--short` sozinho cresce conforme o numero de objetos do repositorio, o que
# faria o cabecalho divergir entre geracoes sobre o MESMO commit. Fixa-se o tamanho.
REV="$(git rev-parse --short=8 HEAD)"

# As secoes PREENCHIMENTO HUMANO destes documentos sao reescritas vazias a cada
# geracao. Guarda-se a versao anterior para que o conteudo humano possa ser
# recuperado e recolado — sem isto, regenerar destruiria trabalho manual.
#
# O destino e var/, ja ignorado pelo .gitignore: copia transitoria nao entra em
# diff nem e commitada por engano, e nao foi preciso alterar o .gitignore.
ANTERIOR="var/inventario-anterior"
preservar() {
  [ -f "$1" ] || return 0
  mkdir -p "$ANTERIOR"
  cp "$1" "$ANTERIOR/$(basename "$1")"
  echo "  [..] versao anterior preservada em $ANTERIOR/$(basename "$1")"
}
for d in docs/MAPA_DE_MODULOS.md docs/MATRIZ_DE_ROTAS.md docs/ARQUITETURA_ATUAL.md; do
  preservar "$d"
done

echo "Inventariando repositorio (commit $REV)..."

# ---------------------------------------------------------------- MODULOS ---
{
  echo "# MAPA DE MODULOS — EJC"
  echo ""
  echo "> Gerado por \`scripts/governanca/inventario-repo.sh\` em $DATA, commit \`$REV\`."
  echo "> Regenerar apos alteracao estrutural. Nao editar as secoes automaticas a mao."
  echo ""

  echo "## 1. Estrutura de primeiro e segundo nivel"
  echo ""
  echo '```'
  # `var/` fica de fora: e diretorio transitorio e ignorado, criado por este
  # proprio script para guardar a copia anterior. Inclui-lo faria o inventario
  # se auto-contaminar, listando o proprio rastro como estrutura do projeto.
  find . -maxdepth 2 -type d \
    -not -path './.git*' -not -path '*/node_modules*' -not -path '*/.venv*' \
    -not -path '*/__pycache__*' -not -path './dist*' -not -path './build*' \
    -not -path './graphify-out*' -not -path './var*' -not -path './evidencias*' \
    | sort | sed 's|^\./||' | sed '/^\.$/d'
  echo '```'
  echo ""

  echo "## 2. Backend — modulos Python"
  echo ""
  if [ -d backend ]; then
    echo "| Caminho | Arquivos .py | Linhas |"
    echo "|---|---|---|"
    find backend -type d -not -path '*/__pycache__*' -not -path '*/.venv*' | sort | while read -r d; do
      N=$(find "$d" -maxdepth 1 -name '*.py' -type f 2>/dev/null | wc -l)
      [ "$N" -eq 0 ] && continue
      L=$(find "$d" -maxdepth 1 -name '*.py' -type f -exec cat {} + 2>/dev/null | wc -l)
      echo "| \`$d\` | $N | $L |"
    done
  else
    echo "_Diretorio \`backend/\` ausente._"
  fi
  echo ""

  echo "## 3. Frontend — estrutura de src"
  echo ""
  if [ -d frontend/src ]; then
    echo "| Caminho | Arquivos .ts/.tsx | Linhas |"
    echo "|---|---|---|"
    find frontend/src -type d | sort | while read -r d; do
      N=$(find "$d" -maxdepth 1 \( -name '*.ts' -o -name '*.tsx' \) -type f 2>/dev/null | wc -l)
      [ "$N" -eq 0 ] && continue
      L=$(find "$d" -maxdepth 1 \( -name '*.ts' -o -name '*.tsx' \) -type f -exec cat {} + 2>/dev/null | wc -l)
      echo "| \`$d\` | $N | $L |"
    done
  else
    echo "_Diretorio \`frontend/src\` ausente._"
  fi
  echo ""

  echo "## 4. Modelos de dados detectados"
  echo ""
  echo '```'
  grep -rhoE 'class +[A-Za-z_][A-Za-z0-9_]* *\( *Base' backend/app 2>/dev/null \
    | sed -E 's/class +([A-Za-z0-9_]+).*/\1/' | sort -u || echo "(nenhum modelo detectado)"
  echo '```'
  echo ""
  echo "> Nem toda tabela possui model ORM: ~30 tabelas do EJC existem apenas em SQL bruto"
  echo "> (ver \`backend/alembic/env.py\`, guarda \`include_name()\`). Esta lista NAO e o schema completo."
  echo ""

  echo "## 5. Migrations"
  echo ""
  if [ -d backend/alembic/versions ]; then
    echo "Total de arquivos: $(find backend/alembic/versions -name '*.py' | wc -l)"
    echo ""
    echo "Ultimas 15 por ordem de numeracao:"
    echo ""
    echo '```'
    ls -1 backend/alembic/versions/*.py 2>/dev/null | sort | tail -15 || true
    echo '```'
    echo ""
    echo "Reserva de numeracao: \`backend/alembic/MIGRATION_RESERVATIONS.md\`."
    echo "A trava automatica esta em \`.github/workflows/governanca.yml\`."
  else
    echo "_Diretorio de migrations nao localizado em \`backend/alembic/versions\`._"
    echo ""
    echo "**Atencao:** se o caminho real divergir, ajuste o passo \"Migration exige reserva"
    echo "registrada\" em \`.github/workflows/governanca.yml\` e este script."
  fi
  echo ""

  echo "## 6. Responsabilidade por modulo — PREENCHIMENTO HUMANO"
  echo ""
  echo "| Modulo | Responsabilidade funcional | Depende de | Nao pode ser duplicado por |"
  echo "|---|---|---|---|"
  echo "| | | | |"
  echo ""
  echo "> Esta secao nao e extraivel do codigo. Define o contrato de responsabilidade"
  echo "> que impede duplicacao de componentes entre agentes."
} > docs/MAPA_DE_MODULOS.md
echo "  [->] docs/MAPA_DE_MODULOS.md"

# ------------------------------------------------------------------ ROTAS ---
{
  echo "# MATRIZ DE ROTAS — EJC"
  echo ""
  echo "> Gerado por \`scripts/governanca/inventario-repo.sh\` em $DATA, commit \`$REV\`."
  echo "> Divergencia entre backend e frontend nesta matriz e defeito P1."
  echo ""

  echo "## 1. Rotas declaradas no backend"
  echo ""
  echo "| Metodo | Caminho | Arquivo |"
  echo "|---|---|---|"
  if [ -d backend/app ]; then
    grep -rnE '@(app|router|api_router)\.(get|post|put|patch|delete)\(' backend/app --include='*.py' 2>/dev/null \
      | sed -E 's|^([^:]+):([0-9]+):.*@[a-z_]+\.([a-z]+)\(["'"'"']([^"'"'"']+)["'"'"'].*|\| \U\3\E \| `\4` \| `\1:\2` \||' \
      | grep '^|' | sort -u || echo "| — | — | (nenhuma rota detectada) |"
  else
    echo "| — | — | (backend/app ausente) |"
  fi
  echo ""

  echo "## 2. Registro de routers em main.py"
  echo ""
  echo '```'
  grep -nE 'include_router\(' backend/app/main.py 2>/dev/null | head -200 \
    || echo "(backend/app/main.py ausente ou sem include_router)"
  echo '```'
  echo ""
  echo "> Todos os routers do EJC sao registrados manualmente em \`backend/app/main.py\`"
  echo "> sob o prefixo \`API = \"/api\"\`. Router nao registrado la nao existe em runtime."
  echo ""

  echo "## 3. Chamadas de API no frontend"
  echo ""
  echo "| Caminho chamado | Arquivo |"
  echo "|---|---|"
  if [ -d frontend/src ]; then
    # O cliente axios usa baseURL "/api" (frontend/src/lib/api.ts), entao as
    # chamadas aparecem como api.get("/casos"), sem o prefixo. Captura ambas
    # as formas: a relativa ao cliente e a absoluta.
    {
      grep -rnoE '\b(api|http)\.(get|post|put|patch|delete)\(\s*[`"'"'"']/[A-Za-z0-9_/{}$.-]+' frontend/src 2>/dev/null \
        | sed -E 's|^([^:]+):([0-9]+):[^`"'"'"']*[`"'"'"'](/.+)|\| `/api\3` \| `\1:\2` \||'
      grep -rnoE '[`"'"'"']/api/[A-Za-z0-9_/{}$.-]+' frontend/src 2>/dev/null \
        | sed -E 's|^([^:]+):([0-9]+):[`"'"'"'](/.+)|\| `\3` \| `\1:\2` \||'
    } | grep '^|' | sort -u || echo "| — | (nenhuma chamada detectada) |"
  else
    echo "| — | (frontend/src ausente) |"
  fi
  echo ""

  echo "## 4. Verificacao de divergencia — PREENCHIMENTO HUMANO"
  echo ""
  echo "| Rota chamada pelo frontend | Existe no backend? | Metodo confere? | Contrato confere? | Acao |"
  echo "|---|---|---|---|---|"
  echo "| | | | | |"
  echo ""
  echo "> Comparar as secoes 1 e 3. Chamada sem rota correspondente e defeito P1."
  echo "> Rota sem consumidor e candidata a remocao — confirmar antes."
  echo "> Rotas com parametro de caminho aparecem parametrizadas de um lado"
  echo "> (\`/casos/{caso_id}\`) e interpoladas do outro (\`/casos/\${id}\`): a"
  echo "> comparacao e por forma normalizada, nao textual."
  echo ""

  echo "## 5. Controle de acesso por rota — PREENCHIMENTO HUMANO"
  echo ""
  echo "| Rota | Autenticacao | RBAC (perfis) | Isolamento por escritorio | Testado |"
  echo "|---|---|---|---|---|"
  echo "| | | | | |"
  echo ""
  echo "> Rota sem autenticacao declarada ou sem filtro de tenant e defeito P0."
  echo "> No EJC a autenticacao e imposta pelo \`AuthMiddleware\`; a autorizacao"
  echo "> por perfil vem de \`require_roles()\`/\`require_admin\`. Endpoint publico"
  echo "> e excecao explicita e precisa de justificativa registrada."
} > docs/MATRIZ_DE_ROTAS.md
echo "  [->] docs/MATRIZ_DE_ROTAS.md"

# ----------------------------------------------------------- ARQUITETURA ---
{
  echo "# ARQUITETURA ATUAL — EJC"
  echo ""
  echo "> Gerado por \`scripts/governanca/inventario-repo.sh\` em $DATA, commit \`$REV\`."
  echo "> Descreve o estado observado, nao o estado desejado."
  echo ""

  echo "## 1. Dependencias declaradas — backend"
  echo ""
  echo '```'
  for f in backend/requirements.txt backend/pyproject.toml requirements.txt pyproject.toml; do
    [ -f "$f" ] && { echo "--- $f ---"; head -60 "$f"; }
  done
  echo '```'
  echo ""

  echo "## 2. Dependencias declaradas — frontend"
  echo ""
  echo '```'
  if [ -f frontend/package.json ]; then
    sed -n '/"dependencies"/,/}/p' frontend/package.json
  else
    echo "(frontend/package.json ausente)"
  fi
  echo '```'
  echo ""

  echo "## 3. Servicos em Docker Compose"
  echo ""
  echo '```'
  if [ -f docker-compose.yml ]; then
    grep -nE '^\s{2}[a-z0-9_-]+:|image:|ports:|volumes:|depends_on:|profiles:' docker-compose.yml | head -80
  else
    echo "(docker-compose.yml ausente)"
  fi
  echo '```'
  echo ""

  echo "## 4. Variaveis de ambiente esperadas"
  echo ""
  echo '```'
  if [ -f .env.example ]; then
    grep -oE '^[A-Z0-9_]+' .env.example | sort -u
  else
    echo "(.env.example ausente — recomendado criar)"
  fi
  echo '```'
  echo ""
  echo "> Nunca listar valores. Apenas nomes de variavel."
  echo ""

  echo "## 5. Workflows de CI"
  echo ""
  echo "| Workflow | Gatilhos | Jobs (nome do check) |"
  echo "|---|---|---|"
  for w in .github/workflows/*.yml; do
    [ -f "$w" ] || continue
    GAT="$(sed -n '/^on:/,/^[a-z]/p' "$w" | grep -oE '^[[:space:]]+(pull_request|push|workflow_dispatch|schedule)' | tr -d ' ' | sort -u | paste -sd' ' - || true)"
    # `paste -d` consome um caractere por delimitador: uma string multibyte como
    # ' · ' corromperia a saida. Junta-se com ';' e troca-se depois.
    # O `|` do nome do job e escapado para nao quebrar a tabela markdown.
    JOBS="$(grep -E '^    name:' "$w" | sed -E 's/^    name: *//; s/\|/\\|/g' | paste -sd';' - | sed 's/;/ · /g' || true)"
    echo "| \`$(basename "$w")\` | ${GAT:-—} | ${JOBS:-—} |"
  done
  echo ""
  echo "> Os nomes de job desta tabela sao os contextos exigidos na protecao da"
  echo "> branch \`main\` (\`scripts/governanca/branch-protection.sh\`). Renomear um"
  echo "> job obriga a reaplicar a protecao, sob pena de nenhum PR ser mesclavel."
  echo ""

  echo "## 6. Integracoes externas detectadas"
  echo ""
  echo '```'
  grep -rhoE 'https?://[a-zA-Z0-9.-]+' backend/app frontend/src --include='*.py' --include='*.ts' --include='*.tsx' 2>/dev/null \
    | sed -E 's|https?://||' | sort -u \
    | grep -vE '^(localhost|127\.0\.0\.1|0\.0\.0\.0|example\.(com|org)|www\.w3\.org|schemas?\.|json-schema\.org)' | head -40 \
    || echo "(nenhuma)"
  echo '```'
  echo ""
  echo "> Toda integracao externa do EJC e opt-in por flag de ambiente, com default"
  echo "> OFF e degradacao graciosa. Dominio nesta lista sem flag correspondente e defeito."
  echo ""

  echo "## 7. Decisoes arquiteturais vigentes — PREENCHIMENTO HUMANO"
  echo ""
  echo "| Decisao | Motivo | Data | Alternativa descartada | Reversivel |"
  echo "|---|---|---|---|---|"
  echo "| | | | | |"
  echo ""

  echo "## 8. Debitos tecnicos conhecidos — PREENCHIMENTO HUMANO"
  echo ""
  echo "| Debito | Impacto | Prioridade | Issue |"
  echo "|---|---|---|---|"
  echo "| | | | |"
} > docs/ARQUITETURA_ATUAL.md
echo "  [->] docs/ARQUITETURA_ATUAL.md"

echo ""
cat <<'FIM'
============================================================
 CONCLUIDO — inventario
============================================================
Tres documentos gerados a partir do codigo real. As secoes marcadas
como PREENCHIMENTO HUMANO nao sao extraiveis e permanecem vazias:
preenche-las por inferencia produziria documentacao falsa.

Revise antes de commitar. Regenere apos alteracao estrutural.
FIM
