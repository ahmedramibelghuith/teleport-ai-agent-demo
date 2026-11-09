"""Step 1: prove we can talk to Claude on Amazon Bedrock.

No tools, no agent loop yet -- just a single round-trip to the model.
We use the Bedrock *Converse* API: one clean, model-agnostic way to send
messages and (later) declare tools. Credentials/region come from your
normal AWS config, so there's nothing secret in this file.
"""

import boto3
from botocore.exceptions import ClientError

REGION = "ap-south-1"
# Newer Claude models on Bedrock require a cross-region *inference profile*,
# not the bare model ID. Opus 4.5 is the current (non-legacy) model with an
# ACTIVE profile in this account/region; it uses a "global." profile.
MODEL_ID = "global.anthropic.claude-opus-4-5-20251101-v1:0"

client = boto3.client("bedrock-runtime", region_name=REGION)


def ask(prompt: str) -> str:
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0.2},
    )
    return resp["output"]["message"]["content"][0]["text"]


if __name__ == "__main__":
    try:
        answer = ask("In one sentence, what is an AI agent that can call tools?")
        print("\n✅ Bedrock is talking to us:\n")
        print(answer)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        print(f"\n❌ Bedrock call failed: {code}\n{e}\n")
        if "AccessDenied" in code or "AccessDenied" in str(e):
            print("→ Likely: model access for this Claude model isn't enabled yet.")
            print("  Enable it in the Bedrock console → Model access (ap-south-1).")
        elif "ValidationException" in code and "on-demand" in str(e).lower():
            print("→ This model needs an inference profile. Try MODEL_ID = 'apac.anthropic.claude-sonnet-4-6'")
