# Complete Architecture & Request Flow — AI SRE Agent secured by Teleport

End-to-end: from typing a question in the UI to the answer coming back, with every
component, file, and YAML we built. Use this as the architecture reference.

---

## The request flow (one question → one answer)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  YOUR MAC  (everything local except Bedrock, Teleport Cloud, AWS)               │
│                                                                                 │
│   (1) type incident in chat box            (17) right panel (live):             │
│        "checkout is slow…"                       • cert expiry countdown        │
│            │                                     • "Try admin" → DENIED          │
│            ▼                                     • audit link                    │
│   ┌────────────────────┐  Streamlit ────────────────────┐                       │
│   │   app.py   (UI)    │                                 │                       │
│   └─────────┬──────────┘                                 │                       │
│             │ (2) iter_agent_events(prompt, use_teleport=True)                   │
│             ▼                                                                    │
│   ┌────────────────────┐   (4) prompt + tool schema    ☁  AMAZON BEDROCK        │
│   │   agent_core.py    │ ───────────────────────────►   (Claude Opus 4.5)       │
│   │  Bedrock + MCP      │ ◄───────────────────────────                          │
│   │  client loop        │   (5) "run this SQL"  (tool_use)                       │
│   └─────────┬──────────┘        ▲                                               │
│             │ (6) call_tool(sql) │ (15) result fed back, loop (4)–(12) ~8×       │
│             ▼  over MCP (stdio)  │                                               │
│   ┌────────────────────┐                                                         │
│   │   mcp_server.py    │  exposes the single tool: run_read_query               │
│   └─────────┬──────────┘                                                         │
│             ▼                                                                    │
│   ┌────────────────────┐  (7) USE_TELEPORT=true →                               │
│   │   db.py            │      connect 127.0.0.1:5433, user=readonly_agent,      │
│   └─────────┬──────────┘      NO password   (static-pw path is the "wrong way") │
│             │                                                                    │
│             ▼ (8) presents a SHORT-LIVED CERT (renewed every 5m)                │
│   ┌────────────────────┐   config: teleport/tbot.yaml                           │
│   │  tbot (Machine ID) │   identity: agent-bot   role: agent-db-readonly        │
│   │   :5433 readonly ✓ │   ← the agent's tunnel                                 │
│   │   :5434 postgres ✗ │   ← the "try to be super-user" tunnel (gets denied)    │
│   └─────────┬──────────┘                                                         │
│             ▼                                                                    │
│   ┌────────────────────┐   config: teleport/teleport-db.yaml                    │
│   │ teleport (DB svc)  │   registers RDS as a Teleport database (label env=demo)│
│   └─────────┬──────────┘                                                         │
└─────────────┼───────────────────────────────────────────────────────────────────┘
              │ (8) mTLS out to the cloud
              ▼
   ┌─────────────────────────────────┐        (13) db.session.query
   │  ☁  TELEPORT CLOUD              │ ─────────►  AUDIT LOG + SESSION RECORDING
   │  your-tenant.teleport.sh│             (tied to identity = agent-bot)
   │   • identity-aware PROXY        │
   │   • RBAC from the role:         │  (9) checks: read-only? db=opsdb?
   │       agent-db-readonly         │       db_user=readonly_agent?
   │   • audit + recording           │       → :5434 postgres request = ✗ DENIED
   └─────────────┬───────────────────┘
                 │ (10) forwards the connection (still as readonly_agent)
                 ▼
   ┌─────────────────────────────────┐
   │  ☁  AWS   (ap-south-1)          │
   │                                 │
   │  Teleport DB Service mints an   │  (10) IAM auth TOKEN (rds-db:connect),
   │  RDS IAM token  ───────────────►│        via AWS creds, over TLS — no password
   │                                 │
   │  ┌───────────────────────────┐  │
   │  │ RDS PostgreSQL            │  │  (11) runs the SELECT on `orders`
   │  │ teleport-demo-db          │  │        login = readonly_agent
   │  │ db = opsdb  ·  IAM auth ON │  │        (member of rds_iam, SELECT-only)
   │  │ SG: 5432 from your IP      │  │
   │  └───────────────────────────┘  │
   └─────────────────────────────────┘

