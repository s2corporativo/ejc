#!/bin/sh
set -eu
for status in exited dead; do
  ids=$(docker ps -aq --filter "status=$status" --filter "name=wp_")
  [ -z "$ids" ] || docker rm $ids >/dev/null 2>&1 || true
done
