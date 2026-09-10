"""AWS Network Firewall tools for querying firewall logs and configuration"""
import logging
import os
import time
import boto3
from typing import Optional
from strands.tools import tool
from tools.validation import validate_ip, validate_port, validate_hours_back, validate_limit

logger = logging.getLogger(__name__)

# Lazy-initialized clients
_logs_client = None
_nfw_client = None


def _get_logs_client():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client(
            'logs',
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
    return _logs_client


def _get_nfw_client():
    global _nfw_client
    if _nfw_client is None:
        _nfw_client = boto3.client(
            'network-firewall',
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
    return _nfw_client


def _run_firewall_log_query(query: str, hours_back: int, limit: int, log_type: str = "alert") -> str:
    """Execute a CloudWatch Logs Insights query against firewall logs."""
    log_group = os.getenv('FIREWALL_ALERT_LOG_GROUP') if log_type == "alert" else os.getenv('FIREWALL_FLOW_LOG_GROUP')
    if not log_group:
        return f"Error: FIREWALL_{log_type.upper()}_LOG_GROUP not configured"

    client = _get_logs_client()
    end_time = int(time.time())
    start_time = end_time - (hours_back * 3600)

    try:
        response = client.start_query(
            logGroupName=log_group,
            startTime=start_time,
            endTime=end_time,
            queryString=query,
            limit=limit,
        )
        query_id = response['queryId']

        for _ in range(60):
            result = client.get_query_results(queryId=query_id)
            status = result['status']
            if status == 'Complete':
                return _format_results(result['results'])
            if status in ('Failed', 'Cancelled'):
                return f"Query {status.lower()}"
            time.sleep(1)

        return "Query timed out after 60 seconds"

    except Exception as e:
        logger.error(f"Firewall log query failed: {e}")
        return f"Error querying firewall logs: {str(e)}"


def _format_results(results: list) -> str:
    """Format raw Insights results into a readable table."""
    if not results:
        return "No results found."

    rows = []
    for row in results:
        fields = {f['field']: f['value'] for f in row if not f['field'].startswith('@')}
        if fields:
            rows.append(fields)

    if not rows:
        return "No matching records found."

    headers = list(rows[0].keys())
    col_widths = {h: max(len(h), max(len(str(r.get(h, ''))) for r in rows)) for h in headers}
    header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
    separator = "  ".join("-" * col_widths[h] for h in headers)
    lines = [header_line, separator]
    for row in rows:
        lines.append("  ".join(str(row.get(h, '')).ljust(col_widths[h]) for h in headers))

    return f"{len(rows)} record(s) found:\n" + "\n".join(lines)



@tool
def get_firewall_alerts(
    hours_back: int = 1,
    source_ip: Optional[str] = None,
    dest_ip: Optional[str] = None,
    limit: int = 50,
) -> str:
    """
    Get traffic blocked or alerted by AWS Network Firewall.

    Args:
        hours_back: How many hours back to search (default: 1)
        source_ip: Filter by source IP address (optional)
        dest_ip: Filter by destination IP address (optional)
        limit: Maximum number of records to return (default: 50)

    Returns:
        Firewall alert records with timestamp, IPs, ports, and matched rule signature
    """
    try:
        hours_back = validate_hours_back(hours_back)
        limit = validate_limit(limit)
        if source_ip:
            source_ip = validate_ip(source_ip)
        if dest_ip:
            dest_ip = validate_ip(dest_ip)
    except ValueError as e:
        return f"Validation error: {e}"

    filters = ["event.event_type = 'alert'"]
    if source_ip:
        filters.append(f"event.src_ip = '{source_ip}'")
    if dest_ip:
        filters.append(f"event.dest_ip = '{dest_ip}'")

    query = f"""
    fields @timestamp, event.src_ip as src_ip, event.dest_ip as dest_ip,
           event.src_port as src_port, event.dest_port as dest_port,
           event.proto as protocol, event.alert.action as action,
           event.alert.signature as signature, event.alert.category as category
    | filter {" and ".join(filters)}
    | sort @timestamp desc
    | limit {limit}
    """
    return _run_firewall_log_query(query, hours_back, limit, "alert")


@tool
def get_firewall_flows(
    source_ip: Optional[str] = None,
    dest_ip: Optional[str] = None,
    hours_back: int = 1,
    limit: int = 50,
) -> str:
    """
    Get network flow records processed by AWS Network Firewall.

    Args:
        source_ip: Filter by source IP (optional)
        dest_ip: Filter by destination IP (optional)
        hours_back: How many hours back to search (default: 1)
        limit: Maximum number of records to return (default: 50)

    Returns:
        Flow records showing traffic processed by the firewall
    """
    try:
        hours_back = validate_hours_back(hours_back)
        limit = validate_limit(limit)
        if source_ip:
            source_ip = validate_ip(source_ip)
        if dest_ip:
            dest_ip = validate_ip(dest_ip)
    except ValueError as e:
        return f"Validation error: {e}"

    filters = ["event.event_type = 'netflow'"]
    if source_ip:
        filters.append(f"event.src_ip = '{source_ip}'")
    if dest_ip:
        filters.append(f"event.dest_ip = '{dest_ip}'")

    query = f"""
    fields @timestamp, event.src_ip as src_ip, event.dest_ip as dest_ip,
           event.src_port as src_port, event.dest_port as dest_port,
           event.proto as protocol, event.app_proto as app_protocol,
           event.netflow.bytes as bytes, event.netflow.pkts as packets
    | filter {" and ".join(filters)}
    | sort @timestamp desc
    | limit {limit}
    """
    return _run_firewall_log_query(query, hours_back, limit, "flow")


@tool
def get_firewall_alert_summary(hours_back: int = 1) -> str:
    """
    Get a summary of top firewall alerts grouped by signature and destination.
    Useful for identifying the most frequently triggered firewall rules.

    Args:
        hours_back: How many hours back to analyze (default: 1)

    Returns:
        Top firewall alerts ranked by frequency with rule signatures
    """
    try:
        hours_back = validate_hours_back(hours_back)
    except ValueError as e:
        return f"Validation error: {e}"

    query = """
    fields event.src_ip as src_ip, event.dest_ip as dest_ip,
           event.dest_port as dest_port, event.alert.signature as signature,
           event.alert.action as action
    | filter event.event_type = 'alert'
    | stats count(*) as alert_count by signature, action, dest_ip, dest_port
    | sort alert_count desc
    | limit 20
    """
    return _run_firewall_log_query(query, hours_back, 20, "alert")


@tool
def analyze_firewall_traffic(
    source_ip: str,
    dest_ip: str,
    dest_port: int,
    hours_back: int = 1,
) -> str:
    """
    Analyze how the firewall handled traffic for a specific source→dest:port flow.
    Shows whether traffic was allowed, alerted, or dropped by the firewall.

    Args:
        source_ip: Source IP address
        dest_ip: Destination IP address
        dest_port: Destination port number
        hours_back: How many hours back to search (default: 1)

    Returns:
        Alert and flow counts for the specific traffic flow through the firewall
    """
    try:
        source_ip = validate_ip(source_ip)
        dest_ip = validate_ip(dest_ip)
        dest_port = validate_port(dest_port)
        hours_back = validate_hours_back(hours_back)
    except ValueError as e:
        return f"Validation error: {e}"

    # Check alerts for this flow
    alert_query = f"""
    fields event.alert.action as action, event.alert.signature as signature
    | filter event.event_type = 'alert'
        and event.src_ip = '{source_ip}'
        and event.dest_ip = '{dest_ip}'
        and event.dest_port = {dest_port}
    | stats count(*) as count by action, signature
    """
    alert_results = _run_firewall_log_query(alert_query, hours_back, 20, "alert")

    # Check flows for this traffic
    flow_query = f"""
    fields event.netflow.bytes as bytes, event.netflow.pkts as packets
    | filter event.event_type = 'netflow'
        and event.src_ip = '{source_ip}'
        and event.dest_ip = '{dest_ip}'
        and event.dest_port = {dest_port}
    | stats sum(event.netflow.pkts) as total_packets, sum(event.netflow.bytes) as total_bytes, count(*) as flow_count
    """
    flow_results = _run_firewall_log_query(flow_query, hours_back, 10, "flow")

    return (
        f"Firewall analysis: {source_ip} → {dest_ip}:{dest_port} (last {hours_back}h)\n\n"
        f"ALERTS:\n{alert_results}\n\n"
        f"FLOWS:\n{flow_results}"
    )


@tool
def describe_firewall_config(firewall_name: Optional[str] = None) -> str:
    """
    Get AWS Network Firewall configuration details including VPC, subnets, and policy.

    Args:
        firewall_name: Name of the firewall (optional, lists all firewalls if not provided)

    Returns:
        Firewall configuration details
    """
    nfw = _get_nfw_client()

    try:
        if not firewall_name:
            # List all firewalls
            response = nfw.list_firewalls()
            firewalls = response.get('Firewalls', [])
            if not firewalls:
                return "No Network Firewalls found in this account/region."
            lines = ["Available firewalls:"]
            for fw in firewalls:
                lines.append(f"  - {fw.get('FirewallName')} (ARN: {fw.get('FirewallArn')})")
            return "\n".join(lines)

        response = nfw.describe_firewall(FirewallName=firewall_name)
        fw = response['Firewall']
        status = response.get('FirewallStatus', {})

        subnet_mappings = fw.get('SubnetMappings', [])
        subnets = [s.get('SubnetId', '') for s in subnet_mappings]

        lines = [
            f"Firewall:        {fw['FirewallName']}",
            f"ARN:             {fw['FirewallArn']}",
            f"VPC:             {fw['VpcId']}",
            f"Policy ARN:      {fw.get('FirewallPolicyArn', 'N/A')}",
            f"Subnets:         {', '.join(subnets)}",
            f"Status:          {status.get('Status', 'Unknown')}",
            f"Delete Protect:  {fw.get('DeleteProtection', False)}",
        ]

        # Also fetch the policy to list rule group names
        policy_arn = fw.get('FirewallPolicyArn')
        if policy_arn:
            try:
                policy_resp = nfw.describe_firewall_policy(FirewallPolicyArn=policy_arn)
                policy = policy_resp.get('FirewallPolicy', {})
                policy_name = policy_resp.get('FirewallPolicyResponse', {}).get('FirewallPolicyName', '')
                lines.append(f"Policy Name:     {policy_name}")

                stateful_refs = policy.get('StatefulRuleGroupReferences', [])
                stateless_refs = policy.get('StatelessRuleGroupReferences', [])

                if stateful_refs:
                    lines.append("Stateful Rule Groups:")
                    for ref in stateful_refs:
                        # Extract name from ARN: ...stateful-rulegroup/NAME
                        arn = ref.get('ResourceArn', '')
                        name = arn.split('/')[-1] if '/' in arn else arn
                        lines.append(f"  - {name}")

                if stateless_refs:
                    lines.append("Stateless Rule Groups:")
                    for ref in stateless_refs:
                        arn = ref.get('ResourceArn', '')
                        name = arn.split('/')[-1] if '/' in arn else arn
                        lines.append(f"  - {name}")
            except (KeyError, TypeError, IndexError):
                pass  # Policy details are best-effort

        return "\n".join(lines)

    except nfw.exceptions.ResourceNotFoundException:
        return f"Firewall '{firewall_name}' not found."
    except Exception as e:
        logger.error(f"Error describing firewall: {e}")
        return f"Error describing firewall: {str(e)}"


@tool
def get_firewall_rules(rule_group_name: str, rule_group_type: str = "STATEFUL") -> str:
    """
    Get the rules from a Network Firewall rule group.

    Args:
        rule_group_name: Name of the rule group
        rule_group_type: Type of rule group - STATEFUL or STATELESS (default: STATEFUL)

    Returns:
        Rule group details including individual rules
    """
    nfw = _get_nfw_client()

    try:
        response = nfw.describe_rule_group(
            RuleGroupName=rule_group_name,
            Type=rule_group_type,
        )
        rg = response['RuleGroup']
        metadata = response['RuleGroupResponse']

        lines = [
            f"Rule Group:  {metadata['RuleGroupName']}",
            f"Type:        {metadata['Type']}",
            f"Capacity:    {metadata.get('Capacity', 'N/A')}",
            f"Description: {metadata.get('Description', 'N/A')}",
            "",
            "Rules:",
            "-" * 60,
        ]

        if rule_group_type == "STATEFUL":
            rules_source = rg.get('RulesSource', {})

            # Suricata-format rules
            if 'RulesString' in rules_source:
                lines.append("Format: Suricata rules")
                lines.append("")
                for rule_line in rules_source['RulesString'].strip().split('\n'):
                    lines.append(f"  {rule_line}")

            # Domain list rules
            elif 'RulesSourceList' in rules_source:
                rsl = rules_source['RulesSourceList']
                lines.append(f"Format: Domain list ({rsl.get('GeneratedRulesType', '')})")
                lines.append(f"Target Types: {', '.join(rsl.get('TargetTypes', []))}")
                lines.append("Targets:")
                for target in rsl.get('Targets', []):
                    lines.append(f"  - {target}")

            # 5-tuple stateful rules
            elif 'StatefulRules' in rules_source:
                lines.append("Format: 5-tuple stateful rules")
                for rule in rules_source['StatefulRules']:
                    header = rule.get('Header', {})
                    lines.append(
                        f"  {rule.get('Action', '')} "
                        f"{header.get('Protocol', '')} "
                        f"{header.get('Source', '')}:{header.get('SourcePort', '')} -> "
                        f"{header.get('Destination', '')}:{header.get('DestinationPort', '')} "
                        f"({header.get('Direction', '')})"
                    )
        else:
            # Stateless rules
            rules_source = rg.get('RulesSource', {})
            stateless = rules_source.get('StatelessRulesAndCustomActions', {})
            for rule in stateless.get('StatelessRules', []):
                rd = rule.get('RuleDefinition', {})
                match_attrs = rd.get('MatchAttributes', {})
                lines.append(
                    f"  Priority {rule.get('Priority', '?')}: "
                    f"Actions={rd.get('Actions', [])} "
                    f"Protocols={match_attrs.get('Protocols', [])} "
                    f"SrcPorts={match_attrs.get('SourcePorts', [])} "
                    f"DstPorts={match_attrs.get('DestinationPorts', [])}"
                )

        return "\n".join(lines)

    except nfw.exceptions.ResourceNotFoundException:
        return f"Rule group '{rule_group_name}' not found."
    except Exception as e:
        logger.error(f"Error describing rule group: {e}")
        return f"Error describing rule group: {str(e)}"
