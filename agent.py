"""
Network Analyzer - AgentCore Entry Point

Deploy:
  agentcore configure -e agent.py
  agentcore deploy

Test locally:
  python agent.py                          (starts HTTP server on :8080)
  agentcore invoke --local '{"prompt": "Why can't 10.0.1.50 reach 10.0.2.100 on port 3306?"}'
"""
import os
from dotenv import load_dotenv

# Load .env before importing agents — they read env vars at module init time.
load_dotenv(override=False)

from bedrock_agentcore.runtime import BedrockAgentCoreApp  # noqa: E402
from agents.orchestrator import orchestrator  # noqa: E402

app = BedrockAgentCoreApp()


def parse_event(event):
    """Parse a streaming event and return displayable text."""
    # Skip lifecycle events
    if any(key in event for key in ['init_event_loop', 'start', 'start_event_loop']):
        return ""

    # Text chunks from the model
    if 'data' in event and isinstance(event['data'], str):
        return event['data']

    # Tool use indicators
    if 'event' in event:
        event_data = event['event']
        if 'contentBlockStart' in event_data and 'start' in event_data['contentBlockStart']:
            if 'toolUse' in event_data['contentBlockStart']['start']:
                tool_name = event_data['contentBlockStart']['start']['toolUse']['name']
                return f"\n\n[Using tool: {tool_name}]\n\n"

    return ""


@app.entrypoint
async def invoke(payload, context):
    """Main entrypoint for AgentCore Runtime — streams response via SSE."""
    user_message = payload.get("prompt", "Please provide a prompt in your request")

    try:
        async for event in orchestrator.stream_async(user_message):
            text = parse_event(event)
            if text:
                yield text
    except Exception as e:
        yield f"Error: {e}"


if __name__ == "__main__":
    app.run()
