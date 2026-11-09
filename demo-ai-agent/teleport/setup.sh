#!/usr/bin/env bash
# Phase 4 wiring -- run AFTER you've signed up for Teleport Cloud and done
#   tsh login --proxy=<tenant>.teleport.sh
# from this same machine (so tctl can use your logged-in admin identity).
#
# Usage:  ./teleport/setup.sh <tenant>.teleport.sh
#
# It is idempotent-ish: re-running re-creates the role and mints fresh tokens.
set -euo pipefail

TENANT="${1:?Usage: ./teleport/setup.sh <tenant>.teleport.sh}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

echo "==> Tenant: $TENANT"
echo "==> Checking you're logged in (tctl status)..."
tctl status >/dev/null

# 1) Least-privilege role for the agent identity.
echo "==> Creating/updating role agent-db-readonly"
tctl create -f role-agent-db-readonly.yaml

# 2) Join token for the Database Service, render its config from the template.
echo "==> Minting Database Service join token"
DB_TOKEN="$(tctl tokens add --type=db --ttl=1h --format=text)"
sed -e "s|__TENANT__|${TENANT}|g" -e "s|__DB_TOKEN__|${DB_TOKEN}|g" \
    teleport-db.yaml.tmpl > teleport-db.yaml
echo "    wrote teleport-db.yaml"

# 3) Bot + its join token, render tbot config from the template.
echo "==> Creating bot 'agent-bot' (role: agent-db-readonly)"
# Remove a pre-existing bot of the same name so re-runs are clean.
tctl bots rm agent-bot >/dev/null 2>&1 || true
BOT_TOKEN="$(tctl bots add agent-bot --roles=agent-db-readonly --format=json \
             | python3 -c 'import sys,json; print(json.load(sys.stdin)["token_id"])')"
sed -e "s|__TENANT__|${TENANT}|g" -e "s|__BOT_TOKEN__|${BOT_TOKEN}|g" \
    tbot.yaml.tmpl > tbot.yaml
echo "    wrote tbot.yaml"

cat <<EOF

==> Done generating config. Next, in TWO separate terminals:

  Terminal A  (Database Service -- registers RDS with Teleport):
    teleport start --config "$HERE/teleport-db.yaml"

  Terminal B  (Machine ID -- issues the agent its short-lived identity +
               opens the local DB tunnel on 127.0.0.1:5433):
    tbot start -c "$HERE/tbot.yaml"

  Then verify the database shows up:
    tsh db ls

  And run the agent the Teleport way (no password):
    cd "$HERE/.." && USE_TELEPORT=true .venv/bin/python agent_mcp.py
EOF
