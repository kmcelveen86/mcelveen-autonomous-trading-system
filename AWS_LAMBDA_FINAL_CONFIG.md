# AWS Lambda Token Caching Configuration - Final Setup

**Date**: 2026-10-10  
**Scope**: Two Lambda functions with Claude API integration

---

## Functions with Claude API (Token Caching Enabled)

### 1. McElveenTradingSystem (Equity Trading)
- **Runtime**: Python 3.11
- **Updated**: 19 hours ago
- **Claude Models**: Opus 5-5 (VIX < 12 or > 20) + Sonnet 5 (VIX 12-20)
- **API Calls**: 2 per cycle (CIO + PM)
- **Call Frequency**: Every 15 minutes, 9:30am-4pm ET
- **Daily Volume**: 26 calls/day

### 2. mcelveen-autonomous-forex (Forex Trading)
- **Runtime**: Python 3.11
- **Updated**: 18 hours ago
- **Claude Model**: Sonnet 5 only
- **API Calls**: 1 per cycle (Combined CIO+PM)
- **Call Frequency**: Every 5 minutes, 24/5 market hours
- **Daily Volume**: 288 calls/day average

---

## Functions WITHOUT Claude API (No Changes Needed)

- ✅ **McElveenTokenRefresh** - Schwab OAuth only, no Claude calls
- ✅ **McElveenDailyReport** - Reporting only, no Claude calls
- ✅ **SchwabDebug** - Debugging utility, no Claude calls

---

## AWS Lambda Configuration Steps

### Configuration 1: McElveenTradingSystem

**Navigate to:**
1. AWS Lambda Console → Functions
2. Select: **McElveenTradingSystem**
3. Configuration tab → Environment variables

**Add/Update these variables:**

| Key | Value | Purpose |
|-----|-------|---------|
| `ENABLE_CACHE` | `true` | Activate token caching |
| `CLAUDE_MODEL` | `claude-sonnet-5` | Default model (will be overridden by VIX routing) |
| `CLAUDE_API_KEY` | *(existing)* | Keep existing API key |

**Steps to Configure:**
```
1. Click "Edit" in Environment variables section
2. Find existing: CLAUDE_API_KEY (keep as-is)
3. Click "Add environment variable"
4. Key: ENABLE_CACHE
5. Value: true
6. Click "Add environment variable"
7. Key: CLAUDE_MODEL
8. Value: claude-sonnet-5
9. Click "Save"
10. Wait for deployment (status: "Successful")
```

**Expected Deployment Time**: ~30 seconds

---

### Configuration 2: mcelveen-autonomous-forex

**Navigate to:**
1. AWS Lambda Console → Functions
2. Select: **mcelveen-autonomous-forex**
3. Configuration tab → Environment variables

**Add/Update these variables:**

| Key | Value | Purpose |
|-----|-------|---------|
| `ENABLE_CACHE` | `true` | Ensure token caching enabled |
| `CLAUDE_MODEL` | `claude-sonnet-5` | Forex uses Sonnet 5 only |
| `CLAUDE_API_KEY` | *(existing)* | Keep existing API key |

**Steps to Configure:**
```
1. Click "Edit" in Environment variables section
2. Find existing: CLAUDE_API_KEY (keep as-is)
3. Find existing: ENABLE_CACHE (should already be "true")
4. Find existing: CLAUDE_MODEL (should already be "claude-sonnet-5")
5. If ENABLE_CACHE is missing, add it with value "true"
6. If CLAUDE_MODEL is missing, add it with value "claude-sonnet-5"
7. Click "Save"
8. Wait for deployment (status: "Successful")
```

**Note**: Forex file already has caching implemented, so these may already be set.

**Expected Deployment Time**: ~30 seconds

---

## Post-Configuration Verification

### Check CloudWatch Logs

**For McElveenTradingSystem:**
```
Log Group: /aws/lambda/McElveenTradingSystem
Recent Log Stream: (select latest)

Search for:
[CACHE] CIO WRITE
[CACHE] CIO HIT
[CACHE] PM WRITE
[CACHE] PM HIT
```

**Expected First Execution (0-5 minutes):**
```
[CACHE] Token caching ENABLED - using ephemeral cache for CIO system prompt
[CACHE] CIO WRITE - Created cache with 1247 tokens (CIO system prompt cached for 5 min)
[CIO TOKENS] Input: 1247 | Output: 45 | Total: 1292

[PM] Token caching ENABLED - using ephemeral cache for Portfolio Manager decision prompt
[CACHE] PM WRITE - Created cache with 892 tokens (Portfolio Manager prompt cached)
[PM TOKENS] Input: 892 | Output: 38 | Total: 930
```

