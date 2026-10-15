# McElveen Autonomous Trading System - Lambda to Fargate Migration Guide

## Overview

This guide walks you through migrating the McElveen Trading System from AWS Lambda to ECS on Fargate. This provides better control, cost optimization, and improved scalability.

## Architecture Changes

### Before (Lambda)
```
EventBridge Rules → Lambda Functions → DynamoDB
                   (Cold starts, timeout issues)
```

### After (Fargate)
```
EventBridge Rules → ECS Tasks (Fargate) → DynamoDB
                   (Always warm, flexible timeout)

Continuous Service → Token Refresh Container → DynamoDB
                    (Running 24/7 for OAuth refresh)
```

## Benefits

| Aspect | Lambda | Fargate |
|--------|--------|---------|
| **Cold Starts** | 3-5 seconds | Minimal |
| **Cost** | Higher for trading hours | Lower (pay per minute) |
| **Execution Time** | 15 min limit | Flexible (hours if needed) |
| **Token Refresh** | Every invoke | Continuous service |
| **Container Size** | 50MB limit | 16GB available |
| **Scaling** | Automatic | Manual (easily adjustable) |

## Prerequisites

### AWS Setup
1. AWS Account with appropriate permissions
2. AWS CLI v2 installed and configured
3. Docker installed locally
4. ECR repositories created (script handles this)

### Environment Variables
```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=123456789012
export VPC_ID=vpc-xxxxxxxx
export SUBNET_IDS=subnet-xxx,subnet-yyy
export ENVIRONMENT=production
```

### DynamoDB Tables
Ensure these exist with proper IAM permissions:
- `mcelveen-oauth-tokens`
- `mcelveen-trades-table`
- `mcelveen-positions-snapshot`

## Step 1: Prepare Code for Containerization

### 1.1 Update Python Code

The trading system code needs minor updates to run in containers:

**In `lambda_function_v3.0.44_HYBRID.py`:**

```python
# Add at the beginning
import logging
import os
import sys
from datetime import datetime

# Setup logging for container
logging.basicConfig(
    level=os.getenv('PYTHON_LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Modify Lambda handler to be callable as main
def lambda_handler(event, context):
    """Lambda handler for DynamoDB integration"""
    try:
        # ... existing code ...
        execute_trading_logic()
        return {
            'statusCode': 200,
            'body': 'Trading executed successfully'
        }
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': f'Error: {str(e)}'
        }

if __name__ == '__main__':
    # Container entry point
    event = {}
    context = {}
    result = lambda_handler(event, context)
    logger.info(f"Result: {result}")
    sys.exit(0 if result['statusCode'] == 200 else 1)
```

**In `mcelveen_daily_report_v4_token_synced.py`:**

```python
# Similar structure
if __name__ == '__main__':
    # Container entry point
    event = {}
    context = {}
    result = lambda_handler(event, context)
    sys.exit(0 if result['statusCode'] == 200 else 1)
```

### 1.2 Create Health Check Endpoints

Add a simple HTTP server for health checks:

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "healthy"}')
        else:
            self.send_response(404)
            self.end_headers()

def start_health_check_server(port=8080):
    """Start health check server in background thread"""
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
```

## Step 2: Build and Push Docker Images

### 2.1 Local Testing with Docker Compose

Test locally before pushing to AWS:

```bash
cd /tmp/mcelveen-repo
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f trading-system

# Test health check
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health

# Stop services
docker-compose -f docker/docker-compose.yml down
```

### 2.2 Deploy to AWS

```bash
# Set environment variables
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export VPC_ID=vpc-xxxxxxxx
export SUBNET_IDS=subnet-xxx,subnet-yyy
export ENVIRONMENT=production

# Run deployment script
./scripts/deploy-to-fargate.sh
```

The script will:
1. ✓ Check AWS CLI and Docker
2. ✓ Create ECR repositories
3. ✓ Build Docker images
4. ✓ Push images to ECR
5. ✓ Deploy CloudFormation stack
6. ✓ Create ECS cluster
7. ✓ Set up EventBridge rules
8. ✓ Launch token refresh service

## Step 3: Verify Deployment

### 3.1 Check ECS Cluster

```bash
# List clusters
aws ecs list-clusters --region us-east-1

# List services
aws ecs list-services --cluster mcelveen-production --region us-east-1

# Describe cluster
aws ecs describe-clusters --clusters mcelveen-production --region us-east-1
```

### 3.2 View Logs

```bash
# Trading System logs
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1

# Daily Report logs
aws logs tail /ecs/mcelveen-daily-report --follow --region us-east-1

