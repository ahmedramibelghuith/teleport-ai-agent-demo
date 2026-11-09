# RESUME — AI SRE Agent demo (Teleport integration)

> Last worked: **2026-06-11**. This file = where we left off + how to restart fast.

> 🔑 **Teleport Cloud login (trial tenant):**
> ```bash
> tsh login --proxy=your-tenant.teleport.sh --user=your-user@example.com
> ```
> Web UI: https://your-tenant.teleport.sh/

---

## ⏱️ Tomorrow, start here (2-min checklist)

1. **Re-authorize your IP on the DB** (your home IP probably changed overnight, which
   will make the DB connection time out). Run:
   ```bash
   MYIP=$(curl -s https://checkip.amazonaws.com)
   aws ec2 authorize-security-group-ingress --region ap-south-1 \
     --group-id sg-0123456789abcdef0 --protocol tcp --port 5432 --cidr $MYIP/32
   # (harmless "already exists" error means your IP didn't change — ignore it)
   ```
2. **Sanity-check the pieces still work:**
   ```bash
   cd "$(dirname "$0")"            # the demo-ai-agent folder
   .venv/bin/python hello_bedrock.py   # Bedrock reachable?
   .venv/bin/python agent_mcp.py       # full MCP agent investigation
   ```
3. If Bedrock errors with "use case details" again, wait ~15 min (it should already
   be approved from yesterday).

---

## 🎯 The goal (one line)
Build an AI DevOps/SRE agent on AWS that investigates an incident by querying a real
database, then **plug in Teleport** so the agent uses a short-lived per-agent identity
instead of the static DB password.

## 🧭 Roadmap & status
| Phase | What | Status |
|---|---|---|
| 1 | Tool-calling agent (Bedrock Converse + a `while` loop) | ✅ done |
| 3 | Running against real **AWS RDS** Postgres | ✅ done (folded in early) |
| 2 | Tool moved into a standalone **MCP server**; agent is an **MCP client** | ✅ done |
| 4 | **Plug in Teleport** (tbot identity, route DB through proxy, audit) | ✅ BUILT & VERIFIED — see `PHASE4-SETUP.md` |

> ⚠️ **FULL TEARDOWN DONE 2026-06-12.** RDS `teleport-demo-db`, its security group, the
> `readonly_agent` user, and all local runtime state (`tbot-data/`, `db-service-data/`,
> rendered `teleport-db.yaml`/`tbot.yaml`, logs) were **deleted**. Kept: all code, the
> diagrams, the Streamlit UI, `teleport/role-*.yaml` + `*.tmpl` + `setup.sh`, the Teleport
> Cloud **tenant** and Bedrock access. Rebuild the database and update `.env` before running the demo.

**Phase 4 progress (2026-06-11):** AWS side done: RDS **IAM auth
enabled**, least-priv Postgres user **`readonly_agent`** created (`admin_setup.py`),
Teleport CLI **v18.8.3** installed, `db.py` given a `USE_TELEPORT` toggle, and all configs
staged under `teleport/` (`role-*.yaml`, `*.tmpl`, `setup.sh`). **Blocked only on the
interactive Teleport Cloud signup** — once `<tenant>.teleport.sh` exists and `tsh login`
is done, run `./teleport/setup.sh <tenant>` then follow `PHASE4-SETUP.md`.


---

## 📁 Files
| File | Role |
|---|---|
| `agent.py` | Phase 1 agent — calls the tool as a **local function**. Kept for comparing connection approaches. |
| `agent_mcp.py` | Phase 2 agent — **MCP client**. Launches the server, discovers tools, calls them over MCP. **This is the current main entry point.** |
| `mcp_server.py` | Phase 2 — the `run_read_query` tool as a standalone **MCP server** (stdio). The seam Teleport wraps in Phase 4. |
| `db.py` | DB connection + read-only query helper. 🔑 Currently uses the static RDS password from `.env` (deliberately the "wrong way" we fix with Teleport). |
| `seed.sql` / `seed.py` | Creates the `orders` table + the planted incident (slow `legacy_gateway` provider). Re-run `seed.py` to reset data. |
| `hello_bedrock.py` | Bedrock connectivity smoke test. |
| `.env` | Config + DB password (gitignored). |
| `flow-explained.html` | Layman browser diagram of the request flow (Brain/Messenger/Librarian/Cabinet, steps 0–7). Open with `open flow-explained.html`. |

## 🏗️ Architecture right now (Phase 2)
```
[you] → agent_mcp.py (MCP client) ⇄ Bedrock Claude Opus 4.5   (the "brain", reasons only)
                     │ MCP protocol
                     ▼
        mcp_server.py (MCP server / the tool) ──🔑 static pw──▶ RDS Postgres (orders table)
                     ▲
        Phase 4: Teleport proxy inserts on this hop; static pw → short-lived identity
```

---

## ☁️ AWS resources (ap-south-1 / Mumbai)
- **RDS instance:** `teleport-demo-db` · Postgres **16.14** · `db.t3.micro` · publicly accessible
  - Endpoint: `your-rds-endpoint.xxxx.ap-south-1.rds.amazonaws.com`
  - DB name `opsdb` · user `postgres` · password in `.env`
- **Security group:** `sg-0123456789abcdef0` — inbound 5432 from creator IP only (re-auth daily, see top)
- **Bedrock model:** `global.anthropic.claude-opus-4-5-20251101-v1:0` (set in `.env` as `BEDROCK_MODEL_ID`)

## 💸 COST REMINDER
RDS is billing ~**$0.40–0.50/day** while it runs. **Delete it after use:**
```bash
aws rds delete-db-instance --region ap-south-1 --db-instance-identifier teleport-demo-db \
  --skip-final-snapshot --delete-automated-backups
# then, after it's gone:
aws ec2 delete-security-group --region ap-south-1 --group-id sg-0123456789abcdef0
```

---

## 🪤 Gotchas we already solved
1. **Inference profiles are mandatory** — current Claude models reject the bare model ID
   on Bedrock; must use a profile (`global.` / `apac.` prefix).
2. **Older models are gated as "Legacy"** — Sonnet 4 was blocked because the account
   hadn't used it in 30 days. Opus 4.5 was the working current model.
3. **Anthropic "use case details" form** — one-time per-account gate in the Bedrock
   console (Model access page). Took ~10–15 min to propagate after submitting.
4. **RDS engine version** — `16.4` wasn't offered in ap-south-1; used `16.14`.
5. **AWS authentication** — use a dedicated IAM user or role with least-privilege permissions.
