# Fargate Quick Start - McElveen Trading System

## 1️⃣ Pre-Deployment Checklist

```bash
# Check AWS CLI
aws --version

# Check Docker
docker --version

# Get AWS Account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: $AWS_ACCOUNT_ID"

# Verify DynamoDB tables exist
aws dynamodb list-tables --region us-east-1 | grep mcelveen

# Note your VPC and Subnet IDs
export VPC_ID=vpc-xxxxxxxx
export SUBNET_IDS=subnet-xxx,subnet-yyy
```

## 2️⃣ Deploy Everything

```bash
# Set environment
export AWS_REGION=us-east-1
export ENVIRONMENT=production

# Run deployment script (handles ECR, Docker build, and CloudFormation)
./scripts/deploy-to-fargate.sh
```

## 3️⃣ Verify Deployment

```bash
# List clusters
aws ecs list-clusters --region us-east-1

# List services
aws ecs list-services --cluster mcelveen-production --region us-east-1

# View token refresh service status
aws ecs describe-services \
  --cluster mcelveen-production \
  --services mcelveen-token-refresh-service \
  --region us-east-1
```

## 4️⃣ Monitor Logs

```bash
# Trading System (runs daily at 3:55 PM)
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1

# Daily Report (runs daily at 4:05 PM)
aws logs tail /ecs/mcelveen-daily-report --follow --region us-east-1

# Token Refresh (continuous)
aws logs tail /ecs/mcelveen-token-refresh --follow --region us-east-1
```

## 5️⃣ Test Manually

```bash
# Get cluster and subnet/security group info
CLUSTER="mcelveen-production"
TASK_DEF="mcelveen-trading-system:1"  # or latest version
SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[0].SubnetId' --output text)
SECURITY_GROUP=$(aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=mcelveen-ecs-sg*" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Manually run trading system task
aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $TASK_DEF \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SECURITY_GROUP],assignPublicIp=DISABLED}" \
  --region us-east-1

# Monitor the task
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1
```

## 6️⃣ Common Commands

### View Running Tasks
```bash
aws ecs list-tasks --cluster mcelveen-production --region us-east-1
```

### Stop a Running Task
```bash
# Get task ARN from list-tasks output
aws ecs stop-task --cluster mcelveen-production --task <task-arn> --region us-east-1
```

### Update Task Definition
```bash
# After updating code and rebuilding Docker image
./scripts/deploy-to-fargate.sh
```

### Scale Token Refresh Service
```bash
# Change desired count to 2 instances
aws ecs update-service \
  --cluster mcelveen-production \
  --service mcelveen-token-refresh-service \
  --desired-count 2 \
  --region us-east-1
```

### View EventBridge Rules
```bash
aws events list-rules --region us-east-1 | grep mcelveen
```

### Check CloudFormation Stack
```bash
aws cloudformation describe-stacks --stack-name mcelveen-ecs-production --region us-east-1
```

## 7️⃣ Local Testing

```bash
# Build and test locally with Docker Compose
cd docker
docker-compose -f docker-compose.yml up -d

# Wait for services to start
sleep 30

# Test health checks
curl http://localhost:8001/health  # Trading System
curl http://localhost:8002/health  # Daily Report
curl http://localhost:8003/health  # Token Refresh

# View logs
docker-compose -f docker-compose.yml logs -f

# Stop
docker-compose -f docker-compose.yml down
```

## 8️⃣ Troubleshooting

### Tasks not starting?
```bash
# Check task definition
aws ecs describe-task-definition --task-definition mcelveen-trading-system --region us-east-1

# Check logs
aws logs describe-log-streams --log-group-name /ecs/mcelveen-trading-system --region us-east-1
aws logs get-log-events --log-group-name /ecs/mcelveen-trading-system \
  --log-stream-name <stream-name> --region us-east-1
```

### DynamoDB permission denied?
```bash
# Verify IAM role policy
aws iam get-role-policy --role-name mcelveen-trading-system-task-role \
  --policy-name DynamoDBAccess

# Check role trust relationship
aws iam get-role --role-name mcelveen-trading-system-task-role
```

### EventBridge rule not triggering?
```bash
# Check rule is enabled
aws events describe-rule --name mcelveen-trading-system-trigger --region us-east-1

# Check targets
aws events list-targets-by-rule --rule mcelveen-trading-system-trigger --region us-east-1
```

## 9️⃣ Cost Optimization

### Estimate Monthly Costs

**Trading System (1 task/day for 1 minute)**
- CPU: 512 (0.5 vCPU) × $0.04665/vCPU-hour × (1 min/day × 30 days / 60 min/hour) = $0.01
- Memory: 1GB × $0.00511/GB-hour × (1 min/day × 30 days / 60 min/hour) = $0.003
- **Subtotal: ~$0.02/month**

**Daily Report (1 task/day for 2 minutes)**
- CPU: 256 (0.25 vCPU) × $0.04665/vCPU-hour × (2 min/day × 30 days / 60 min/hour) = $0.01
- Memory: 512MB × $0.00511/GB-hour × (2 min/day × 30 days / 60 min/hour) = $0.002
- **Subtotal: ~$0.01/month**

**Token Refresh (continuous, 24/7)**
- CPU: 256 (0.25 vCPU) × $0.04665/vCPU-hour × (24 × 30) = $8.40
- Memory: 512MB × $0.00511/GB-hour × (24 × 30) = $3.67
- **Subtotal: ~$12/month**

**Total: ~$12.04/month** (vs ~$5-10 for Lambda with cold start issues)

## 🔟 Next Steps

1. ✅ Deploy with `./scripts/deploy-to-fargate.sh`
2. ✅ Monitor logs daily for first week
3. ✅ Set up CloudWatch alarms for failures
4. ✅ Schedule weekly cost reviews
5. ✅ Plan auto-scaling if needed

---

**For detailed guide:** See `FARGATE_MIGRATION_GUIDE.md`
