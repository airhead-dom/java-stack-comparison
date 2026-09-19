#!/usr/bin/env bash
# Bring up everything a run needs: Postgres (seeded) and stub-service.
# Idempotent -- safe to re-run.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "==> Postgres"
docker compose -f "$ROOT/infra/docker-compose.yml" up -d postgres >/dev/null
echo -n "    seeding (first start takes ~2.5 min) "
for _ in $(seq 1 90); do
  n=$(docker exec infra-postgres-1 psql -U bench -d bench -tAc \
        "select count(*) from transactions" 2>/dev/null || echo 0)
  if [ "${n:-0}" -ge 2600000 ] 2>/dev/null; then echo " ok ($n transactions)"; break; fi
  echo -n "."; sleep 5
done

echo "==> stub-service"
if curl -sf "$STUB_URL/actuator/health" >/dev/null 2>&1; then
  echo "    already running"
else
  jar="$ROOT/stub-service/build/libs/stub-service-0.0.1-SNAPSHOT.jar"
  [ -f "$jar" ] || die "missing $jar -- run ./gradlew bootJar"
  nohup "$JAVA_BIN" -jar "$jar" > "$ROOT/results/stub.log" 2>&1 &
  wait_healthy "$STUB_URL" 60 || die "stub-service failed to start; see results/stub.log"
  echo "    started on $STUB_URL"
fi

echo "==> ready. Run a cell with: scripts/run-one.sh <variant> <workload> <rate>"
