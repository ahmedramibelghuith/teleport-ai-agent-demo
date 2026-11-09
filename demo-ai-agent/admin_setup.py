"""One-off admin script (run as the RDS master `postgres` user) to create the
least-privilege identity the agent will use THROUGH Teleport in Phase 4.

Creates `readonly_agent`:
  - LOGIN role, no password (authenticates via RDS IAM / Teleport short-lived token)
  - rds_iam membership so RDS accepts IAM auth tokens for it
  - SELECT-only on the orders table -- nothing else

This is the Postgres-side half of "least privilege": Teleport's role limits the
agent to logging in *as this user*, and this user can only read. Re-runnable.
"""

import sys
from db import get_connection


STATEMENTS = [
    # Create the role if it doesn't already exist (idempotent).
    """DO $$
       BEGIN
         IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_agent') THEN
           CREATE ROLE readonly_agent WITH LOGIN;
         END IF;
       END
       $$;""",
    # Let RDS accept IAM auth tokens for this role (passwordless).
    "GRANT rds_iam TO readonly_agent;",
    # Minimal read path to the orders table only.
    "GRANT CONNECT ON DATABASE opsdb TO readonly_agent;",
    "GRANT USAGE ON SCHEMA public TO readonly_agent;",
    "GRANT SELECT ON public.orders TO readonly_agent;",
    # Make sure nothing broader is lingering.
    "REVOKE CREATE ON SCHEMA public FROM readonly_agent;",
]


def main():
    conn = get_connection()
    conn.autocommit = True
    with conn.cursor() as cur:
        for stmt in STATEMENTS:
            cur.execute(stmt)
            print("OK:", " ".join(stmt.split())[:70])
        # Show what the role can touch, for the record.
        cur.execute(
            """SELECT grantee, privilege_type, table_name
               FROM information_schema.role_table_grants
               WHERE grantee = 'readonly_agent';"""
        )
        print("\nGrants for readonly_agent:")
        for row in cur.fetchall():
            print("  ", row)
        cur.execute(
            "SELECT g.rolname FROM pg_roles r "
            "JOIN pg_auth_members m ON m.member = r.oid "
            "JOIN pg_roles g ON g.oid = m.roleid "
            "WHERE r.rolname = 'readonly_agent' AND g.rolname = 'rds_iam';"
        )
        print("rds_iam membership:", "yes" if cur.fetchone() else "NO")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
