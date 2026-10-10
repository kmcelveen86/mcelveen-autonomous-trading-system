# Cache Optimization Deployment Checklist

## Pre-Deployment Verification

### Code Changes ✅
- [x] System prompt enhanced with trading framework (lines 119-163)
- [x] Cache control added to system prompt and user messages
- [x] Cache metrics tracking implemented
- [x] CloudWatch logging for cache hits/misses
- [x] Commit: `feat: add prompt caching optimization to Claude Sonnet 5 forex analysis`

### Environment Variables ✅
Verify these are set in Lambda:
```
ENABLE_CACHE=true
CLAUDE_API_KEY=sk-ant-... (valid, API key with access)
CLAUDE_MODEL=claude-sonnet-5
```

### Lambda Layer ✅
Confirm `mcelveen-forex-dependencies` layer has:
```
anthropic >= 0.28.0  (supports cache_control parameter)
requests==2.32.0
pytz==2024.1
python-dateutil==2.8.2
python-dotenv==1.0.1
```

## Deployment Options

### Option A: Update Code Only (Recommended if Layer is current)
1. Go to **Lambda** → **mcelveen-autonomous-forex** → **Code** tab
2. **Copy the updated code** from `/mcelveen_autonomous_forex_v3.0.36.py`
3. **Paste into Lambda editor**
4. Click **Save**
5. Go to **Test** tab
6. Create test event: `{}`
7. **Invoke** and verify cache metrics in output

### Option B: Re-package ZIP (Full deployment)
1. Run updated PowerShell script:
```powershell
cd C:\WINDOWS\System32\mcelveen-autonomous-trading-system
powershell -ExecutionPolicy Bypass -File .\CREATE_LAMBDA_PACKAGE.ps1
```

2. Upload new ZIP to Lambda:
   - **Code** tab → **Upload from** → **ZIP file**
   - Select the newly created `mcelveen-v3.0.36-deployment.zip`
   - Click **Save**

### Option C: Update Layer Only (If code already deployed)
1. Delete old `mcelveen-forex-dependencies` Layer
2. Create new Layer with updated `anthropic==0.28.0`
3. Re-attach to function
4. Test

## Post-Deployment Testing

### Test 1: Verify Cache is Working
1. Go to **Test** tab
2. **Create new test** with: `{}`
3. **Invoke first time** → Look for: `Cache WRITE` message
4. **Invoke second time** (within 5 minutes) → Look for: `Cache HIT` message
5. **Expected output**:
```
✓ Cache HIT - 89.2% tokens from cache (1,170 cached tokens reused)
```

### Test 2: Check Cache Metrics
Look for in CloudWatch logs:
```json
"cache_stats": {
  "cache_enabled": true,
  "cache_read_tokens": 1170,
  "cache_creation_tokens": 0,
  "input_tokens": 145,
  "output_tokens": 425
}
```

### Test 3: Verify Response Structure
Expected JSON response includes:
```json
{
  "statusCode": 200,
  "timestamp": "2026-10-10T...",
  "trading_mode": "FOREX_TRADING",
  "et_time": "HH:MM",
  "macro_analysis": {
    "regime": "USD_STRENGTH|EUR_STRENGTH|NEUTRAL",
    "conviction": 0.75,
    "recommended_pairs": ["EUR/USD", "GBP/USD"],
    "pair_analysis": {...},
    "cache_stats": {...}
  },
  "body": {
    "status": "SUCCESS"
  }
}
```

## Cost Verification

### Before Caching
```
Rough estimate: $45.30/month (504,000 tokens/day)
```

### After Caching
```
New estimate: $4.80/month (52,160 tokens/day)
Savings: ~$40.50/month ✅
```

To verify live:
1. Check **Lambda** → **Monitor** → **CloudWatch Logs**
2. Look for cache messages over 24 hours
3. Calculate hit rate: `Cache HIT events / Total invocations`
4. Compare estimated cost

## Rollback Plan (if issues)

If problems occur after deployment:

### Step 1: Revert Code
```powershell
git revert HEAD
git push origin main
```

### Step 2: Redeploy Previous Version
- Use the old `mcelveen-v3.0.36-deployment.zip` backup
- Upload to Lambda
- Test

### Step 3: Check Logs
- Go to **CloudWatch** → **Log Groups** → `/aws/lambda/mcelveen-autonomous-forex`
- Look for error messages
- Share logs in support ticket

## Monitoring Going Forward

### Weekly Check
```
CloudWatch Logs → Filter: "Cache"
- Count "Cache HIT" messages
- Count "Cache WRITE" messages  
- Calculate hit rate: HIT / (HIT + WRITE)
- Expected: 85-95% hit rate
```

### Monthly Cost Review
```
AWS Billing → Lambda → Filter by function
- Compare to baseline ($45.30/month)
- Should see 80-90% reduction
```

### Alert Setup (Optional)
```
CloudWatch → Alarms → Create new alarm
- Metric: "Cache HIT not detected for 1 hour"
- Action: Send SNS notification
- Helps catch cache issues early
```

## Support

### If Cache Hits Are 0%
1. Verify `ENABLE_CACHE=true` in env vars
2. Verify anthropic >= 0.28.0 in Layer
3. Check that Claude Sonnet 5 is selected
4. Look at error logs in CloudWatch

### If Invocations Fail
1. Check error details in Lambda Test output
2. Look at CloudWatch Logs for stack trace
3. Verify API key is valid (not expired)

### Questions?
- Review `TOKEN_CACHE_IMPLEMENTATION.md` for details
- Check Anthropic docs: https://docs.anthropic.com/claude/reference/prompt-caching

---

**Status**: Ready for Deployment  
**Commit**: `feat: add prompt caching optimization to Claude Sonnet 5 forex analysis`  
**Expected Benefit**: ~$40.50/month cost reduction