(12) rows travel back the SAME path: RDS → DB svc → Teleport proxy → tbot → db.py
     → mcp_server → agent_core → (14) rendered as a live table in the UI
(16) once Claude is confident → final root-cause diagnosis streamed to the UI
```

---

## Component inventory (what each piece is)

### UI layer
| Component | Role |
|---|---|
| `app.py` | Streamlit chat UI + right-hand Teleport panel (identity/cert countdown, "Try admin → DENIED", Teleport↔static toggle, audit). |
| `run_ui.sh` | Launcher: `streamlit run app.py`. |

### Agent / Python layer
| Component | Role |
|---|---|
| `agent_core.py` | The brains of the loop: Bedrock **Converse** + **MCP client**. `iter_agent_events()` streams events to the UI (runs the async MCP loop on a bg thread+queue). |
| `mcp_server.py` | **MCP server** exposing one tool, `run_read_query` (the seam Teleport secures). |
| `db.py` | DB connection helper. `USE_TELEPORT` toggle: static password → RDS (wrong way) **vs** `127.0.0.1:5433` tbot tunnel, no password (right way). |
| `agent_mcp.py` / `agent.py` | Terminal versions (MCP client / Phase-1 local function) — kept for comparing the two approaches. |
| `seed.sql` / `seed.py` | Create the `orders` table + the planted incident (slow `legacy_gateway`). |
| `admin_setup.py` | One-time: create the least-privilege `readonly_agent` Postgres user (rds_iam member, SELECT-only). |

### LLM
| Component | Role |
|---|---|
| **Amazon Bedrock** | Claude Opus 4.5 (`global.anthropic.claude-opus-4-5-…`) — reasons and decides which SQL to run. Touches nothing itself. |

### Teleport layer
| Component | Role |
|---|---|
| **Teleport Cloud** tenant | Managed identity-aware **proxy + auth + audit** at `your-tenant.teleport.sh`. |
| `teleport/teleport-db.yaml` | **Database Service** config — registers RDS, connects to it via IAM auth. |
| `teleport/tbot.yaml` | **Machine ID** config — issues the agent (`agent-bot`) a short-lived identity; opens tunnels `:5433` (readonly, allowed) and `:5434` (postgres, denied). |
| `teleport/role-agent-db-readonly.yaml` | The **policy**: `db_users:[readonly_agent]`, `db_names:[opsdb]`, read-only. |
| `teleport/setup.sh` | Mints join tokens, renders the two configs, creates the role + bot. |
| `teleport start …` / `tbot start …` | The two running processes (DB service, Machine ID + tunnels). |

### AWS layer
| Component | Role |
|---|---|
| **RDS PostgreSQL** `teleport-demo-db` | The "production" DB (`opsdb`, `orders` table). **IAM auth enabled**. |
| **IAM** | `rds-db:connect` lets the DB Service mint short-lived RDS tokens; the `readonly_agent` Postgres user is a member of `rds_iam`. |
| **Security group** `sg-0123456789abcdef0` | Allows 5432 from your home IP only. |

---

## Build-time (one-time setup)  vs  Run-time (every question)

**Build-time (you do once via the Teleport Web UI):**
`admin_setup.py` (readonly_agent) · enroll RDS as a Teleport DB (→ `teleport-db.yaml`) ·
create the role (`role-agent-db-readonly.yaml`) · enroll the bot (→ `tbot.yaml`) ·
enable RDS IAM auth + the IAM permission.

**Run-time (happens on every question):** steps (1)–(17) above. The only long-running
processes are: the Streamlit UI, `teleport` (DB service), and `tbot` (identity + tunnel).

---

## The two security beats, located on the diagram
- **No static credential** — at step (7)/(8): `db.py` sends no password; tbot's short-lived
  cert does the auth, and even DB-service→RDS (step 10) is a short-lived IAM token.
- **Least privilege + denied** — at step (9): the `:5434` "be the postgres super-user"
  request is refused by the Teleport proxy before RDS is ever touched.
- **Audited** — at step (13): every query is logged as `db.session.query` under `agent-bot`.
