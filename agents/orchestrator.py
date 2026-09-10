"""Orchestrator Agent - Routes queries to specialist agents"""
import os
from strands import Agent
from strands.models import BedrockModel
from agents.vpc_flow_agent import vpc_flow_agent
from agents.network_config_agent import network_config_agent
from agents.knowledge_base_agent import knowledge_base_agent
from agents.firewall_agent import firewall_agent
from config.prompts import ORCHESTRATOR_SYSTEM_PROMPT


# Module-level singleton with explicit BedrockModel for max_tokens control
orchestrator = Agent(
    model=BedrockModel(
        model_id=os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'),
        max_tokens=4096,
    ),
    system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
    tools=[
        vpc_flow_agent,
        network_config_agent,
        knowledge_base_agent,
        firewall_agent,
    ],
    callback_handler=None,  # Prevent duplicate streaming output
)
