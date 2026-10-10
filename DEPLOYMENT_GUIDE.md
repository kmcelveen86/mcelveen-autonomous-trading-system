# McElveen Autonomous Trading System - Deployment Guide
## Complete Phase 1A & 1B AWS Setup for Personal Account

**Date:** Oct 9, 2026  
**Target Deployment:** Oct 15, 2026  
**System:** McElveen Autonomous Forex Trading (v3.0.33 + v3.0.34)

---

## Prerequisites

### AWS Account Setup
- AWS Account with sufficient permissions (EC2, Lambda, DynamoDB, CloudWatch, EventBridge, IAM)
- AWS CLI configured with profile (or use `default`)
- Schwab developer account with API credentials
- Fresh Schwab refresh token (from OAuth flow)

### Local Setup
```bash
# Install AWS CLI (if not already installed)
pip install awscli

# Configure AWS profile
aws configure --profile mcelveen
# Enter: Access Key ID, Secret Access Key, Region (us-east-2), Output format (json)

# Verify AWS CLI
aws sts get-caller-identity --profile mcelveen
```

### Required Environment Variables
```bash
# Schwab OAuth Credentials
export SCHWAB_CLIENT_ID="<your-client-id>"
export SCHWAB_CLIENT_SECRET="<your-client-secret>"
export SCHWAB_ACCOUNT_ID="7720-9306"
export SCHWAB_REFRESH_TOKEN="<fresh-token-from-oauth>"
```

---

## Deployment Process

### Phase 1A: Infrastructure Setup (Oct 15 Morning)

**Time Required:** 10-15 minutes  
**What Gets Created:** DynamoDB tables, Lambda functions, IAM roles, EventBridge rules

```bash
# Navigate to repository
cd mcelveen-autonomous-trading-system

# Make deployment script executable
chmod +x deploy-phase-1a.sh

# Run Phase 1A deployment
./deploy-phase-1a.sh mcelveen
```

**What This Does:**
1. ✅ Creates `mcelveen-forex-trades` DynamoDB table
2. ✅ Creates `mcelveen-forex-metrics` DynamoDB table
3. ✅ Creates/updates `Lambda-EventBridge-Role` IAM role
4. ✅ Deploys `mcelveen-hybrid-trading-v3.0.33` Lambda function
5. ✅ Creates EventBridge rule: every 15 minutes (forex hours)
6. ✅ Creates EventBridge rule: daily at 4:01 PM ET (reports)
7. ✅ Validates all resources created

**Expected Output:**
```
==========================================
Phase 1A Deployment Complete!
==========================================

Next Steps:
1. Set SCHWAB_REFRESH_TOKEN in Lambda environment:
   aws lambda update-function-configuration ...
2. Test the router:
   aws lambda invoke --function-name mcelveen-hybrid-trading-v3.0.33 ...
3. Proceed to Phase 1B deployment:
   ./deploy-phase-1b.sh mcelveen
```

---

### Phase 1B: Execution Layer Deployment (Oct 15 Afternoon)

**Time Required:** 10-15 minutes  
**What Gets Created:** Forex execution Lambda, router→execution chain

```bash
# Run Phase 1B deployment
./deploy-phase-1b.sh mcelveen
```

**What This Does:**
1. ✅ Deploys `mcelveen-forex-execution-v3.0.34` Lambda function
2. ✅ Configures v3.0.33 to invoke v3.0.34 (router→execution chain)
3. ✅ Sets up permission for chain invocation
4. ✅ Runs validation tests (direct invocation, chain test, logs check)
5. ✅ Displays configuration summary

**Expected Output:**
```
==========================================
Phase 1B Deployment Complete!
==========================================

System Status:
✓ v3.0.33 Router deployed
✓ v3.0.34 Execution deployed
✓ Router → Execution chain configured
✓ EventBridge triggers set (every 15 min)
✓ DynamoDB tables ready
✓ CloudWatch metrics namespace ready
```

---

## Post-Deployment Configuration

### Step 1: Update Schwab Credentials

After Phase 1A & 1B deployment, update both Lambda functions with your fresh Schwab token:

```bash
AWS_PROFILE=mcelveen
AWS_REGION=us-east-2

# Update v3.0.33 Router
aws lambda update-function-configuration \
  --function-name mcelveon-hybrid-trading-v3.0.33 \
  --environment Variables="{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,SCHWAB_REFRESH_TOKEN=<YOUR-FRESH-TOKEN>,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
  --region $AWS_REGION \
  --profile $AWS_PROFILE

# Update v3.0.34 Execution
aws lambda update-function-configuration \
  --function-name mcelveen-forex-execution-v3.0.34 \
  --environment Variables="{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
  --region $AWS_REGION \
  --profile $AWS_PROFILE
```

### Step 2: Test the Router

Verify v3.0.33 routing logic works:

```bash
aws lambda invoke \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 \
  --profile mcelveen \
  /tmp/router-test.json && jq . /tmp/router-test.json
```

**Expected Response (during Forex hours):**
```json
{
  "statusCode": 200,
  "body": {
    "mode": "FOREX",
    "status": "ROUTING_CONFIGURED",
    "macro_analysis": {
      "regime": "NEUTRAL",
      "conviction": 0.50,
      "recommended_pairs": ["EUR/USD", "USD/CAD"]
    }
  }
}
```

### Step 3: Test the Execution Chain

Verify v3.0.33 → v3.0.34 invocation works:

