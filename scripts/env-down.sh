#!/usr/bin/env bash
# Stop everything. Pass --purge to also delete the seeded database.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "==> stopping JVMs"
if command -v taskkill >/dev/null 2>&1; then
  taskkill //F //IM java.exe //T >/dev/null 2>&1 || true
else
  pkill -f 'benchmark|stub-service|mvc-|webflux-' 2>/dev/null || true
fi

if [ "${1:-}" = "--purge" ]; then
  echo "==> removing Postgres AND its data (next start re-seeds, ~2.5 min)"
  docker compose -f "$ROOT/infra/docker-compose.yml" down -v >/dev/null
else
  echo "==> stopping Postgres, keeping data"
  docker compose -f "$ROOT/infra/docker-compose.yml" stop >/dev/null
fi
echo "==> done"