# Token Refresh logs
aws logs tail /ecs/mcelveen-token-refresh --follow --region us-east-1
```

### 3.3 Monitor EventBridge Rules

```bash
# List EventBridge rules
aws events list-rules --region us-east-1 | grep mcelveen

# View rule targets
aws events list-targets-by-rule --rule mcelveen-trading-system-trigger --region us-east-1
```

## Step 4: Testing & Verification

### 4.1 Manual Task Execution

Trigger a task manually to verify it works:

```bash
# Get cluster and task definition
CLUSTER="mcelveen-production"
TASK_DEF="mcelveen-trading-system"
SUBNET_ID="subnet-xxx"
SECURITY_GROUP="sg-xxx"

# Run trading system task
aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $TASK_DEF \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SECURITY_GROUP],assignPublicIp=DISABLED}" \
  --region us-east-1
```

### 4.2 Check Task Status

```bash
# List running tasks
aws ecs list-tasks --cluster mcelveen-production --region us-east-1

# Describe task
aws ecs describe-tasks --cluster mcelveen-production --tasks <task-arn> --region us-east-1
```

## Step 5: Monitor & Optimize

### 5.1 CloudWatch Metrics

```bash
# View container insights
aws cloudwatch get-metric-statistics \
  --namespace ECS/ContainerInsights \
  --metric-name CPUUtilized \
  --dimensions Name=ServiceName,Value=mcelveen-trading-system \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Average,Maximum \
  --region us-east-1
```

### 5.2 Cost Analysis

```bash
# Estimate Fargate costs
# Pricing: $0.04665 per vCPU-hour + $0.00511 per GB-hour

# Trading System: 512 CPU (0.5 vCPU) + 1024 MB (1 GB)
# Daily runs: 1 minute/day = 0.017 hours/day
# Monthly cost: 0.5 * 0.04665 + 1 * 0.00511 = ~$0.027 per invocation

# Token Refresh: 256 CPU (0.25 vCPU) + 512 MB (0.5 GB)
# Continuous: 24 * 30 = 720 hours/month
# Monthly cost: 0.25 * 0.04665 * 720 + 0.5 * 0.00511 * 720 = ~$51.30
```

## Step 6: Rollback Plan

If you need to rollback to Lambda:

### 6.1 Keep Lambda Functions Deployed

```bash
# Deploy trading system back to Lambda
aws lambda update-function-code \
  --function-name mcelveen-trading-system \
  --zip-file fileb://lambda_function_v3.0.44_HYBRID.zip
```

### 6.2 Update EventBridge Rules

```bash
# Switch rule target from ECS back to Lambda
aws events put-targets \
  --rule mcelveen-trading-system-trigger \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:ACCOUNT_ID:function:mcelveen-trading-system","RoleArn"="arn:aws:iam::ACCOUNT_ID:role/EventBridgeLambdaRole"
```

### 6.3 Delete Fargate Resources

```bash
# Delete ECS service
aws ecs delete-service --cluster mcelveen-production --service mcelveen-token-refresh-service --force

# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name mcelveen-ecs-production

# Delete ECR images
aws ecr delete-repository --repository-name mcelveen-trading-system --force
aws ecr delete-repository --repository-name mcelveen-daily-report --force
aws ecr delete-repository --repository-name mcelveen-token-refresh --force
```

## Troubleshooting

### Task fails to start

```bash
# Check task logs
aws logs describe-log-streams --log-group-name /ecs/mcelveen-trading-system

# Check task status
aws ecs describe-tasks --cluster mcelveen-production --tasks <task-arn>
```

### DynamoDB access denied

Verify IAM roles have correct permissions:

```bash
# Check task role policy
aws iam get-role-policy --role-name mcelveen-trading-system-task-role --policy-name DynamoDBAccess
```

### Token refresh not updating

Check the continuous service is running:

```bash
# List running tasks
aws ecs list-tasks --cluster mcelveen-production --service-name mcelveen-token-refresh-service

# Check logs
aws logs tail /ecs/mcelveen-token-refresh --follow
```

## Next Steps

1. ✓ Update Python code with health checks and main entry points
2. ✓ Test locally with docker-compose
3. ✓ Deploy to AWS using deploy script
4. ✓ Monitor logs and metrics
5. ✓ Optimize resource allocation based on metrics
6. ✓ Set up alarms for failures

## Support & Resources

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [AWS Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
- [ECS Task Definition Reference](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [EventBridge Scheduler](https://docs.aws.amazon.com/scheduler/)

---

**Last Updated:** 2026-10-14  
**Version:** 1.0
