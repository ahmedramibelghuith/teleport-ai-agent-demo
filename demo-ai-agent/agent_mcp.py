"""Phase 2: the same SRE agent, but now an MCP client.

What changed from agent.py (Phase 1):
  - Phase 1 called a local Python function (db.run_read_query) directly.
  - Phase 2 launches mcp_server.py, asks it "what tools do you have?"
    (list_tools), and routes every tool call over the MCP protocol
    (call_tool). The agent no longer imports the database code at all.

The Bedrock reasoning loop is identical -- only the tool *transport* changed.
MCP is async, so the loop is written with asyncio.
"""

import asyncio
import json
import os
import sys

import boto3
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
HERE = os.path.dirname(os.path.abspath(__file__))

bedrock = boto3.client("bedrock-runtime", region_name=REGION)

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


async def run_agent(user_prompt: str):
    # Launch the MCP server as a subprocess and connect to it over stdio.
    server = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(HERE, "mcp_server.py")],
        cwd=HERE,
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Tool discovery over MCP -- the agent doesn't hard-code the tools.
            listed = await session.list_tools()
            tools = to_bedrock_tools(listed.tools)
            names = [t["toolSpec"]["name"] for t in tools]
            print(f"🔌 Connected to MCP server 'orders-db'. Discovered tools: {names}")

            messages = [{"role": "user", "content": [{"text": user_prompt}]}]
            print(f"\n👤 {user_prompt}")

            while True:
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
                        print(f"\n🤖 {block['text']}")

                if resp["stopReason"] != "tool_use":
                    break

                tool_results = []
                for block in reply["content"]:
                    if "toolUse" not in block:
                        continue
                    tool_use = block["toolUse"]
                    sql = tool_use["input"].get("sql", "")
                    print(f"\n🔧 (via MCP) {tool_use['name']}:\n   {sql}")

                    # The tool call now travels over the MCP protocol.
                    result = await session.call_tool(tool_use["name"], tool_use["input"])
                    text = "".join(
                        block.text for block in result.content if hasattr(block, "text")
                    )
                    status = "error" if result.isError else "success"
                    print(f"   → {status}")

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


if __name__ == "__main__":
    asyncio.run(
        run_agent(
            "Checkout has felt slow in the last hour. Investigate the orders "
            "database and tell me the most likely root cause."
        )
    )
