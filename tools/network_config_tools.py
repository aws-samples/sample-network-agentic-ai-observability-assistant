"""Network Configuration tools for querying live AWS resources"""
import logging
import os
import boto3
from typing import Optional
from strands.tools import tool
from tools.validation import validate_ip, validate_port, sanitize_sg_id, sanitize_subnet_id

logger = logging.getLogger(__name__)

# Lazy-initialized EC2 client singleton
_ec2_client = None


def _get_ec2_client():
    global _ec2_client
    if _ec2_client is None:
        _ec2_client = boto3.client(
            'ec2',
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
    return _ec2_client


@tool
def get_eni_by_ip(ip_address: str) -> str:
    """
    Find the Elastic Network Interface (ENI) associated with an IP address.
    Returns ENI ID, security groups, subnet, VPC, and attached instance.

    Args:
        ip_address: Private or public IP address to look up

    Returns:
        ENI details including security group IDs and subnet
    """
    try:
        ip_address = validate_ip(ip_address)
    except ValueError as e:
        return f"Validation error: {e}"

    try:
        ec2 = _get_ec2_client()

        response = ec2.describe_network_interfaces(
            Filters=[{'Name': 'addresses.private-ip-address', 'Values': [ip_address]}]
        )
        if not response['NetworkInterfaces']:
            response = ec2.describe_network_interfaces(
                Filters=[{'Name': 'association.public-ip', 'Values': [ip_address]}]
            )
        if not response['NetworkInterfaces']:
            return f"No ENI found for IP {ip_address}"

        eni = response['NetworkInterfaces'][0]
        sg_ids = [sg['GroupId'] for sg in eni.get('Groups', [])]

        lines = [
            f"ENI ID:          {eni['NetworkInterfaceId']}",
            f"Private IP:      {eni.get('PrivateIpAddress')}",
            f"Public IP:       {eni.get('Association', {}).get('PublicIp', 'None')}",
            f"Subnet:          {eni['SubnetId']}",
            f"VPC:             {eni['VpcId']}",
            f"Security Groups: {', '.join(sg_ids) if sg_ids else 'None'}",
            f"Instance ID:     {eni.get('Attachment', {}).get('InstanceId', 'None')}",
            f"Description:     {eni.get('Description', '')}",
        ]
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error finding ENI for {ip_address}: {e}")
        return f"Error finding ENI for {ip_address}: {str(e)}"


@tool
def get_security_group_rules(sg_id: str) -> str:
    """
    Get all inbound and outbound rules for a security group.

    Args:
        sg_id: Security group ID (e.g., sg-0abc12345)

    Returns:
        Formatted inbound and outbound rules
    """
    try:
        sg_id = sanitize_sg_id(sg_id)
    except ValueError as e:
        return f"Validation error: {e}"

    try:
        ec2 = _get_ec2_client()
        response = ec2.describe_security_groups(GroupIds=[sg_id])

        if not response['SecurityGroups']:
            return f"Security group {sg_id} not found"

        sg = response['SecurityGroups'][0]

        def format_rules(permissions, direction):
            lines = []
            for rule in permissions:
                protocol = rule.get('IpProtocol', '-1')
                if protocol == '-1':
                    protocol = 'ALL'
                from_port = rule.get('FromPort', '*')
                to_port = rule.get('ToPort', '*')
                port_range = f"{from_port}" if from_port == to_port else f"{from_port}-{to_port}"

                sources = (
                    [r.get('CidrIp') for r in rule.get('IpRanges', [])] +
                    [r.get('CidrIpv6') for r in rule.get('Ipv6Ranges', [])] +
                    [f"sg:{r.get('GroupId')}" for r in rule.get('UserIdGroupPairs', [])]
                )
                lines.append(
                    f"  [{direction}] {protocol} port {port_range} from {', '.join(filter(None, sources)) or 'N/A'}"
                )
            return lines

        lines = [
            f"Security Group: {sg_id} ({sg.get('GroupName')})",
            f"VPC:            {sg.get('VpcId')}",
            f"Description:    {sg.get('Description')}",
            "Rules:",
        ]
        lines += format_rules(sg.get('IpPermissions', []), 'INBOUND')
        lines += format_rules(sg.get('IpPermissionsEgress', []), 'OUTBOUND')
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error getting security group {sg_id}: {e}")
        return f"Error getting security group {sg_id}: {str(e)}"


@tool
def get_nacl_rules(subnet_id: str) -> str:
    """
    Get Network ACL rules for a subnet (both inbound and outbound).

    Args:
        subnet_id: Subnet ID to look up the associated NACL

    Returns:
        NACL rules sorted by rule number
    """
    try:
        subnet_id = sanitize_subnet_id(subnet_id)
    except ValueError as e:
        return f"Validation error: {e}"

    try:
        ec2 = _get_ec2_client()
        response = ec2.describe_network_acls(
            Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
        )
        if not response['NetworkAcls']:
            return f"No NACL found for subnet {subnet_id}"

        nacl = response['NetworkAcls'][0]
        entries = sorted(nacl.get('Entries', []), key=lambda e: (e.get('Egress'), e.get('RuleNumber')))

        protocol_map = {'-1': 'ALL', '6': 'TCP', '17': 'UDP', '1': 'ICMP'}

        lines = [
            f"NACL ID: {nacl['NetworkAclId']}  VPC: {nacl['VpcId']}",
            f"{'#':<8} {'Dir':<10} {'Protocol':<10} {'CIDR':<20} {'Ports':<15} {'Action'}",
            "-" * 70,
        ]
        for e in entries:
            direction = 'OUTBOUND' if e.get('Egress') else 'INBOUND'
            proto = protocol_map.get(e.get('Protocol', '-1'), e.get('Protocol'))
            port_range = e.get('PortRange', {})
            ports = f"{port_range.get('From')}-{port_range.get('To')}" if port_range else '*'
            lines.append(
                f"{e.get('RuleNumber'):<8} {direction:<10} {proto:<10} "
                f"{e.get('CidrBlock', ''):<20} {ports:<15} {e.get('RuleAction', '').upper()}"
            )
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error getting NACL for subnet {subnet_id}: {e}")
        return f"Error getting NACL for subnet {subnet_id}: {str(e)}"


@tool
def get_route_table(subnet_id: str) -> str:
    """
    Get the route table for a subnet. Falls back to the VPC main route table
    if no explicit association exists.

    Args:
        subnet_id: Subnet ID

    Returns:
        Route table entries with destination and target
    """
    try:
        subnet_id = sanitize_subnet_id(subnet_id)
    except ValueError as e:
        return f"Validation error: {e}"

    try:
        ec2 = _get_ec2_client()

        response = ec2.describe_route_tables(
            Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
        )
        if not response['RouteTables']:
            subnet_resp = ec2.describe_subnets(SubnetIds=[subnet_id])
            if subnet_resp['Subnets']:
                vpc_id = subnet_resp['Subnets'][0]['VpcId']
                response = ec2.describe_route_tables(
                    Filters=[
                        {'Name': 'vpc-id', 'Values': [vpc_id]},
                        {'Name': 'association.main', 'Values': ['true']},
                    ]
                )
        if not response['RouteTables']:
            return f"No route table found for subnet {subnet_id}"

        rt = response['RouteTables'][0]
        lines = [
            f"Route Table: {rt['RouteTableId']}  VPC: {rt['VpcId']}",
            f"{'Destination':<25} {'Target':<35} {'State'}",
            "-" * 65,
        ]
        for route in rt.get('Routes', []):
            dest = (route.get('DestinationCidrBlock') or
                    route.get('DestinationIpv6CidrBlock') or
                    route.get('DestinationPrefixListId', ''))
            target = (route.get('GatewayId') or route.get('NatGatewayId') or
                      route.get('TransitGatewayId') or route.get('NetworkInterfaceId') or
                      route.get('VpcPeeringConnectionId') or 'local')
            lines.append(f"{dest:<25} {target:<35} {route.get('State', '')}")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Error getting route table for subnet {subnet_id}: {e}")
        return f"Error getting route table for subnet {subnet_id}: {str(e)}"


@tool
def list_security_groups(vpc_id: Optional[str] = None) -> str:
    """
    List all security groups, optionally filtered by VPC.

    Args:
        vpc_id: Optional VPC ID to filter results

    Returns:
        Summary list of security groups with rule counts
    """
    try:
        ec2 = _get_ec2_client()
        filters = [{'Name': 'vpc-id', 'Values': [vpc_id]}] if vpc_id else []
        response = ec2.describe_security_groups(Filters=filters)

        lines = [f"{'SG ID':<22} {'Name':<30} {'VPC':<22} {'In':<5} {'Out'}"]
        lines.append("-" * 85)
        for sg in response['SecurityGroups']:
            lines.append(
                f"{sg['GroupId']:<22} {sg['GroupName'][:28]:<30} {sg['VpcId']:<22} "
                f"{len(sg.get('IpPermissions', [])):<5} {len(sg.get('IpPermissionsEgress', []))}"
            )
        return "\n".join(lines) if len(lines) > 2 else "No security groups found."

    except Exception as e:
        logger.error(f"Error listing security groups: {e}")
        return f"Error listing security groups: {str(e)}"


@tool
def find_permissive_rules(vpc_id: Optional[str] = None) -> str:
    """
    Find security groups with overly permissive inbound rules (0.0.0.0/0 or ::/0).

    Args:
        vpc_id: Optional VPC ID to scope the search

    Returns:
        List of permissive rules with SG ID, protocol, and port range
    """
    try:
        ec2 = _get_ec2_client()
        filters = [{'Name': 'vpc-id', 'Values': [vpc_id]}] if vpc_id else []
        response = ec2.describe_security_groups(Filters=filters)

        permissive = []
        for sg in response['SecurityGroups']:
            for rule in sg.get('IpPermissions', []):
                cidrs = [r.get('CidrIp') for r in rule.get('IpRanges', [])]
                cidrs += [r.get('CidrIpv6') for r in rule.get('Ipv6Ranges', [])]
                if '0.0.0.0/0' in cidrs or '::/0' in cidrs:
                    protocol = rule.get('IpProtocol', '-1')
                    if protocol == '-1':
                        protocol = 'ALL'
                    permissive.append(
                        f"{sg['GroupId']} ({sg['GroupName']}) — "
                        f"{protocol} {rule.get('FromPort', '*')}-{rule.get('ToPort', '*')} "
                        f"from {'0.0.0.0/0' if '0.0.0.0/0' in cidrs else '::/0'}"
                    )

        if not permissive:
            return "No overly permissive inbound rules found (no 0.0.0.0/0 or ::/0)."
        return "Permissive inbound rules:\n" + "\n".join(f"  - {r}" for r in permissive)

    except Exception as e:
        logger.error(f"Error finding permissive rules: {e}")
        return f"Error finding permissive rules: {str(e)}"


@tool
def check_connectivity(source_ip: str, dest_ip: str, port: int) -> str:
    """
    Analyze potential connectivity between two IPs on a given port by fetching
    both ENIs and their associated security groups.

    Args:
        source_ip: Source IP address
        dest_ip: Destination IP address
        port: Destination port number

    Returns:
        ENI and security group details for both endpoints to aid connectivity analysis
    """
    try:
        source_ip = validate_ip(source_ip)
        dest_ip = validate_ip(dest_ip)
        port = validate_port(port)
    except ValueError as e:
        return f"Validation error: {e}"

    try:
        source_info = get_eni_by_ip(source_ip)
        dest_info = get_eni_by_ip(dest_ip)

        return (
            f"Connectivity check: {source_ip} → {dest_ip}:{port}\n\n"
            f"SOURCE ({source_ip}):\n{source_info}\n\n"
            f"DESTINATION ({dest_ip}):\n{dest_info}\n\n"
            "Next steps: inspect the security group rules on the destination ENI "
            "and the NACL for the destination subnet."
        )
    except Exception as e:
        logger.error(f"Error checking connectivity: {e}")
        return f"Error checking connectivity: {str(e)}"
