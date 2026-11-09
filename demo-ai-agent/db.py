"""Database access helper.

Two connection modes, chosen by the USE_TELEPORT env flag -- this is the
comparison between connection approaches:

  USE_TELEPORT unset/false  -> THE WRONG WAY
      Connect DIRECTLY to RDS using the long-lived master password from .env.
      Static, never-expiring, publicly-reachable -- the anti-pattern we call out.

  USE_TELEPORT=true          -> THE TELEPORT WAY
      Connect to a local port that Machine ID (tbot) opens and routes through
      the Teleport identity-aware proxy. The credential is a short-lived,
      auto-renewing certificate held by tbot -- the app sends NO password and
      writes NO authorization code. Access (read-only, this DB only) is enforced
      by Teleport policy, not by hopeful string checks in this file.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def _use_teleport() -> bool:
    return os.environ.get("USE_TELEPORT", "").lower() in ("1", "true", "yes")


def get_connection():
    if _use_teleport():
        # tbot's database-tunnel listens here and owns the (short-lived) identity.
        # No password, no master user -- we present the agent's own identity as
        # the read-only Postgres user, through the Teleport proxy.
        return psycopg2.connect(
            host="127.0.0.1",
            port=os.environ.get("TELEPORT_DB_PORT", "5433"),
            dbname=os.environ.get("DB_NAME", "opsdb"),
            user=os.environ.get("TELEPORT_DB_USER", "readonly_agent"),
            sslmode="disable",   # local hop to tbot; tbot does mTLS upstream
            connect_timeout=30,  # first connect warms the tunnel/cert (cold start)
        )

    # The wrong way: static master password straight to a public RDS endpoint.
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=10,
    )


def run_read_query(sql: str, max_rows: int = 100):
    """Execute a single read-only SELECT and return rows as a list of dicts.

    Phase-1 guardrail: we reject anything that isn't a SELECT. This is fragile
    (string checks are easy to fool) -- it's the motivation for enforcing access
    at the identity layer with Teleport. With USE_TELEPORT=true, even if this
    check were bypassed, the readonly_agent identity simply cannot write.
    """
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned.lower().startswith("select"):
        raise ValueError("Only read-only SELECT queries are allowed.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(cleaned)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows)
    return [dict(zip(columns, row)) for row in rows]
