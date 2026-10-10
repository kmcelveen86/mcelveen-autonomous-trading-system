# McElveen Autonomous Trading System - Deployment Preflight Checklist
**Deployment Date:** October 15, 2026  
**Status:** Pre-Flight Checklist (Oct 9-14)

---

## Prerequisites Verification (Complete by Oct 14)

### ✅ AWS Account & CLI Setup
- [ ] AWS Account created and active
- [ ] AWS CLI installed locally
- [ ] AWS profile "mcelveen" configured with:
  - [ ] Access Key ID
  - [ ] Secret Access Key
  - [ ] Region: us-east-2
  - [ ] Output format: json
- [ ] Verify CLI works: `aws sts get-caller-identity --profile mcelveen`
- [ ] Account ID confirmed: **650589744593** (should match output above)

### ✅ Schwab Developer Account
- [ ] Schwab developer account created (developer.schwab.com)
- [ ] API app registered with:
  - [ ] Client ID: **<note your value>**
  - [ ] Client Secret: **<note your value>** (keep secret!)
- [ ] OAuth app configured for:
  - [ ] Redirect URI: `http://localhost:8000/callback` (or your OAuth callback URL)
  - [ ] Scopes: `PlaceTrades AccountAccess MoveMoney`

### ✅ Schwab OAuth Token
- [ ] Fresh Schwab refresh token obtained (within 24 hours of deployment)
- [ ] Token generation method documented:
  - [ ] Ran v3.0.32 token refresh locally? OR
  - [ ] Used Schwab OAuth flow manually? OR
  - [ ] Other method: ________________
- [ ] Token value: `<SCHWAB_REFRESH_TOKEN>` (save in secure location, will need on Oct 15)

### ✅ Repository & Code
- [ ] Repository cloned to local machine: `/home/claude/mcelveen-autonomous-trading-system`
- [ ] Latest commits pulled from GitHub
- [ ] Verify Phase 1A & 1B files present:
  - [ ] `deploy-phase-1a.sh` (executable)
  - [ ] `deploy-phase-1b.sh` (executable)
  - [ ] `v3.0.33_hybrid_forex_system.py`
  - [ ] `v3.0.34_forex_execution.py`
  - [ ] `DEPLOYMENT_GUIDE.md`
  - [ ] `PHASE_1B_DEPLOYMENT_GUIDE.md`

### ✅ IAM Permissions Check
- [ ] AWS IAM user/role has permissions for:
  - [ ] `dynamodb:CreateTable`
  - [ ] `lambda:CreateFunction`
  - [ ] `lambda:UpdateFunctionCode`
  - [ ] `iam:CreateRole`
  - [ ] `iam:PutRolePolicy`
  - [ ] `events:PutRule`
  - [ ] `events:PutTargets`
- [ ] If errors occur during deployment, may need to use root AWS account or request elevated permissions

---

## Deployment Day Timeline (October 15, 2026)

### Morning (9:00 AM - 10:00 AM ET)
**Phase 1A Infrastructure Deployment**

```bash
cd /home/claude/mcelveen-autonomous-trading-system
chmod +x deploy-phase-1a.sh
./deploy-phase-1a.sh mcelveen
```

**Expected Output:**
```
==========================================
Phase 1A: AWS Infrastructure Deployment
==========================================
...
✓ DynamoDB tables ready
✓ IAM role configured
✓ v3.0.33 Lambda deployed
✓ EventBridge rules configured
...
Phase 1A Deployment Complete!
```

**Validation After Phase 1A:**
- [ ] Check AWS Console → DynamoDB: `mcelveen-forex-trades` table exists
- [ ] Check AWS Console → DynamoDB: `mcelveen-forex-metrics` table exists
- [ ] Check AWS Console → Lambda: `mcelveen-hybrid-trading-v3.0.33` function exists
- [ ] Check AWS Console → Events → Rules: Two rules created (15-min and 4 PM)

---

### Afternoon (1:00 PM - 2:00 PM ET)
**Phase 1B Execution Layer Deployment**

```bash
./deploy-phase-1b.sh mcelveen
```

**Expected Output:**
```
==========================================
Phase 1B: Forex Execution Layer Deployment
==========================================
...
✓ v3.0.34 Lambda deployed
✓ Router → Execution chain configured
✓ Validation tests complete
...
Phase 1B Deployment Complete!
```

**Validation After Phase 1B:**
- [ ] Check AWS Console → Lambda: `mcelveen-forex-execution-v3.0.34` function exists
- [ ] Check AWS Console → CloudWatch Logs: Both Lambda log groups visible
- [ ] CloudWatch log groups:
  - [ ] `/aws/lambda/mcelveen-hybrid-trading-v3.0.33`
  - [ ] `/aws/lambda/mcelveen-forex-execution-v3.0.34`

