# Fargate Deployment Checklist - McElveen Trading System

## 📋 Pre-Deployment Verification

### AWS Prerequisites
- [ ] AWS Account configured with CLI
- [ ] IAM permissions to create ECR, ECS, CloudFormation, EventBridge, CloudWatch
- [ ] VPC ID noted: `________________`
- [ ] Private Subnet IDs noted: `________________`
- [ ] DynamoDB tables exist: `mcelveen-oauth-tokens`, `mcelveen-trades-table`, `mcelveen-positions-snapshot`
- [ ] Schwab OAuth token already in DynamoDB

### Local Environment
- [ ] AWS CLI v2 installed (`aws --version`)
- [ ] Docker installed (`docker --version`)
- [ ] GitHub repo cloned: `/tmp/mcelveen-repo`
- [ ] Git commits ready to push
- [ ] Python 3.11+ available for testing

### Code Readiness
- [ ] `lambda_function_v3.0.44_HYBRID.py` tested and verified
- [ ] `mcelveen_daily_report_v4_token_synced.py` tested and verified
- [ ] `McElveenTokenRefresh.py` tested and verified
- [ ] `requirements.txt` updated with all dependencies
- [ ] Health check endpoints added to code (or will add during migration)

---

## 🔧 Deployment Steps

### Step 1: Set Environment Variables
```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=________________  # Your account ID
export VPC_ID=vpc-________________
export SUBNET_IDS=subnet-xxx,subnet-yyy
export ENVIRONMENT=production
```
- [ ] Environment variables exported

### Step 2: Test Locally with Docker Compose
```bash
cd docker
docker-compose -f docker-compose.yml up -d
sleep 30

# Health checks
curl http://localhost:8001/health  # Trading System
curl http://localhost:8002/health  # Daily Report
curl http://localhost:8003/health  # Token Refresh

docker-compose -f docker-compose.yml logs -f
docker-compose -f docker-compose.yml down
```
- [ ] Docker Compose test successful
- [ ] All health checks passing

### Step 3: Deploy to AWS
```bash
cd /tmp/mcelveen-repo
./scripts/deploy-to-fargate.sh
```
- [ ] ECR repositories created
- [ ] Docker images built successfully
- [ ] Images pushed to ECR
- [ ] CloudFormation stack deployed
- [ ] Deployment script completed without errors

### Step 4: Verify ECS Resources
```bash
# Check cluster
aws ecs describe-clusters --clusters mcelveen-production --region us-east-1

# Check services
aws ecs list-services --cluster mcelveen-production --region us-east-1

# Check token refresh service
aws ecs describe-services \
  --cluster mcelveen-production \
  --services mcelveen-token-refresh-service \
  --region us-east-1
```
- [ ] ECS Cluster created: `mcelveen-production`
- [ ] Token Refresh service running (desired count = 1)
- [ ] Task definitions registered
- [ ] Security groups created
- [ ] IAM roles created

### Step 5: Verify EventBridge Rules
```bash
# List all EventBridge rules
aws events list-rules --region us-east-1 | grep mcelveen

# Check trading system rules are enabled
aws events describe-rule --name mcelveen-trading-system-0930 --region us-east-1
aws events describe-rule --name mcelveen-trading-system-10 --region us-east-1
# ... check all hours (9, 10, 11, 12, 13, 14, 15, 16)

# Check daily report rule
aws events describe-rule --name mcelveen-daily-report --region us-east-1
```
- [ ] Trading system rules created (8 rules for different hours)
- [ ] All trading system rules set to ENABLED
- [ ] Daily report rule created and ENABLED
- [ ] Rules have ECS task as target

### Step 6: Verify CloudWatch Logs
```bash
# List log groups
aws logs describe-log-groups --region us-east-1 | grep mcelveen

# Check logs exist
aws logs describe-log-streams --log-group-name /ecs/mcelveen-trading-system --region us-east-1
aws logs describe-log-streams --log-group-name /ecs/mcelveen-daily-report --region us-east-1
aws logs describe-log-streams --log-group-name /ecs/mcelveen-token-refresh --region us-east-1
```
- [ ] Log group created: `/ecs/mcelveen-trading-system`
- [ ] Log group created: `/ecs/mcelveen-daily-report`
- [ ] Log group created: `/ecs/mcelveen-token-refresh`
- [ ] Log retention set to 30 days (trading/daily) and 7 days (token)

