"""Network Config Agent - Queries live AWS network configuration"""
import os
from strands import Agent, tool
from tools.network_config_tools import (
    get_eni_by_ip,
    get_security_group_rules,
    get_nacl_rules,
    get_route_table,
    list_security_groups,
    find_permissive_rules,
    check_connectivity,
)
from config.prompts import NETWORK_CONFIG_AGENT_PROMPT

# Module-level singleton — initialized once, reused across invocations
_network_agent = None


def _get_network_agent() -> Agent:
    """Lazy-initialize the network config agent."""
    global _network_agent
    if _network_agent is None:
        _network_agent = Agent(
            model=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
            system_prompt=NETWORK_CONFIG_AGENT_PROMPT,
            tools=[
                get_eni_by_ip,
                get_security_group_rules,
                get_nacl_rules,
                get_route_table,
                list_security_groups,
                find_permissive_rules,
                check_connectivity,
            ],
            callback_handler=None,
        )
    return _network_agent


@tool
def network_config_agent(query: str) -> str:
    """
    Query live AWS network configuration - security groups, NACLs, and routes.

    Use when you need to:
    - Find which security groups or NACLs control traffic for an IP
    - Inspect security group inbound/outbound rules
    - Check NACL rules for a subnet
    - Inspect route tables
    - List or audit security groups for permissive rules (0.0.0.0/0)
    - Analyze connectivity between two IPs on a specific port

    Args:
        query: Natural language description of what to look up, e.g.:
            - "What security groups does 10.0.1.50 have?"
            - "Show rules for sg-abc123"
            - "Check NACL for subnet-xyz"
            - "Are there any permissive security groups in vpc-123?"
            - "Can 10.0.1.50 reach 10.0.2.100 on port 3306?"

    Returns:
        Synthesized answer about the AWS network configuration
    """
    try:
        agent = _get_network_agent()
        response = agent(query)
        content = response.message.get('content', [])
        if content and isinstance(content, list) and len(content) > 0:
            return str(content[0].get('text', 'No response text available'))
        return "No response from network config agent"
    except Exception as e:
        return f"Error in network config agent: {str(e)}"
