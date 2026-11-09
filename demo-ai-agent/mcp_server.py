"""Phase 2: the database tool, now exposed as a standalone MCP server.

This is the same `run_read_query` logic from Phase 1 -- but instead of the
agent importing it as a local Python function, it now lives in its own process
and speaks the Model Context Protocol (MCP) over stdio. The agent becomes an
MCP *client* (see agent_mcp.py) and discovers/calls this tool over the wire.

Why this matters: this MCP boundary is the seam Teleport secures in Phase 4.
Today the connection from server -> RDS still uses the static password in .env;
later, the client -> server hop is routed through the Teleport proxy with a
short-lived identity, and that's the "zero-code MCP security" story.

FastMCP turns the type hints + docstring below into the tool's MCP schema
automatically -- we don't hand-write a JSON schema.
"""

import json

from mcp.server.fastmcp import FastMCP

from db import run_read_query as _db_query

mcp = FastMCP("orders-db")


@mcp.tool()
def run_read_query(sql: str) -> str:
    """Run a read-only SQL SELECT against the production 'opsdb' Postgres
    database and return matching rows as JSON.

    Table 'orders' columns: order_id, customer_email, status
    (completed|pending_payment|failed), amount_usd, payment_provider
    (stripe|paypal|legacy_gateway), checkout_duration_ms, created_at (timestamptz).

    Args:
        sql: A single SELECT statement.
    """
    rows = _db_query(sql)
    return json.dumps(rows, default=str)


if __name__ == "__main__":
    # Default transport is stdio: the client launches this file as a subprocess
    # and talks to it over stdin/stdout.
    mcp.run()
