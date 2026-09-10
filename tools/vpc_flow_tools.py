"""VPC Flow Log tools for querying CloudWatch Logs Insights"""
import logging
import os
import time
import boto3
from typing import Optional
from strands.tools import tool
from tools.validation import validate_ip, validate_port, validate_hours_back, validate_limit

logger = logging.getLogger(__name__)

# Lazy-initialized CloudWatch Logs client singleton
_logs_client = None


def _get_logs_client():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client(
            'logs',
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
    return _logs_client


def _run_insights_query(query: str, hours_back: int, limit: int) -> str:
    """Execute a CloudWatch Logs Insights query and wait for results."""
    log_group = os.getenv('VPC_FLOW_LOG_GROUP')
    if not log_group:
        return "Error: VPC_FLOW_LOG_GROUP not configured"

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

        # Poll up to 60 seconds
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
        logger.error(f"CloudWatch Logs Insights query failed: {e}")
        return f"Error querying VPC flow logs: {str(e)}"


def _format_results(results: list) -> str:
    """Format raw Insights results into a readable table."""
    if not results:
        return "No results found."

    # Collect rows, skipping internal @ptr/@log fields
    rows = []
    for row in results:
        fields = {f['field']: f['value'] for f in row if not f['field'].startswith('@')}
        if fields:
            rows.append(fields)

    if not rows:
        return "No matching records found."

    # Build aligned table
    headers = list(rows[0].keys())
    col_widths = {h: max(len(h), max(len(str(r.get(h, ''))) for r in rows)) for h in headers}
    header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
    separator = "  ".join("-" * col_widths[h] for h in headers)
    lines = [header_line, separator]
    for row in rows:
        lines.append("  ".join(str(row.get(h, '')).ljust(col_widths[h]) for h in headers))

    return f"{len(rows)} record(s) found:\n" + "\n".join(lines)


@tool
def get_rejected_traffic(
    hours_back: int = 1,
    source_ip: Optional[str] = None,
    dest_ip: Optional[str] = None,
    limit: int = 50,
) -> str:
    """
    Get rejected/blocked traffic from VPC Flow Logs.

    Args:
        hours_back: How many hours back to search (default: 1)
        source_ip: Filter by source IP address (optional)
        dest_ip: Filter by destination IP address (optional)
        limit: Maximum number of records to return (default: 50)

    Returns:
        Rejected traffic records with timestamp, IPs, ports, and protocol
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

    filters = ["action = 'REJECT'"]
    if source_ip:
        filters.append(f"srcAddr = '{source_ip}'")
    if dest_ip:
        filters.append(f"dstAddr = '{dest_ip}'")

    query = f"""
    fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, protocol, action, bytes
    | filter {" and ".join(filters)}
    | sort @timestamp desc
    | limit {limit}
    """
    return _run_insights_query(query, hours_back, limit)


@tool
def get_traffic_between_ips(
    source_ip: str,
    dest_ip: str,
    hours_back: int = 1,
    limit: int = 50,
) -> str:
    """
    Get all traffic (accepted and rejected) between two IP addresses.

    Args:
        source_ip: First IP address
        dest_ip: Second IP address
        hours_back: How many hours back to search (default: 1)
        limit: Maximum number of records to return (default: 50)

    Returns:
        Traffic records in both directions between the two IPs
    """
    try:
        source_ip = validate_ip(source_ip)
        dest_ip = validate_ip(dest_ip)
        hours_back = validate_hours_back(hours_back)
        limit = validate_limit(limit)
    except ValueError as e:
        return f"Validation error: {e}"

    query = f"""
    fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, protocol, action, bytes
    | filter (srcAddr = '{source_ip}' and dstAddr = '{dest_ip}')
          or (srcAddr = '{dest_ip}' and dstAddr = '{source_ip}')
    | sort @timestamp desc
    | limit {limit}
    """
    return _run_insights_query(query, hours_back, limit)


@tool
def analyze_connectivity(
    source_ip: str,
    dest_ip: str,
    dest_port: int,
    hours_back: int = 1,
) -> str:
    """
    Analyze connectivity between a source and destination on a specific port.
    Returns accepted vs rejected counts to determine if traffic is being blocked.

    Args:
        source_ip: Source IP address
        dest_ip: Destination IP address
        dest_port: Destination port number
        hours_back: How many hours back to search (default: 1)

    Returns:
        Accepted and rejected connection counts for the specific flow
    """
    try:
        source_ip = validate_ip(source_ip)
        dest_ip = validate_ip(dest_ip)
        dest_port = validate_port(dest_port)
        hours_back = validate_hours_back(hours_back)
    except ValueError as e:
        return f"Validation error: {e}"

    query = f"""
    fields @timestamp, srcAddr, dstAddr, dstPort, protocol, action
    | filter srcAddr = '{source_ip}' and dstAddr = '{dest_ip}' and dstPort = {dest_port}
    | stats count(*) as total,
            sum(action = 'ACCEPT') as accepted,
            sum(action = 'REJECT') as rejected
      by srcAddr, dstAddr, dstPort
    """
    return _run_insights_query(query, hours_back, 10)


@tool
def get_traffic_summary(hours_back: int = 1) -> str:
    """
    Get a summary of top rejected connections grouped by source, destination, and port.
    Useful for identifying the most frequent blocked flows.

    Args:
        hours_back: How many hours back to analyze (default: 1)

    Returns:
        Top rejected connections ranked by frequency
    """
    try:
        hours_back = validate_hours_back(hours_back)
    except ValueError as e:
        return f"Validation error: {e}"

    query = """
    fields srcAddr, dstAddr, dstPort, action
    | filter action = 'REJECT'
    | stats count(*) as reject_count by srcAddr, dstAddr, dstPort
    | sort reject_count desc
    | limit 20
    """
    return _run_insights_query(query, hours_back, 20)


@tool
def query_vpc_flow_logs(query: str, hours_back: int = 1, limit: int = 100) -> str:
    """
    Run a custom CloudWatch Logs Insights query against VPC Flow Logs.
    Use this for advanced analysis not covered by the other tools.

    Args:
        query: A valid CloudWatch Logs Insights query string
        hours_back: How many hours back to search (default: 1)
        limit: Maximum number of results (default: 100)

    Returns:
        Query results formatted as a table
    """
    return _run_insights_query(query, hours_back, limit)