```bash
# (Same command as above - if it invokes v3.0.34 successfully, you'll see execution results)
aws lambda invoke \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 \
  --profile mcelveen \
  --payload '{"action":"EXECUTE"}' \
  /tmp/chain-test.json && jq . /tmp/chain-test.json
```

---

## Monitoring & Validation

### Check DynamoDB Tables

```bash
# List tables
aws dynamodb list-tables --region us-east-2 --profile mcelveen

# Scan trade log (after first execution)
aws dynamodb scan \
  --table-name mcelveen-forex-trades \
  --region us-east-2 \
  --profile mcelveen
```

### Monitor CloudWatch Logs

```bash
# Watch v3.0.33 router logs
aws logs tail /aws/lambda/mcelveen-hybrid-trading-v3.0.33 --follow --region us-east-2 --profile mcelveen

# Watch v3.0.34 execution logs
aws logs tail /aws/lambda/mcelveen-forex-execution-v3.0.34 --follow --region us-east-2 --profile mcelveen
```

### Check CloudWatch Metrics

```bash
# Query DailyPnL metric
aws cloudwatch get-metric-statistics \
  --namespace McElveen/Forex \
  --metric-name DailyPnL \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region us-east-2 \
  --profile mcelveen
```

---

## Deployment Checklist

### Phase 1A Infrastructure
- [ ] AWS CLI configured with profile
- [ ] `deploy-phase-1a.sh` script executed successfully
- [ ] DynamoDB tables created (mcelveen-forex-trades, mcelveen-forex-metrics)
- [ ] Lambda function deployed (mcelveen-hybrid-trading-v3.0.33)
- [ ] EventBridge rules created (15-min, daily 4 PM)
- [ ] IAM role configured with DynamoDB + CloudWatch permissions

### Phase 1B Execution Layer
- [ ] `deploy-phase-1b.sh` script executed successfully
- [ ] v3.0.34 Lambda function deployed
- [ ] v3.0.33 → v3.0.34 invocation chain configured
- [ ] Lambda permissions set (router can invoke execution)
- [ ] Validation tests passed (direct invocation, chain test)

### Post-Deployment Configuration
- [ ] Schwab refresh token updated in both Lambda functions
- [ ] Router invocation test passed (returns FOREX mode + macro analysis)
- [ ] Execution chain test passed (returns execution results)
- [ ] CloudWatch logs visible for both functions
- [ ] DynamoDB tables accessible and ready for trades

### Live Trading (Oct 15 onwards)
- [ ] First trade logged to DynamoDB by Oct 16
- [ ] Daily metrics published to CloudWatch
- [ ] 7+ trades collected by Nov 5 (baseline data)
- [ ] No execution errors in CloudWatch logs

---

## Troubleshooting

### Problem: "AccessDenied: User is not authorized to perform: dynamodb:CreateTable"

**Solution:** Update IAM user/role to include DynamoDB, Lambda, and CloudWatch permissions. Or use root AWS account credentials.

### Problem: "ResourceNotFoundException: Requested resource not found"

**Solution:** Lambda function or DynamoDB table not found. Verify script completed successfully, or check table/function names in AWS console.

### Problem: Lambda invocation returns no results

**Solution:** Check CloudWatch logs for errors. Verify Schwab credentials are set in environment variables.

### Problem: "eventbridge.amazonaws.com is not authorized to assume the role"

**Solution:** Trust policy in IAM role needs to include `events.amazonaws.com`. Run Phase 1A script again to fix.

### Problem: Trades not appearing in DynamoDB

**Solution:** 
1. Verify v3.0.34 Lambda is being invoked (check CloudWatch logs)
2. Verify DynamoDB table permissions in IAM role
3. Check if Schwab API credentials are fresh (< 30 minutes old)

---

## Timeline

```
Oct 9, 2026   - Code complete, committed to GitHub
Oct 15, 2026  - Phase 1A deployment (morning) + Phase 1B deployment (afternoon)
Oct 15-Nov 5  - Baseline data collection (7+ weeks, 50+ trades)
Nov 5-20      - Phase 1C: ML integration & A/B testing
Nov 20-Feb 28 - Phase 2: Live ML trading (12 weeks)
Q2 2027       - Paylinq investor pitch (12-month data)
```

---

## Support & Questions

### Deployment Issues
- Check CloudWatch logs: `/aws/lambda/mcelveen-*`
- Verify AWS credentials and permissions
- Review DynamoDB table schemas
- Test Lambda functions manually via AWS Console

### Code Issues
- Review PHASE_1A_SUMMARY.md for architecture
- Review PHASE_1B_SUMMARY.md for execution layer
- Check v3.0.33_hybrid_forex_system.py for router logic
- Check v3.0.34_forex_execution.py for execution logic

### Schwab API Issues
- Verify OAuth token is fresh (< 30 min old)
- Check Schwab API documentation
- Verify account ID matches (7720-9306)
- Test quote fetching manually

---

## Next Steps After Deployment

1. **Oct 15-16:** Monitor first forex trades execute and log to DynamoDB
2. **Oct 15-Nov 5:** Collect baseline data (target: 50+ trades)
3. **Nov 5:** Prepare Phase 1C ML integration
4. **Nov 5-20:** Train and test ML models on baseline data
5. **Nov 20:** Launch Phase 2 live ML trading
6. **Q2 2027:** Present to Paylinq investors with 12-month results

---

**McElveen Autonomous Trading System - Ready for Deployment** 🚀