---

### Late Afternoon (3:00 PM - 4:00 PM ET)
**Post-Deployment Configuration**

**Update Schwab Credentials in Lambda Environment Variables:**

```bash
# Update v3.0.33 Router
aws lambda update-function-configuration \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --environment Variables="{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,SCHWAB_REFRESH_TOKEN=<YOUR-FRESH-TOKEN>,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
  --region us-east-2 \
  --profile mcelveen

# Update v3.0.34 Execution
aws lambda update-function-configuration \
  --function-name mcelveen-forex-execution-v3.0.34 \
  --environment Variables="{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
  --region us-east-2 \
  --profile mcelveen
```

**Replace `<YOUR-FRESH-TOKEN>` with your Schwab refresh token from prerequisites.**

---

## Quick Test Scripts (After Credentials Updated)

### Test 1: Router Invocation
```bash
aws lambda invoke \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 \
  --profile mcelveen \
  /tmp/router-test.json && cat /tmp/router-test.json | jq .
```

**Expected:** Status 200, FOREX mode detected (if testing during forex hours)

### Test 2: Execution Chain
```bash
aws lambda invoke \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 \
  --profile mcelveen \
  --payload '{"action":"EXECUTE"}' \
  /tmp/chain-test.json && cat /tmp/chain-test.json | jq .
```

**Expected:** Status 200, execution results returned

### Test 3: CloudWatch Logs
```bash
aws logs tail /aws/lambda/mcelveen-hybrid-trading-v3.0.33 --region us-east-2 --profile mcelveen
aws logs tail /aws/lambda/mcelveen-forex-execution-v3.0.34 --region us-east-2 --profile mcelveen
```

**Expected:** Recent log entries showing router and execution activity

---

## Troubleshooting During Deployment

### "AccessDenied" Errors
**Solution:** Your AWS credentials don't have required permissions. Check:
- [ ] Are you using correct AWS profile? `aws sts get-caller-identity --profile mcelveen`
- [ ] Does IAM user have DynamoDB, Lambda, IAM, Events permissions?
- [ ] Try using AWS root account credentials if elevated permissions available

### "ResourceNotFoundException"
**Solution:** Previously created resource not found. Either:
- [ ] Delete the resource from AWS console and re-run script, OR
- [ ] Update script to use existing resource names

### Quote/Order Execution Fails
**Solution:** Schwab token is likely expired or invalid. Check:
- [ ] Is your refresh token less than 24 hours old?
- [ ] Run v3.0.32 token refresh to get fresh access token
- [ ] Update both Lambda functions with new token

### No Trades Appearing in DynamoDB
**Solution:** Check in this order:
1. [ ] Verify v3.0.34 Lambda is being invoked: Check CloudWatch logs
2. [ ] Verify DynamoDB table permissions in IAM role
3. [ ] Verify Schwab API credentials are fresh (< 30 min old)
4. [ ] Check Lambda timeout (60s might be too short if network is slow)

---

## Success Criteria (Oct 15 Evening)

After deployment completes, verify:
- [ ] Phase 1A script ran without errors
- [ ] Phase 1B script ran without errors
- [ ] Both Lambda functions visible in AWS console
- [ ] DynamoDB tables populated (after first trade)
- [ ] CloudWatch logs showing execution activity
- [ ] At least one trade logged to DynamoDB by Oct 16 morning

---

## Baseline Data Collection (Oct 15 - Nov 5)

After successful deployment:
- **Target:** 50+ trades logged by Nov 5, 2026
- **Monitoring:** Check CloudWatch metrics daily (DailyPnL, WinRate, TradesCompleted)
- **Schedule:** Trading runs every 15 minutes during forex hours (Sun-Fri 5 PM - Fri 4 PM ET)
- **Next Phase:** Phase 1C ML integration starts Nov 5

---

## Contact/Support if Issues Arise

If deployment encounters unexpected issues:
1. Check `DEPLOYMENT_GUIDE.md` troubleshooting section
2. Check CloudWatch logs for error details
3. Verify Schwab API credentials and token freshness
4. Review script output for specific error messages
5. Consult PHASE_1B_DEPLOYMENT_GUIDE.md for detailed technical specs

---

**Deployment Readiness Status:** ⏳ Pending Prerequisites Verification

**Next Action:** Complete all checkboxes above by Oct 14, 2026 EOD. Report back when ready for Oct 15 deployment.

---

*McElveen Autonomous Trading System - Production Ready* 🚀
