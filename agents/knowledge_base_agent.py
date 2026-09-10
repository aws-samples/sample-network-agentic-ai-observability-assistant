"""Knowledge Base Agent for network architecture documentation"""
import os
from strands import Agent, tool
from tools.kb_tools import search_knowledge_base
from config.prompts import KNOWLEDGE_BASE_AGENT_PROMPT

# Initialize agent once at module level (not per-invocation)
_kb_agent = None


def _get_kb_agent() -> Agent:
    """Lazy-initialize the KB agent to avoid cold-start cost at import time."""
    global _kb_agent
    if _kb_agent is None:
        _kb_agent = Agent(
            model=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
            system_prompt=KNOWLEDGE_BASE_AGENT_PROMPT,
            tools=[search_knowledge_base],  # Agent can call KB multiple times if needed
            callback_handler=None,
        )
    return _kb_agent


@tool
def knowledge_base_agent(query: str) -> str:
    """
    Query network architecture documentation and design patterns.

    Use when you need:
    - Network topology and design intent
    - Subnet layouts and CIDR allocations
    - Routing policies and expected traffic flows
    - Security group design and architecture decisions

    Args:
        query: Natural language query about network architecture

    Returns:
        Synthesized answer from architecture documentation with source citations
    """
    kb_id = os.getenv('KNOWLEDGE_BASE_ID')
    if not kb_id:
        return "Error: KNOWLEDGE_BASE_ID not configured in environment"

    try:
        agent = _get_kb_agent()
        response = agent(query)
        content = response.message.get('content', [])
        if content and isinstance(content, list) and len(content) > 0:
            return str(content[0].get('text', 'No response text available'))
        return "No response from knowledge base agent"
    except Exception as e:
        return f"Error in knowledge base agent: {str(e)}"
