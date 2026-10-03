#!/bin/bash
cd /home/z/my-project
while true; do
  if ! pgrep -f "next-server" > /dev/null 2>&1; then
    echo "[$(date)] starting next dev..." >> dev-keepalive.log
    nohup setsid /home/z/my-project/node_modules/.bin/next dev -p 3000 -H 0.0.0.0 > dev.log 2>&1 < /dev/null &
    disown
    sleep 8
  else
    sleep 5
  fi
done
