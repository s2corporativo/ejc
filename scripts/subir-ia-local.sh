#!/usr/bin/env bash
# subir-ia-local.sh — liga o profile "ia-local" (Ollama) do EJC em 1 comando.
#
# O que faz, na ordem:
#   1. sobe o serviço `ollama` (docker compose --profile ia-local) e espera
#      o healthcheck ficar healthy
#   2. roda o one-shot `ollama-init`, que baixa os modelos de
#      OLLAMA_PULL_MODELS (.env; default: deepseek-r1:8b,qwen2.5:14b,gemma3:9b)
#      — em ATTACHED mode, então dá para acompanhar o progresso do download
#   3. lista os modelos instalados como prova final
#
# Idempotente: rodar de novo só confere digests (pull de modelo baixado é
# no-op rápido). Requisitos de RAM por modelo: ver .env.example (perfis
# prontos para VPS 8GB e servidor 16GB+). Com Ollama fora do ar o backend
# NÃO quebra — a cadeia de IA cai para Anthropic/Groq automaticamente.
#
# Verificação depois de subir:
#   docker compose exec ollama ollama list
#   POST /api/ai/gateway/health (admin) — mostra o status de cada provedor.
set -euo pipefail
cd "$(dirname "$0")/.."

log() { printf '\n===== %s =====\n' "$*"; }
die() { printf '\n[ERRO] %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "docker nao instalado"
docker compose version >/dev/null 2>&1 || die "plugin docker compose ausente"
[ -f .env ] || die ".env ausente em $(pwd) (copie de .env.example)"

log "1/3 Subindo o servico ollama (profile ia-local)"
docker compose --profile ia-local up -d ollama
OID="$(docker compose --profile ia-local ps -q ollama)"
ST=starting
for i in $(seq 1 18); do
  ST="$(docker inspect --format '{{.State.Health.Status}}' "$OID" 2>/dev/null || echo starting)"
  echo "  aguardando ollama: tentativa $i/18 -> $ST"
  [ "$ST" = healthy ] && break
  [ "$ST" = unhealthy ] && break
  sleep 10
done
[ "$ST" = healthy ] || die "ollama terminou como '$ST' (docker logs ejc_ollama)"

log "2/3 Baixando os modelos (ollama-init) — pode demorar na 1a vez"
# `run --rm` em vez de `up --exit-code-from`: este último implica
# --abort-on-container-exit e, em algumas versões do compose, PARA o serviço
# ollama quando o init sai. `run --rm` roda o one-shot attached (progresso
# visível) sem tocar no serviço, e propaga o exit code do init.
docker compose --profile ia-local run --rm ollama-init \
  || die "ollama-init falhou em ao menos um modelo (log acima)"

log "3/3 Modelos instalados"
docker compose --profile ia-local exec ollama ollama list

printf '\n[SUCESSO] IA local no ar. O backend usa http://ollama:11434 automaticamente;\n'
printf 'se o Ollama cair/ficar lento, a cadeia volta para Anthropic/Groq sozinha.\n'
printf 'Status por provedor: POST /api/ai/gateway/health (como admin).\n'
