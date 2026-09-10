#!/usr/bin/env python3
"""
Network Analyzer - Multi-Agent System
Local CLI for testing before deploying to Bedrock AgentCore.

Usage:
  Interactive mode:  python main.py
  Single-shot mode:  python main.py "Why can't 10.0.1.50 reach 10.0.2.100 on port 3306?"

For hot-reload local testing against the AgentCore runtime contract, use:
  agentcore dev          (in one terminal)
  agentcore invoke --dev "your query"  (in another terminal)
"""
import os
import sys

# Load .env BEFORE importing agents — they read env vars at module init time.
# override=False means real shell env vars take precedence over .env values.
from dotenv import load_dotenv
load_dotenv(override=False)

from agents.orchestrator import orchestrator  # noqa: E402 — intentional late import


def check_environment() -> bool:
    """Validate required environment variables are set."""
    required = ['AWS_REGION', 'VPC_FLOW_LOG_GROUP']
    optional = {'KNOWLEDGE_BASE_ID': 'knowledge_base_agent will be unavailable'}

    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print("⚠️  Missing required environment variables:")
        for v in missing:
            print(f"   - {v}")
        print("\nSet these in your .env file or shell environment.")
        return False

    for var, note in optional.items():
        if not os.getenv(var):
            print(f"ℹ️  {var} not set — {note}")

    return True


def invoke(prompt: str) -> None:
    """Stream a single query through the orchestrator, printing chunks as they arrive."""
    import asyncio

    async def _stream():
        async for event in orchestrator.stream_async(prompt):
            if "data" in event and isinstance(event["data"], str):
                print(event["data"], end="", flush=True)

    asyncio.run(_stream())
    print()  # newline after stream ends


def print_banner():
    print("=" * 70)
    print("🔍 Network Analyzer — Multi-Agent System (local mode)")
    print("=" * 70)
    print("Commands: 'help' for examples, 'exit' / 'quit' to stop\n")


def print_help():
    print("""
📚 Example queries:

  Connectivity:
    Why can't 10.0.1.50 connect to 10.0.2.100 on port 3306?
    Show me blocked traffic from 10.0.1.50 in the last 2 hours

  Configuration:
    What security groups does 10.0.2.100 have?
    Are there any permissive security groups in vpc-abc123?
    Show the route table for subnet-xyz

  Architecture:
    What is the expected traffic flow between app and database tiers?
    What are the CIDR blocks for each subnet?
""")


def interactive_loop():
    """Run an interactive REPL."""
    print_banner()
    while True:
        try:
            user_input = input("🔍 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ('exit', 'quit', 'q'):
            print("\n👋 Goodbye!")
            break
        if user_input.lower() in ('help', '?'):
            print_help()
            continue

        print("\n🤖 Analyzing...\n💡 Assistant:\n")
        try:
            invoke(user_input)
            print()
        except Exception as e:
            print(f"❌ Error: {e}\n")
            print("Check your AWS credentials or try rephrasing.\n")


def main():
    if not check_environment():
        sys.exit(1)

    # Single-shot mode: python main.py "query string"
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"🔍 Query: {prompt}\n🤖 Analyzing...\n")
        try:
            invoke(prompt)
        except Exception as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        interactive_loop()


if __name__ == "__main__":
    main()
