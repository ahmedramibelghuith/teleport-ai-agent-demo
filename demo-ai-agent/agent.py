"""Step 3: a minimal AI SRE agent that can call a tool.

The loop is the whole idea behind an "agent":
  1. We send the user's question + a list of tools the model may use.
  2. The model either answers, or asks to call a tool (stopReason == 'tool_use').
  3. If it asks for a tool, WE run it, hand back the result, and loop.
  4. It keeps going until it has enough to answer.

No agent framework -- just the Bedrock Converse API and a while loop, so you
can see exactly what's happening. (MCP comes in Phase 2; Teleport in Phase 4.)
"""

import json
import os

import boto3
from dotenv import load_dotenv

from db import run_read_query

load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-south-1")
MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

client = boto3.client("bedrock-runtime", region_name=REGION)

# The tool contract we expose to the model. The description is the model's only
# documentation, so it spells out the table and columns it can query.
TOOLS = [
    {
        "toolSpec": {
            "name": "run_read_query",
            "description": (
                "Run a read-only SQL SELECT against the production 'opsdb' "
                "Postgres database and return matching rows as JSON. "
                "Table 'orders' columns: order_id, customer_email, status "
                "(completed|pending_payment|failed), amount_usd, "
                "payment_provider (stripe|paypal|legacy_gateway), "
                "checkout_duration_ms, created_at (timestamptz)."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "A single SELECT statement.",
                        }
                    },
                    "required": ["sql"],
                }
            },
        }
    }
]

SYSTEM = [
    {
        "text": (
            "You are an SRE assistant investigating a production incident. "
            "Use the run_read_query tool to inspect the orders database: form a "
            "hypothesis, query to confirm it, and iterate. When you have enough "
            "evidence, give a concise root-cause diagnosis with the numbers that "
            "support it. Keep queries read-only."
        )
    }
]


def _json_safe(value):
    # Decimals and datetimes from Postgres aren't JSON-serializable by default.
    return str(value)


def run_agent(user_prompt: str):
    messages = [{"role": "user", "content": [{"text": user_prompt}]}]
    print(f"\n👤 {user_prompt}")

    while True:
        resp = client.converse(
            modelId=MODEL_ID,
            system=SYSTEM,
            messages=messages,
            toolConfig={"tools": TOOLS},
            inferenceConfig={"maxTokens": 1500, "temperature": 0},
        )
        reply = resp["output"]["message"]
        messages.append(reply)

        for block in reply["content"]:
            if "text" in block and block["text"].strip():
                print(f"\n🤖 {block['text']}")

        if resp["stopReason"] != "tool_use":
            break

        # Run every tool the model asked for, then feed results back in.
        tool_results = []
        for block in reply["content"]:
            if "toolUse" not in block:
                continue
            tool_use = block["toolUse"]
            sql = tool_use["input"]["sql"]
            print(f"\n🔧 run_read_query:\n   {sql}")
            try:
                rows = run_read_query(sql)
                payload = json.dumps(rows, default=_json_safe)
                status = "success"
                print(f"   → {len(rows)} row(s)")
            except Exception as exc:  # surfaced back to the model so it can recover
                payload = json.dumps({"error": str(exc)})
                status = "error"
                print(f"   → error: {exc}")
            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"text": payload}],
                        "status": status,
                    }
                }
            )
        messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    run_agent(
        "Checkout has felt slow in the last hour. Investigate the orders "
        "database and tell me the most likely root cause."
    )
