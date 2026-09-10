# Prerequisites

## 1. Python

Python 3.13+ is recommended.

```bash
python --version
```

If not installed, download from [python.org](https://www.python.org/downloads/) or use your package manager:

```bash
# macOS
brew install python@3.13

# Amazon Linux / RHEL
sudo dnf install python3.13
```


## 2. AWS CLI

```bash
# Verify
aws --version
```

If not installed: [AWS CLI install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)


## 3. AWS Credentials

Configure credentials for an AWS account with permissions for Bedrock AgentCore,
Amazon Bedrock, EC2 (read-only), and CloudWatch Logs (read-only). These AWS managed
policies cover the requirements:
- `BedrockAgentCoreFullAccess`
- `AmazonBedrockFullAccess`
- `AmazonEC2ReadOnlyAccess`
- `CloudWatchLogsReadOnlyAccess`

Set up credentials with either IAM Identity Center (SSO) or IAM user access keys.

### Option A — IAM Identity Center (SSO)

```bash
aws configure sso
# follow the prompts to create a profile, then sign in:
aws sso login --profile <your-profile>
export AWS_PROFILE=<your-profile>
```

### Option B — IAM user access keys

```bash
aws configure
# enter your Access Key ID, Secret Access Key, and default region
```

### Verify credentials

```bash
aws sts get-caller-identity
```
