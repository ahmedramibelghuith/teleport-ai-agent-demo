#!/usr/bin/env bash
# Launch the AI SRE Agent demo UI.
# Needs the Teleport tunnel running for the secure path:
#   teleport start --config ./teleport/teleport-db.yaml   (terminal A)
#   tbot start -c ./teleport/tbot.yaml                     (terminal B)
cd "$(dirname "$0")"
exec .venv/bin/streamlit run app.py "$@"
