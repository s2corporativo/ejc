#!/usr/bin/env bash
# EJC — auditoria dos vhosts do Nginx na VPS (somente leitura).
#
# PROBLEMA (auditoria de 27/07/2026): sites-enabled tinha DOIS vhosts para
# `ejc.depaulateixeira.adv.br` (`ejc` e `ejc.conf`) e dois para o Verde Limp
# (`verdelimp-erp` e `verdelimp-erp-s2`). Quando dois blocos `server` declaram
# o mesmo server_name na mesma porta, o Nginx usa o PRIMEIRO que carregar e
# ignora o outro em silêncio — dá para editar a config errada por semanas e
# concluir que "o deploy não pegou".
#
# Este script NÃO altera nada: aponta duplicatas, órfãos e destinos de proxy
# para que a consolidação seja uma decisão consciente. Com 3 sites novos a
# entrar, é o momento de acertar a base.
#
# Uso: sudo bash scripts/vps-nginx-auditoria.sh
set -euo pipefail

titulo() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
command -v nginx >/dev/null || { echo "nginx não encontrado." >&2; exit 2; }

CONF="$(nginx -T 2>/dev/null || true)"
[ -n "$CONF" ] || { echo "Falha ao ler a configuração (rode como root)." >&2; exit 2; }

titulo "Sintaxe"
nginx -t 2>&1 | sed 's/^/  /'

titulo "server_name declarados mais de uma vez (CONFLITO)"
# Um mesmo nome pode aparecer legitimamente 2x (porta 80 + 443). Acima disso,
# ou repetido no mesmo arquivo, é sinal de vhost duplicado.
printf '%s\n' "$CONF" \
  | awk '/server_name/ {for(i=2;i<=NF;i++){gsub(/;/,"",$i); if($i!="_" && $i!="") print $i}}' \
  | sort | uniq -c | sort -rn \
  | awk '$1>2 {printf "  %s vezes: %s\n", $1, $2; achou=1} END {if(!achou) print "  nenhum conflito evidente"}'

titulo "Arquivos habilitados"
for f in /etc/nginx/sites-enabled/*; do
  [ -e "$f" ] || continue
  alvo="$(readlink -f "$f" 2>/dev/null || echo "$f")"
  nomes="$(awk '/server_name/ {for(i=2;i<=NF;i++){gsub(/;/,"",$i); if($i!="") printf "%s ", $i}}' "$alvo" 2>/dev/null | tr ' ' '\n' | sort -u | tr '\n' ' ')"
  printf '  %-24s → %s\n' "$(basename "$f")" "${nomes:-(sem server_name)}"
done

titulo "Destinos de proxy_pass (para onde cada vhost aponta)"
printf '%s\n' "$CONF" | awk '
  /server_name/ {for(i=2;i<=NF;i++){gsub(/;/,"",$i); if($i!="" && $i!="_") nome=$i}}
  /proxy_pass/  {gsub(/;/,"",$2); printf "  %-42s → %s\n", nome, $2}
' | sort -u

titulo "Vhosts sem certificado TLS"
nomes_tls="$(certbot certificates 2>/dev/null | awk '/Domains:/ {for(i=2;i<=NF;i++) print $i}' | sort -u)"
printf '%s\n' "$CONF" \
  | awk '/server_name/ {for(i=2;i<=NF;i++){gsub(/;/,"",$i); if($i!="" && $i!="_" && $i !~ /^[0-9.]+$/) print $i}}' \
  | sort -u | while read -r nome; do
      printf '%s\n' "$nomes_tls" | grep -qx "$nome" || echo "  sem cert: $nome"
    done

titulo "Certificados perto do vencimento (< 30 dias)"
certbot certificates 2>/dev/null \
  | awk '/Certificate Name:/{n=$3} /Expiry Date:/{if (match($0,/VALID: ([0-9]+) days/,m) && m[1]<30) printf "  %s vence em %s dias\n", n, m[1]}' \
  || echo "  certbot indisponível"

cat <<'NOTA'

Como consolidar um vhost duplicado com segurança:
  1. Descubra qual está valendo:  nginx -T | grep -n -A5 'server_name <dominio>'
     (o primeiro bloco carregado é o que responde)
  2. Guarde o descartado:         mv /etc/nginx/sites-available/<arquivo> /root/nginx-baixados/
  3. Remova só o symlink:         rm /etc/nginx/sites-enabled/<arquivo>
  4. Valide ANTES de recarregar:  nginx -t
  5. Recarregue sem downtime:     systemctl reload nginx
Nunca use `nginx -s stop`/restart para isso: reload troca a config sem derrubar
conexões em curso.
NOTA