---

## ✅ Post-Deployment Verification

### Test Trading System Manually
```bash
# Get cluster and resources
CLUSTER="mcelveen-production"
TASK_DEF="mcelveen-trading-system:1"
SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[0].SubnetId' --output text)
SG=$(aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=mcelveen-ecs-sg*" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Run task manually
aws ecs run-task \
  --cluster $CLUSTER \
  --task-definition $TASK_DEF \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --region us-east-1

# Monitor logs
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1
```
- [ ] Task started successfully
- [ ] Task reached RUNNING state
- [ ] Logs appear in CloudWatch within 30 seconds
- [ ] Task completed without errors

### Test Daily Report Manually
```bash
# Similar process for daily report
aws ecs run-task \
  --cluster mcelveen-production \
  --task-definition mcelveen-daily-report:1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --region us-east-1

aws logs tail /ecs/mcelveen-daily-report --follow --region us-east-1
```
- [ ] Task started successfully
- [ ] Logs show P&L report generation
- [ ] SNS notification sent successfully

### Verify Token Refresh Service
```bash
# Check service is running
aws ecs describe-services \
  --cluster mcelveen-production \
  --services mcelveen-token-refresh-service \
  --region us-east-1 \
  --query 'services[0].[runningCount,desiredCount,status]'

# Check logs
aws logs tail /ecs/mcelveen-token-refresh --follow --region us-east-1
```
- [ ] Token Refresh service running (runningCount = 1, desiredCount = 1)
- [ ] Service status = ACTIVE
- [ ] Logs show token refresh occurring every 30 minutes
- [ ] DynamoDB `mcelveen-oauth-tokens` is being updated

### Verify Scheduled Execution (Wait for Next 5-Min Cycle)
```bash
# Check if tasks auto-triggered by EventBridge
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1

# Should see new logs around trading hours:
# - 9:30, 9:35, 9:40, 9:45, 9:50, 9:55 AM
# - 10:00, 10:05, ... throughout day
# - 4:00 PM (market close)
```
- [ ] Trading system tasks auto-triggered by EventBridge
- [ ] Tasks appear every 5 minutes during market hours
- [ ] Daily report task auto-triggered at 4:05 PM
- [ ] No manual intervention required

---

## 📊 Monitoring Setup

### Create CloudWatch Alarms
```bash
# Alarm for trading system task failures
aws cloudwatch put-metric-alarm \
  --alarm-name mcelveen-trading-system-failures \
  --alarm-description "Alert when trading system tasks fail" \
  --metric-name TasksFailed \
  --namespace ECS/ContainerInsights \
  --dimensions Name=ServiceName,Value=mcelveen-trading-system \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --alarm-actions "arn:aws:sns:us-east-1:ACCOUNT_ID:mcelveen-alerts"

# Alarm for token refresh service
aws cloudwatch put-metric-alarm \
  --alarm-name mcelveen-token-refresh-health \
  --alarm-description "Alert if token refresh service stops" \
  --metric-name RunningCount \
  --namespace ECS/ContainerInsights \
  --dimensions Name=ServiceName,Value=mcelveen-token-refresh-service \
  --statistic Minimum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 1 \
  --comparison-operator LessThanThreshold \
  --alarm-actions "arn:aws:sns:us-east-1:ACCOUNT_ID:mcelveen-alerts"
```
- [ ] Created CloudWatch alarms for task failures
- [ ] Created CloudWatch alarms for service health
- [ ] SNS topic for alerts configured

### Setup CloudWatch Dashboard
```bash
# Create dashboard for monitoring
aws cloudwatch put-dashboard \
  --dashboard-name McElveenTrading \
  --dashboard-body file://cloudwatch-dashboard.json
```
- [ ] CloudWatch dashboard created
- [ ] Dashboard shows CPU, Memory, Task count
- [ ] Dashboard shows log errors and warnings

---

## 🚀 Go-Live Checklist

### Before Market Hours (Morning of First Day)
- [ ] Verify all services running without errors
- [ ] Check EventBridge rules are ENABLED
- [ ] Confirm token is fresh in DynamoDB (within last 30 mins)
- [ ] Test manual task execution (should complete in <2 minutes)
- [ ] Review CloudWatch logs from previous day
- [ ] Confirm backup/disaster recovery plan

