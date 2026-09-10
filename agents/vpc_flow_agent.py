"""VPC Flow Log Agent for traffic analysis"""
import os
from strands import Agent, tool
from tools.vpc_flow_tools import (
    get_rejected_traffic,
    get_traffic_between_ips,
    analyze_connectivity,
    get_traffic_summary,
    query_vpc_flow_logs,
)
from config.prompts import VPC_FLOW_AGENT_PROMPT

# Module-level singleton — initialized once, reused across invocations
_vpc_agent = None


def _get_vpc_agent() -> Agent:
    """Lazy-initialize the VPC flow agent."""
    global _vpc_agent
    if _vpc_agent is None:
        _vpc_agent = Agent(
            model=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
            system_prompt=VPC_FLOW_AGENT_PROMPT,
            tools=[
                get_rejected_traffic,
                get_traffic_between_ips,
                analyze_connectivity,
                get_traffic_summary,
                query_vpc_flow_logs,
            ],
            callback_handler=None,
        )
    return _vpc_agent


@tool
def vpc_flow_agent(query: str, hours_back: int = 1) -> str:
    """
    Analyze VPC Flow Logs to identify traffic patterns, blocked connections, and anomalies.

    Use when you need to:
    - Find rejected or blocked traffic
    - Analyze traffic between specific IPs
    - Check if a specific connection (source → dest:port) is being accepted or rejected
    - Get a summary of the most frequently blocked flows
    - Run custom CloudWatch Logs Insights queries

    Args:
        query: Natural language description of what to analyze, e.g.:
            - "Show me all rejected traffic in the last hour"
            - "What traffic is being blocked from 10.0.1.50?"
            - "Is 10.0.1.50 able to reach 10.0.2.100 on port 3306?"
            - "Summarize the top blocked connections"
            - "Show all traffic between 10.0.1.50 and 10.0.2.100"
        hours_back: Hours of logs to search (default: 1)

    Returns:
        Synthesized analysis of VPC flow log data
    """
    log_group = os.getenv('VPC_FLOW_LOG_GROUP')
    if not log_group:
        return "Error: VPC_FLOW_LOG_GROUP not configured in environment"

    try:
        agent = _get_vpc_agent()
        # Pass hours_back as context so the agent uses it when calling tools
        full_query = query if hours_back == 1 else f"{query} (look back {hours_back} hours)"
        response = agent(full_query)
        content = response.message.get('content', [])
        if content and isinstance(content, list) and len(content) > 0:
            return str(content[0].get('text', 'No response text available'))
        return "No response from VPC flow agent"
    except Exception as e:
        return f"Error in VPC flow agent: {str(e)}"
