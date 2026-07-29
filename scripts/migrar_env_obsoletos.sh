#!/usr/bin/env bash
# migrar_env_obsoletos.sh — ajusta valores OBSOLETOS num .env já existente.
#
# Por que existe: o .env da VPS sobrevive ao deploy por desenho, então trocar um
# default em app/core/config.py ou em .env.example NÃO alcança as instalações
# existentes. Estes ajustes fecham essa lacuna.
#
# A migração vivia embutida em scripts/deploy-vps.sh, que é um bootstrap MANUAL
# e NÃO faz parte do caminho de deploy real (.github/workflows/deploy-vps.yml →
# scripts/deploy_vps_safe.sh). Na prática, a correção nunca rodava em produção.
# Agora ela é um script único chamado pelos dois caminhos.
#
# Garantias:
#   • age só sobre a chave exata e só sobre valores antigos CONHECIDOS —
#     valor personalizado pelo titular é preservado;
#   • idempotente: rodar de novo não muda nada e sai 0;
#   • backup antes de escrever, com permissão 600 (o .env tem segredos);
#   • nunca reescreve o arquivo inteiro: sed pontual preserva comentários,
#     espaços em branco, ordem e demais variáveis;
#   • nunca imprime valor de variável — só o nome da chave e o modelo novo,
#     que não é segredo;
#   • --dry-run informa o que mudaria sem tocar no arquivo.
#
# Uso: bash scripts/migrar_env_obsoletos.sh [caminho/do/.env] [--dry-run]
set -euo pipefail

ENV_FILE="${1:-.env}"
if [ "${ENV_FILE}" = "--dry-run" ]; then
  ENV_FILE=".env"
  DRY_RUN=1
else
  DRY_RUN=0
fi
[ "${2:-}" = "--dry-run" ] && DRY_RUN=1

if [ ! -f "$ENV_FILE" ]; then
  echo "migrar_env: ${ENV_FILE} não existe — nada a migrar."
  exit 0
fi

BACKUP_FEITO=0

# Faz UM backup por execução, na primeira alteração efetiva.
backup_uma_vez() {
  [ "$BACKUP_FEITO" = "1" ] && return 0
  local destino="${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
  # umask 077 antes do cp: o backup carrega os mesmos segredos do .env e não
  # pode nascer legível para outros usuários da VPS.
  (umask 077 && cp "$ENV_FILE" "$destino")
  chmod 600 "$destino"
  echo "migrar_env: backup criado em ${destino} (permissão 600)"
  BACKUP_FEITO=1
}

# Escapa um valor LITERAL para uso como padrão de busca (BRE/ERE) e como
# delimitador `|` do sed. Sem isto, o "." de "llama-3.3" casaria qualquer char.
escapar_padrao() {
  printf '%s' "$1" | sed 's/[][\.*^$\/|&]/\\&/g'
}

# migrar_valor <CHAVE> <VALOR_ANTIGO_LITERAL> <VALOR_NOVO> <MOTIVO>
migrar_valor() {
  local chave="$1" antigo="$2" novo="$3" motivo="$4"
  local antigo_re
  antigo_re="$(escapar_padrao "$antigo")"
  # Ancorado no início da linha e no fim do valor, para não casar por prefixo
  # (OUTRO_GROQ_MODEL= não é GROQ_MODEL=) nem por valor parcial.
  if ! grep -qE "^${chave}=${antigo_re}[[:space:]]*$" "$ENV_FILE"; then
    return 0
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "migrar_env: [dry-run] ${chave} seria migrada para ${novo} (${motivo})"
    return 0
  fi
  backup_uma_vez
  local novo_esc
  novo_esc="$(printf '%s' "$novo" | sed 's/[\/|&]/\\&/g')"
  sed -i -E "s|^${chave}=${antigo_re}[[:space:]]*$|${chave}=${novo_esc}|" "$ENV_FILE"
  echo "migrar_env: ${chave} migrada para ${novo} (${motivo})"
}

# ── AI-043: llama-3.3-70b-versatile foi DEPRECIADO pela Groq. O substituto é o
# mesmo default de app/core/config.py e de .env.example (openai/gpt-oss-120b).
GROQ_MODELO_DEPRECIADO="llama-3.3-70b-versatile"
GROQ_MODELO_ATUAL="openai/gpt-oss-120b"
migrar_valor "GROQ_MODEL" "$GROQ_MODELO_DEPRECIADO" "$GROQ_MODELO_ATUAL" \
  "modelo Groq depreciado"
migrar_valor "GROQ_MODEL_LARGE" "$GROQ_MODELO_DEPRECIADO" "$GROQ_MODELO_ATUAL" \
  "modelo Groq depreciado"

# ── AI-033/AI-034: agente com ferramentas de ESCRITA ligado. Só AVISA —
# desligar em produção é decisão do titular, não do script de deploy.
if grep -qE '^AI_AGENT_ENABLED=true[[:space:]]*$' "$ENV_FILE"; then
  echo "migrar_env: ATENÇÃO — AI_AGENT_ENABLED=true (agente de IA com"
  echo "            ferramentas de ESCRITA habilitado). A auditoria de"
  echo "            2026-07-26 recomenda false até a homologação do HITL."
fi

if [ "$BACKUP_FEITO" = "0" ] && [ "$DRY_RUN" = "0" ]; then
  echo "migrar_env: nenhum valor obsoleto encontrado — ${ENV_FILE} preservado."
fi
exit 0
