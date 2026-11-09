"""Create and populate the demo 'orders' table by running seed.sql."""

from db import get_connection

with open("seed.sql") as f:
    sql = f.read()

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute("SELECT count(*) FROM orders;")
        total = cur.fetchone()[0]
    conn.commit()

print(f"✅ Seeded opsdb: {total} rows in 'orders'.")
