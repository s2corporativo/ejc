#!/bin/bash
cd /home/ubuntu/ejc/backend
( set -a && source ../.env && set +a && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 & )
sleep 12
TOK=$(curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@seu-dominio.com.br","password":"TROCAR_POR_SENHA_FORTE_INICIAL"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
for i in $(seq 1 25); do
  curl -s -o /dev/null -H "Authorization: Bearer $TOK" "http://localhost:8000/api/clients/?search=TESTE_EJC_AUDITORIA_2026"
  sleep 1
done
for t in $(seq 1 18); do
  sleep 10
  RS=$(ps -eo rss,pid,cmd --sort=-rss 2>/dev/null | grep 'uvicorn app' | grep -v grep | awk '{printf "%.0f", $1/1024}')
  echo "t+${t}0s rss=${RS:-DEAD}MB avail=$(free -m | awk 'NR==2{print $7}')"
  [ -z "$RS" ] && break
done
