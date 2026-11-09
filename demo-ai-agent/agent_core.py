"""Streaming core for the AI SRE agent, shared by the terminal script and the
Streamlit UI.

`run_agent_events()` is the same Bedrock + MCP reason->tool->observe loop as
agent_mcp.py, but instead of printing it **yields structured events** so a UI can
render each reasoning step and each SQL tool-call live as it happens:

    {"type": "connected", "tools": [...]}
    {"type": "text", "text": "..."}                 # agent reasoning
    {"type": "tool_call", "name": "...", "sql": "..."}
    {"type": "tool_result", "status": "success|error", "rows": [...], "text": "..."}
    {"type": "final"}

The `use_teleport` flag is passed straight through to the MCP server's
environment, so the UI can flip between the static-password path and the
Teleport short-lived-identity path with one toggle.
"""

import json
import os
import queue
import sys
import threading

import boto3
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
HERE = os.path.dirname(os.path.abspath(__file__))

SYSTEM = [
    {
        "text": (
            "You are an SRE assistant investigating a production incident. "
            "Use the available tools to inspect the orders database: form a "
            "hypothesis, query to confirm it, and iterate. When you have enough "
            "evidence, give a concise root-cause diagnosis with the numbers that "
            "support it. Keep queries read-only."
        )
    }
]


def to_bedrock_tools(mcp_tools):
    """Translate MCP tool definitions into Bedrock Converse toolConfig format."""
    return [
        {
            "toolSpec": {
                "name": t.name,
                "description": t.description,
                "inputSchema": {"json": t.inputSchema},
            }
        }
        for t in mcp_tools
    ]


async def run_agent_events(user_prompt: str, use_teleport: bool = True, max_steps: int = 12):
    """Async generator: drive the agent loop, yielding UI events."""
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)

    # Pass the connection mode down to the MCP server subprocess (db.py reads it).
    env = dict(os.environ)
    env["USE_TELEPORT"] = "true" if use_teleport else "false"

    server = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(HERE, "mcp_server.py")],
        cwd=HERE,
        env=env,
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            tools = to_bedrock_tools(listed.tools)
            yield {"type": "connected", "tools": [t["toolSpec"]["name"] for t in tools]}

            messages = [{"role": "user", "content": [{"text": user_prompt}]}]

            for _ in range(max_steps):
                resp = bedrock.converse(
                    modelId=MODEL_ID,
                    system=SYSTEM,
                    messages=messages,
                    toolConfig={"tools": tools},
                    inferenceConfig={"maxTokens": 1500, "temperature": 0},
                )
                reply = resp["output"]["message"]
                messages.append(reply)

                for block in reply["content"]:
                    if "text" in block and block["text"].strip():
                        yield {"type": "text", "text": block["text"].strip()}

                if resp["stopReason"] != "tool_use":
                    yield {"type": "final"}
                    return

                tool_results = []
                for block in reply["content"]:
                    if "toolUse" not in block:
                        continue
                    tool_use = block["toolUse"]
                    sql = tool_use["input"].get("sql", "")
                    yield {"type": "tool_call", "name": tool_use["name"], "sql": sql}

                    result = await session.call_tool(tool_use["name"], tool_use["input"])
                    text = "".join(
                        b.text for b in result.content if hasattr(b, "text")
                    )
                    status = "error" if result.isError else "success"

                    rows = None
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, list):
                            rows = parsed
                    except (ValueError, TypeError):
                        pass

                    yield {
                        "type": "tool_result",
                        "status": status,
                        "text": text,
                        "rows": rows,
                        "sql": sql,
                    }

                    tool_results.append(
                        {
                            "toolResult": {
                                "toolUseId": tool_use["toolUseId"],
                                "content": [{"text": text}],
                                "status": status,
                            }
                        }
                    )
                messages.append({"role": "user", "content": tool_results})

            yield {"type": "final"}


def iter_agent_events(user_prompt: str, use_teleport: bool = True):
    """Synchronous generator wrapper for non-async callers (e.g. Streamlit).

    The async agent (and its MCP stdio task group) runs to completion inside a
    single `asyncio.run` on a background thread; events are streamed back over a
    thread-safe queue. Running the whole async context in one task avoids
    anyio's 'cancel scope in a different task' error you'd hit if you stepped the
    async generator across multiple event-loop calls.
    """
    import asyncio

    q: "queue.Queue" = queue.Queue()
    SENTINEL = object()

    def worker():
        async def consume():
            async for ev in run_agent_events(user_prompt, use_teleport):
                q.put(ev)

        try:
            asyncio.run(consume())
        except Exception as e:  # surface failures to the UI instead of hanging
            q.put({"type": "error", "text": f"{type(e).__name__}: {e}"})
        finally:
            q.put(SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        ev = q.get()
        if ev is SENTINEL:
            break
        yield ev
