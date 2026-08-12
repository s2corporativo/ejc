#!/bin/bash
set -e
cd /home/ubuntu/ejc/backend
pkill -f 'uvicorn app.main' 2>/dev/null || true
sleep 2
( set -a && source ../.env && set +a && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 & )
sleep 15
for i in $(seq 1 20); do
  if curl -s -o /dev/null -f http://localhost:8000/api/docs; then
    echo "server up"
    break
  fi
  sleep 5
done
cd /home/ubuntu/ejc/auditoria_e2e
python3 testes_e2e.py > resultados_e2e_final.txt 2>&1
echo "=== resultado:"
grep -cE '^PASS' resultados_e2e_final.txt || true
grep -E '^FAIL|^ABORT' resultados_e2e_final.txt | cut -c1-170 || true
