# McElveen Deployment - Quick Reference Card
**October 15, 2026 | Deployment Day Checklist**

---

## Prerequisites Ready? ✅
Before 9 AM:
- [ ] AWS CLI configured: `aws sts get-caller-identity --profile mcelveen`
- [ ] Fresh Schwab refresh token ready (< 24 hrs old)
- [ ] In correct directory: `cd /home/claude/mcelveen-autonomous-trading-system`

---

## Morning Phase 1A (9:00 AM)
```bash
./deploy-phase-1a.sh mcelveen
```
**Watch for:** ✓ DynamoDB tables, ✓ IAM role, ✓ Lambda deployed, ✓ EventBridge rules  
**Time:** ~10-15 minutes  
**If error:** Check AWS permissions, see DEPLOYMENT_GUIDE.md troubleshooting

---

## Validate Phase 1A (After script completes)
```bash
aws dynamodb list-tables --region us-east-2 --profile mcelveen
aws lambda get-function --function-name mcelveen-hybrid-trading-v3.0.33 --region us-east-2 --profile mcelveen
aws events list-rules --name-prefix mcelveen-forex --region us-east-2 --profile mcelveen
```
**Expected:** Both tables listed, Lambda function found, both rules listed

---

## Lunch Break (11:00 AM - 1:00 PM)

---

## Afternoon Phase 1B (1:00 PM)
```bash
./deploy-phase-1b.sh mcelveen
```
**Watch for:** ✓ v3.0.34 deployed, ✓ Chain configured, ✓ Tests passed  
**Time:** ~10-15 minutes  
**If error:** Check Phase 1A completed, see PHASE_1B_DEPLOYMENT_GUIDE.md

---

## Post-Deployment Config (2:00 PM)
**Replace `<YOUR-FRESH-TOKEN>` with Schwab refresh token:**

```bash
# Update v3.0.33 Router
aws lambda update-function-configuration \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --environment Variables="{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,SCHWAB_REFRESH_TOKEN=<YOUR-FRESH-TOKEN>,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
  --region us-east-2 --profile mcelveen

# Update v3.0.34 Execution
aws lambda update-function-configuration \
  --function-name mcelveen-forex-execution-v3.0.34 \
  --environment Variables="{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
  --region us-east-2 --profile mcelveen
```

---

## Test Router (2:30 PM)
```bash
aws lambda invoke --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 --profile mcelveen /tmp/test.json && cat /tmp/test.json | jq .
```
**Expected:** statusCode 200, body with FOREX mode if during forex hours

---

## Test Execution Chain (3:00 PM)
```bash
aws lambda invoke --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 --profile mcelveen \
  --payload '{"action":"EXECUTE"}' /tmp/chain.json && cat /tmp/chain.json | jq .
```
**Expected:** statusCode 200, execution results

---

## Monitor CloudWatch Logs (3:30 PM)
```bash
aws logs tail /aws/lambda/mcelveen-hybrid-trading-v3.0.33 --region us-east-2 --profile mcelveen
aws logs tail /aws/lambda/mcelveen-forex-execution-v3.0.34 --region us-east-2 --profile mcelveen
```
**Expected:** Recent log entries from both functions

---

## End of Day Checklist (4:00 PM)
- [ ] Phase 1A script completed without errors
- [ ] Phase 1B script completed without errors  
- [ ] Both Lambda functions deployed
- [ ] Schwab credentials updated in both Lambdas
- [ ] Router test passed (status 200)
- [ ] Execution test passed (status 200)
- [ ] CloudWatch logs showing activity
- [ ] DynamoDB tables empty (awaiting first trade)

---

## Monitoring (Oct 15-16)
**First forex trade should execute by Oct 16 morning during forex hours**

```bash
# Check for trades in DynamoDB
aws dynamodb scan --table-name mcelveen-forex-trades --region us-east-2 --profile mcelveen

# Check CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace McElveen/Forex \
  --metric-name DailyPnL \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum --region us-east-2 --profile mcelveen
```

---

## Troubleshooting Quick Links
- **Deployment errors:** See DEPLOYMENT_GUIDE.md → Troubleshooting
- **Phase 1B issues:** See PHASE_1B_DEPLOYMENT_GUIDE.md → Troubleshooting Phase 1B
- **Technical specs:** See PHASE_1B_SUMMARY.md
- **Architecture overview:** See PHASE_1A_SUMMARY.md

---

## Timeline Ahead
- **Oct 15-Nov 5:** Baseline data collection (target: 50+ trades)
- **Nov 5-20:** Phase 1C ML integration & A/B testing
- **Nov 20-Feb 28:** Phase 2 Live ML trading (12 weeks)
- **Q2 2027:** Paylinq investor pitch with 12-month data

---

**Status:** Ready for deployment Oct 15, 2026 🚀