### During Market Hours (First Day of Trading)
- [ ] Monitor logs in real-time: `aws logs tail /ecs/mcelveen-trading-system --follow`
- [ ] Verify tasks trigger every 5 minutes
- [ ] Check DynamoDB `mcelveen-trades-table` being updated
- [ ] Check `mcelveen-positions-snapshot` being updated
- [ ] Monitor task duration (should be 1-2 minutes each)
- [ ] Verify no errors in CloudWatch logs

### After Market Close (First Day)
- [ ] Verify Daily Report executed at 4:05 PM
- [ ] Confirm P&L report calculated correctly
- [ ] Verify SNS email sent
- [ ] Review first day's trading metrics
- [ ] Check cost estimate

### First Week of Trading
- [ ] Daily monitoring of logs
- [ ] Weekly cost review
- [ ] Document any issues or tweaks needed
- [ ] Tune resource allocation if needed

---

## 📁 Files Created/Modified

### Docker Files
- ✅ `docker/Dockerfile.trading-system` - Trading system container
- ✅ `docker/Dockerfile.daily-report` - Daily report container
- ✅ `docker/Dockerfile.token-refresh` - Token refresh service
- ✅ `docker/docker-compose.yml` - Local testing compose file
- ✅ `requirements.txt` - Updated Python dependencies

### Infrastructure Files
- ✅ `ecs/cloudformation-ecs-fargate.yaml` - Complete infrastructure stack
- ✅ `ecs/task-definition-trading-system.json` - Trading system task definition
- ✅ `ecs/task-definition-daily-report.json` - Daily report task definition
- ✅ `ecs/task-definition-token-refresh.json` - Token refresh task definition
- ✅ `ecs/iam-policies.json` - IAM policies for task roles

### Deployment Scripts
- ✅ `scripts/deploy-to-fargate.sh` - Main deployment script
- ✅ `scripts/enable-trading.sh` - Enable EventBridge rules
- ✅ `scripts/disable-trading.sh` - Disable EventBridge rules

### Documentation
- ✅ `FARGATE_MIGRATION_GUIDE.md` - Complete migration guide
- ✅ `FARGATE_QUICK_START.md` - Quick reference guide
- ✅ `TRADING_SCHEDULE.md` - Market hours and schedule info
- ✅ `FARGATE_DEPLOYMENT_CHECKLIST.md` - This file

---

## 🆘 Rollback Procedure

If you need to rollback to Lambda:

```bash
# 1. Disable EventBridge rules
aws events put-rule --name mcelveen-trading-system-0930 --state DISABLED
# ... disable all trading system rules

# 2. Update EventBridge targets back to Lambda
aws events put-targets --rule mcelveen-trading-system-0930 \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:ACCOUNT_ID:function:mcelveen-trading-system"

# 3. Delete Fargate resources
aws ecs delete-service --cluster mcelveen-production \
  --service mcelveen-token-refresh-service --force

# 4. Delete CloudFormation stack
aws cloudformation delete-stack --stack-name mcelveen-ecs-production

# 5. Cleanup ECR (optional)
aws ecr delete-repository --repository-name mcelveen-trading-system --force
```

- [ ] Rollback procedure documented
- [ ] Lambda functions still deployed and ready
- [ ] Previous EventBridge configuration saved
- [ ] DynamoDB backup created before going live

---

## ✨ Summary

**Total Execution Time:** ~30-45 minutes  
**Resources Created:**
- 1 ECS Cluster
- 3 ECS Task Definitions
- 1 ECS Service (Token Refresh)
- 8 EventBridge Rules (Trading System)
- 1 EventBridge Rule (Daily Report)
- 3 IAM Roles + Policies
- 3 CloudWatch Log Groups
- 3 ECR Repositories
- 1 Security Group

**Monthly Cost:** ~$24.10 (vs ~$5-10 for Lambda with intermittent cold start issues)

**Benefits:**
✅ No Lambda cold starts  
✅ Continuous token refresh  
✅ Better error handling and monitoring  
✅ Flexible execution times  
✅ Easy scaling  
✅ Cost predictable  

---

**Ready to Deploy?** Run: `./scripts/deploy-to-fargate.sh`

**Questions?** See `FARGATE_MIGRATION_GUIDE.md` for detailed help.

---

**Last Updated:** 2026-10-14  
**Status:** Ready for Deployment ✅
