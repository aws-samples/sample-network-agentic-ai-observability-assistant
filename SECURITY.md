# Security Policy

## Disclaimer

This project is provided as sample/educational code and is NOT intended for production
use without additional security hardening and review. See "Production Hardening
Recommendations" below.

## Reporting Vulnerabilities

If you discover a security vulnerability in this project, please report it by emailing
aws-security@amazon.com. Do not report security vulnerabilities through public GitHub issues.

## AWS Services Used

- **Amazon Bedrock (AgentCore)** — hosts the generative-AI agents (Anthropic Claude models)
- **Amazon VPC** — the assistant reads VPC Flow Logs and network configuration (read-only)
- **Amazon CloudWatch Logs** — queried via Logs Insights for VPC Flow Log analysis (read-only)
- **AWS Network Firewall** — firewall policy and rule-group inspection (read-only)
- **Amazon EC2 (networking)** — security groups, route tables, ENIs described (read-only)

## Prerequisites and Permissions

To run this solution you need:
- An AWS account with read-only permissions to the services above (see the example
  policy in the README — it uses ec2:Describe*, logs:StartQuery/GetQueryResults,
  network-firewall:Describe*/List* and similar read-only actions).
- Access to Amazon Bedrock with the configured Claude model enabled in your region.
- Python 3.x and the dependencies in requirements.txt.

## Known Security Considerations

| Item | Category | Rationale |
|------|----------|-----------|
| Free-text prompts sent to the model without output guardrails | Security Debt (NB-4) | Read-only tool set limits impact; add Bedrock Guardrails for production. |
| Best-effort `except Exception: pass` in firewall_tools.py | Security Debt (NB-1) | Non-security; narrow the exception and log for diagnosability. |

## Production Hardening Recommendations

Before using this code in production:
- Add Amazon Bedrock Guardrails on model invocations to filter prompt injection and unsafe output.
- Scope the IAM policy to the specific resources/regions in scope rather than `Resource: "*"` on describe actions.
- Enable CloudTrail and monitor the read-only API calls the agent makes.
- Add Responsible AI usage documentation describing intended use and limitations.
- Pin all dependencies (runtime and dev) and run pip-audit in CI.

## Resource Cleanup

This sample does not deploy standing infrastructure. To clean up:
1. Remove the local virtual environment and any downloaded model configuration.
2. Revoke or delete any IAM policy/role created to run the agent.
3. Disable Bedrock model access if it was enabled solely for this sample.

## Dependencies

| Dependency | Version | Notes |
|------------|---------|-------|
| strands-agents | pinned in requirements.txt | Agent framework |
| boto3 | pinned in requirements.txt | AWS SDK — read-only usage |
| bedrock-agentcore-starter-toolkit | pinned in requirements.txt | Dev/deploy tooling |
| pytest | pinned in requirements.txt | Test framework |
| pytest-asyncio | pinned in requirements.txt | Async test support |
