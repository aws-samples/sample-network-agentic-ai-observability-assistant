"""Network Firewall Agent - Analyzes AWS Network Firewall logs and configuration"""
import os
from strands import Agent, tool
from tools.firewall_tools import (
    get_firewall_alerts,
    get_firewall_flows,
    get_firewall_alert_summary,
    analyze_firewall_traffic,
    describe_firewall_config,
    get_firewall_rules,
)
from config.prompts import FIREWALL_AGENT_PROMPT

# Module-level singleton — initialized once, reused across invocations
_firewall_agent = None


def _get_firewall_agent() -> Agent:
    """Lazy-initialize the firewall agent."""
    global _firewall_agent
    if _firewall_agent is None:
        _firewall_agent = Agent(
            model=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
            system_prompt=FIREWALL_AGENT_PROMPT,
            tools=[
                get_firewall_alerts,
                get_firewall_flows,
                get_firewall_alert_summary,
                analyze_firewall_traffic,
                describe_firewall_config,
                get_firewall_rules,
            ],
            callback_handler=None,
        )
    return _firewall_agent


@tool
def firewall_agent(query: str, hours_back: int = 1) -> str:
    """
    Analyze AWS Network Firewall logs and configuration.

    Use when you need to:
    - Find traffic blocked or alerted by Network Firewall (distinct from SG/NACL blocks)
    - Inspect firewall rules and policies
    - Determine which firewall rule is dropping specific traffic
    - Get alert summaries for suspicious or blocked traffic patterns
    - Understand firewall configuration (VPC, subnets, policy)

    Args:
        query: Natural language description of what to analyze, e.g.:
            - "What traffic is being blocked by the firewall?"
            - "Is 10.0.1.50 being blocked from reaching 203.0.113.99 on port 443?"
            - "Show me the top firewall alerts in the last 2 hours"
            - "What rules are in the egress-filter rule group?"
            - "Describe the firewall configuration"
        hours_back: Hours of logs to search (default: 1)

    Returns:
        Synthesized analysis of Network Firewall logs or configuration
    """
    alert_log = os.getenv('FIREWALL_ALERT_LOG_GROUP')
    flow_log = os.getenv('FIREWALL_FLOW_LOG_GROUP')
    if not alert_log and not flow_log:
        return "Error: Neither FIREWALL_ALERT_LOG_GROUP nor FIREWALL_FLOW_LOG_GROUP is configured in environment"

    try:
        agent = _get_firewall_agent()
        full_query = query if hours_back == 1 else f"{query} (look back {hours_back} hours)"
        response = agent(full_query)
        content = response.message.get('content', [])
        if content and isinstance(content, list) and len(content) > 0:
            return str(content[0].get('text', 'No response text available'))
        return "No response from firewall agent"
    except Exception as e:
        return f"Error in firewall agent: {str(e)}"