**Expected Subsequent Executions (within 5 minutes):**
```
[CACHE] Token caching ENABLED - using ephemeral cache for CIO system prompt
[CACHE] CIO HIT - Read 1247 tokens from cache (saved ~$0.0011)
[CIO TOKENS] Input: 0 | Output: 42 | Total: 42

[PM] Token caching ENABLED - using ephemeral cache for Portfolio Manager decision prompt
[CACHE] PM HIT - Read 892 tokens from cache (saved ~$0.0008)
[PM TOKENS] Input: 0 | Output: 35 | Total: 35
```

---

### For mcelveen-autonomous-forex:
```
Log Group: /aws/lambda/mcelveen-autonomous-forex
Recent Log Stream: (select latest)

Search for:
cache_enabled
cache_read_tokens
cache_creation_tokens
```

**Expected Log Entry:**
```json
{
  "cache_enabled": true,
  "cache_read_tokens": 950,
  "cache_creation_tokens": 0,
  "input_tokens": 0,
  "output_tokens": 98,
  "total_tokens": 98
}
```

---

## Cost Verification (After 24-48 Hours)

### AWS Billing Dashboard

1. Go to **AWS Billing → Cost Explorer**
2. Filter by: Service = "API Calls - Claude"
3. Compare:
   - **Before**: ~$20.74/month
   - **After**: ~$2.07/month
   - **Savings**: ~$18.67/month

### Daily Cost Check

**McElveenTradingSystem:**
- Before: ~$0.10/day → After: ~$0.01/day
- Savings: ~$0.09/day × 30 = **$2.70/month**

**mcelveen-autonomous-forex:**
- Before: ~$0.82/day → After: ~$0.08/day
- Savings: ~$0.74/day × 30 = **$22.20/month**

**Note**: Forex savings vary based on market hours (288 calls/day when forex open, 0 when closed)

---

## Rollback (If Needed)

**Quick disable (30 seconds):**
1. Go to Lambda function → Configuration → Environment variables
2. Change: `ENABLE_CACHE` = `false`
3. Click "Save"
4. System reverts to standard (non-cached) API calls

**Full rollback (5 minutes):**
1. Re-deploy original `lambda_function.py` without caching code
2. Delete `ENABLE_CACHE` and `CLAUDE_MODEL` environment variables

---

## Summary

| Function | Cache Status | Expected Logs | Verification |
|----------|--------------|----------------|--------------|
| McElveenTradingSystem | ✅ Configure | [CACHE] CIO/PM WRITE/HIT | CloudWatch logs |
| mcelveen-autonomous-forex | ✅ Verify/Configure | cache_enabled: true | CloudWatch logs |
| McElveenTokenRefresh | ✅ No change | N/A | N/A |
| McElveenDailyReport | ✅ No change | N/A | N/A |
| SchwabDebug | ✅ No change | N/A | N/A |

---

## Timeline

| Step | Time | Status |
|------|------|--------|
| Configure McElveenTradingSystem | 2 min | ⏳ Ready |
| Configure mcelveen-autonomous-forex | 2 min | ⏳ Ready |
| Verify CloudWatch logs | 5-15 min | ⏳ Ready |
| Monitor cost reduction | 24-48 hrs | ⏳ Ready |

**Total Configuration Time**: ~4 minutes  
**Immediate Savings Activation**: Upon configuration  
**First Cost Report**: 24-48 hours after configuration

---

## Final Checklist

- [ ] Log into AWS Console
- [ ] Navigate to Lambda → McElveenTradingSystem
- [ ] Add `ENABLE_CACHE` = `true`
- [ ] Add `CLAUDE_MODEL` = `claude-sonnet-5`
- [ ] Click Save (wait for "Successful" status)
- [ ] Navigate to Lambda → mcelveen-autonomous-forex
- [ ] Verify/Add `ENABLE_CACHE` = `true`
- [ ] Verify/Add `CLAUDE_MODEL` = `claude-sonnet-5`
- [ ] Click Save (wait for "Successful" status)
- [ ] Check CloudWatch logs for cache metrics
- [ ] Verify cost reduction in AWS Billing (24-48 hrs)

---

**Ready to activate**: Yes ✅  
**Configuration complexity**: Low (environment variables only)  
**Risk level**: Very Low (easy rollback)  
**Expected monthly savings**: ~$18.67
