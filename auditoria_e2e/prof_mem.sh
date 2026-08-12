#!/bin/bash
# monitor uvicorn memory growth
cd /home/ubuntu/ejc/backend
( set -a && source ../.env && set +a && nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 & )
sleep 12
echo "mem after boot: $(ps -eo rss,pid,cmd --sort=-rss | grep uvicorn | grep -v grep | awk '{printf "%.0fMB", $1/1024}')"
for i in $(seq 1 18); do
  sleep 10
  RS=$(ps -eo rss,pid,cmd --sort=-rss 2>/dev/null | grep 'uvicorn app' | grep -v grep | awk '{printf "%.0f", $1/1024}')
  echo "t=${i}0s rss=${RS:-DEAD}MB avail=$(free -m | awk 'NR==2{print $7}')"
  [ -z "$RS" ] && break
done
