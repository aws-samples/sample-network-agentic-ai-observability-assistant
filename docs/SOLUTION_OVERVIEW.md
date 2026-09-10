# Network Observability Assistant

A multi-agent GenAI solution for AWS network troubleshooting, deployed on Amazon Bedrock AgentCore Runtime.

## Problem Statement

When connectivity issues arise in AWS, engineers must manually correlate data across VPC flow logs, security groups, NACLs, route tables, Network Firewall logs, and architecture docs. This is slow, error-prone, and requires deep expertise.

## Architecture

```
User Query
    │
    ▼
┌─────────────────┐
│   Orchestrator  │  (Claude Sonnet via Bedrock cross-region inference)
└────────┬────────┘
         │
         ├──► knowledge_base_agent  ──► Architecture docs (Bedrock KB)
         ├──► vpc_flow_agent        ──► VPC Flow Logs (CloudWatch Insights)
         ├──► network_config_agent  ──► Live AWS config (EC2/VPC APIs)
         └──► firewall_agent        ──► Network Firewall logs & rules (CloudWatch)
```

All four specialists are `@tool`-decorated Strands agents (Agents as Tools pattern). The orchestrator invokes them for connectivity questions: KB → flow logs → firewall → live config → root cause.

## Agents

### Orchestrator
Routes queries to specialists and synthesizes findings. Uses `claude-sonnet-4-5` with `max_tokens=4096`.

### Knowledge Base Agent
Queries a Bedrock Knowledge Base for architecture docs, subnet layouts, CIDR allocations, and expected traffic flows. Re-queries with different terms if initial results are insufficient.

### VPC Flow Log Agent
Queries CloudWatch Logs Insights against VPC Flow Logs (`VPC_FLOW_LOG_GROUP`). Tools:
- `analyze_connectivity` — accepted vs rejected counts for a specific src→dst:port
- `get_rejected_traffic` — blocked flows, filterable by source/dest IP
- `get_traffic_between_ips` — bidirectional traffic between two IPs
- `get_traffic_summary` — top rejected flows by frequency
- `query_vpc_flow_logs` — custom Insights queries

### Network Config Agent
Inspects live AWS resources via EC2 APIs. Tools:
- `get_eni_by_ip` — find ENI and security groups for an IP
- `get_security_group_rules` — inbound/outbound rules for a SG
- `get_nacl_rules` — NACL rules for a subnet
- `get_route_table` — routes for a subnet (falls back to VPC main route table)
- `list_security_groups` / `find_permissive_rules` — audit for 0.0.0.0/0 rules
- `check_connectivity` — ENI details for both endpoints of a connection

### Firewall Agent
Analyzes AWS Network Firewall logs and configuration (`FIREWALL_ALERT_LOG_GROUP`, `FIREWALL_FLOW_LOG_GROUP`). Tools:
- `analyze_firewall_traffic` — how the firewall handled a specific src→dst:port (alerts + flows)
- `get_firewall_alerts` — traffic blocked/alerted by the firewall, filterable by source/dest IP
- `get_firewall_flows` — flow records processed by the stateful engine
- `get_firewall_alert_summary` — top alerts by frequency (signatures and destinations)
- `describe_firewall_config` — firewall metadata (VPC, subnets, policy) or list all firewalls
- `get_firewall_rules` — rules from a specific rule group (stateful or stateless)

## Deployment

- Runtime: Amazon Bedrock AgentCore (`direct_code_deploy`, Python 3.12, ARM64; region from `AWS_REGION`)
- Memory: AgentCore STM enabled
- Observability: OpenTelemetry enabled
- Entry point: `agent.py` wraps the orchestrator with `BedrockAgentCoreApp`

## Environment Variables

| Variable | Purpose |
|---|---|
| `BEDROCK_MODEL_ID` | Model ID (default: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`) |
| `KNOWLEDGE_BASE_ID` | Bedrock Knowledge Base ID |
| `VPC_FLOW_LOG_GROUP` | CloudWatch Log Group for VPC Flow Logs |
| `FIREWALL_ALERT_LOG_GROUP` | CloudWatch Log Group for Network Firewall alert logs |
| `FIREWALL_FLOW_LOG_GROUP` | CloudWatch Log Group for Network Firewall flow logs |
| `AWS_REGION` | AWS region for boto3 clients |
