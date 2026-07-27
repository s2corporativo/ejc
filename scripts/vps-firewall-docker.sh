#!/usr/bin/env bash
# EJC — fecha portas de containers expostas à internet.
#
# PROBLEMA (auditoria de 27/07/2026): o Docker publica portas escrevendo direto
# no iptables, ANTES e por fora do UFW. Um `ports: "5432:5432"` em compose — ou
# um service container do GitHub Actions — fica acessível ao mundo mesmo com o
# UFW "ativo" e negando tudo. Foi o caso do Postgres do CI (0.0.0.0:5432) e do
# sistema-s2 (0.0.0.0:8088) nesta VPS.
#
# SOLUÇÃO: a cadeia DOCKER-USER é avaliada antes das regras do próprio Docker e
# é o ponto de extensão oficial. Bloqueamos as portas sensíveis SOMENTE quando
# chegam pela interface externa; tráfego local e entre containers segue intacto.
#
# NÃO substitui o UFW (que protege serviços do host, como o SSH) — complementa.
#
# Uso:
#   sudo bash scripts/vps-firewall-docker.sh            # relatório (não altera)
#   sudo bash scripts/vps-firewall-docker.sh --apply    # aplica e persiste
#   PORTAS="5432 3306 8088" sudo bash ... --apply       # lista customizada
set -euo pipefail

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

# Bancos e serviços internos que NUNCA devem responder na internet.
# 80/443 (Nginx) e 22 (SSH) ficam de fora de propósito: são o acesso legítimo.
PORTAS="${PORTAS:-5432 3306 33060 6379 6380 27017 8088 8081 3000 3001 3011}"

titulo() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

[ "$(id -u)" -eq 0 ] || { echo "Execute como root (sudo)." >&2; exit 2; }
command -v iptables >/dev/null || { echo "iptables ausente." >&2; exit 2; }

# Interface que fala com a internet — as regras valem só para ela, de modo que
# loopback e as bridges do Docker (comunicação entre containers) não são afetados.
_detectar_iface() {
  command -v ip >/dev/null 2>&1 || return 0
  ip route get 1.1.1.1 2>/dev/null \
    | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}' || true
}
IFACE="${IFACE:-$(_detectar_iface)}"
if [ -z "$IFACE" ]; then
  echo "Não foi possível detectar a interface externa." >&2
  echo "Informe manualmente:  IFACE=eth0 sudo bash $0 --apply" >&2
  exit 2
fi

titulo "Contexto"
echo "  interface externa: $IFACE"
echo "  portas protegidas: $PORTAS"

# A cadeia existe assim que o Docker sobe; criamos se preciso (idempotente).
if ! iptables -L DOCKER-USER -n >/dev/null 2>&1; then
  echo "  DOCKER-USER ausente — criando"
  [ "$APPLY" = "1" ] && { iptables -N DOCKER-USER 2>/dev/null || true; \
                          iptables -I FORWARD -j DOCKER-USER 2>/dev/null || true; }
fi

titulo "Portas de container publicadas em 0.0.0.0 (expostas hoje)"
docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null \
  | grep -E '0\.0\.0\.0|\[::\]' || echo "  nenhuma — bom sinal"

titulo "Regras"
for porta in $PORTAS; do
  # -C testa se a regra já existe: rodar de novo não duplica nada.
  if iptables -C DOCKER-USER -i "$IFACE" -p tcp --dport "$porta" -j DROP 2>/dev/null; then
    echo "  já protegida: $porta"
    continue
  fi
  if [ "$APPLY" = "1" ]; then
    iptables -I DOCKER-USER -i "$IFACE" -p tcp --dport "$porta" -j DROP
    echo "  → bloqueada: $porta (externa)"
  else
    echo "  [dry-run] bloquear $porta vinda de $IFACE"
  fi
done

if [ "$APPLY" = "1" ]; then
  titulo "Persistência (sobrevive a reboot)"
  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save && echo "  salvo via netfilter-persistent"
  else
    echo "  ⚠ iptables-persistent não instalado — as regras se perdem no reboot."
    echo "    Instale com: apt-get install -y iptables-persistent"
  fi

  titulo "Verificação"
  iptables -L DOCKER-USER -n --line-numbers | head -20
else
  printf '\nNada foi alterado. Para aplicar: sudo bash %s --apply\n' "$0"
fi

cat <<'NOTA'

Depois de aplicar, confirme de FORA da VPS (outra máquina/celular):
    nc -zv <IP_PUBLICO> 5432     # deve dar timeout/refused
    curl -I https://<seu-dominio> # deve continuar respondendo 200/301

Se algum serviço legítimo depender de acesso externo direto a uma dessas
portas, remova-a de PORTAS em vez de desativar o script inteiro — e prefira
expor via Nginx com TLS a abrir a porta do banco.
NOTA
