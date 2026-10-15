# McElveen Trading System - Schedule & Execution Plan

## Market Hours Schedule

### Trading System Execution
**Frequency:** Every 5 minutes  
**Trading Days:** Monday - Friday (excluding US federal holidays)  
**Trading Hours:** 9:30 AM - 4:00 PM EST/EDT

### Daily Executions
- **9:30 AM** - Market open + first execution
- **9:35 AM, 9:40 AM, 9:45 AM...** - Every 5 minutes
- **4:00 PM** - Market close + final execution
- **Total executions per day:** 78 tasks (50 minutes / 5 min intervals + 1)

### Daily Report
**Frequency:** Once daily  
**Execution Time:** 4:05 PM EST/EDT (5 minutes after market close)  
**Trading Days:** Monday - Friday only

### Token Refresh Service
**Frequency:** Continuous  
**Execution:** Every 30 minutes (24/7)  
**Purpose:** Maintains fresh Schwab OAuth tokens

---

## EventBridge Schedule Rules

### Trading System Rules (Every 5 Minutes)

```
Rule: mcelveen-trading-system-0930
  Time: Every 5 mins from 9:30 AM - 9:55 AM
  Cron: cron(30,35,40,45,50,55 9 ? * MON-FRI *)

Rule: mcelveen-trading-system-10
  Time: Every 5 mins from 10:00 AM - 10:55 AM
  Cron: cron(0,5,10,15,20,25,30,35,40,45,50,55 10 ? * MON-FRI *)

Rule: mcelveen-trading-system-11
  Time: Every 5 mins from 11:00 AM - 11:55 AM
  Cron: cron(0,5,10,15,20,25,30,35,40,45,50,55 11 ? * MON-FRI *)

Rule: mcelveen-trading-system-12
  Time: Every 5 mins from 12:00 PM - 12:55 PM
  Cron: cron(0,5,10,15,20,25,30,35,40,45,50,55 12 ? * MON-FRI *)

Rule: mcelveen-trading-system-13
  Time: Every 5 mins from 1:00 PM - 1:55 PM
  Cron: cron(0,5,10,15,20,25,30,35,40,45,50,55 13 ? * MON-FRI *)

Rule: mcelveen-trading-system-14
  Time: Every 5 mins from 2:00 PM - 2:55 PM
  Cron: cron(0,5,10,15,20,25,30,35,40,45,50,55 14 ? * MON-FRI *)

Rule: mcelveen-trading-system-15
  Time: Every 5 mins from 3:00 PM - 3:55 PM
  Cron: cron(0,5,10,15,20,25,30,35,40,45,50,55 15 ? * MON-FRI *)

Rule: mcelveen-trading-system-16
  Time: 4:00 PM (market close)
  Cron: cron(0 16 ? * MON-FRI *)
```

### Daily Report Rule

```
Rule: mcelveen-daily-report
  Time: 4:05 PM (5 mins after close)
  Cron: cron(5 16 ? * MON-FRI *)
```

---

## HYBRID Strategy Execution Flow

### Every 5-Minute Cycle:

```
1. Check Market Status
   └─ Is market open? (9:30 AM - 4:00 PM)
   └─ Is it a trading day? (Mon-Fri, no holidays)
   └─ Token valid? (Synced from DynamoDB)

2. Fetch Current Portfolio
   └─ Read positions from DynamoDB snapshot
   └─ Get current prices (Schwab API)
   └─ Calculate current P&L

3. Apply SELL_AND_BUY Rotation
   └─ Identify worst performing positions
   └─ Sell selected positions
   └─ Buy predetermined stocks
   └─ Log trades to DynamoDB

4. Check G9/G10 Guardrails
   ├─ Gap Check: Auto-sell if >5% down
   ├─ Consolidation: If 3+ positions down >2%
   └─ Rebalance portfolio

5. Update Positions Snapshot
   └─ Store latest holdings to DynamoDB
   └─ Record execution time

6. Log & Monitor
   └─ CloudWatch metrics
   └─ Error handling & alerts
```

---

## Cost Implications

### Fargate Cost Calculation

**Trading System - 78 executions/day**
- CPU: 512 (0.5 vCPU) per execution
- Memory: 1GB per execution
- Duration: ~1 minute per execution
- Daily cost: 78 × (0.5 × $0.04665 + 1 × $0.00511) / 60 = **$0.60/day**
- Monthly: ~**$12/month** (252 trading days/year ÷ 12)

**Daily Report - 1 execution/day**
- CPU: 256 (0.25 vCPU)
- Memory: 512MB
- Duration: ~2 minutes
- Daily cost: (0.25 × $0.04665 + 0.5 × $0.00511) × 2 / 60 = **$0.001/day**
- Monthly: ~**$0.03/month**

**Token Refresh - Continuous**
- CPU: 256 (0.25 vCPU)
- Memory: 512MB
- Duration: 24/7
- Monthly: 0.25 × $0.04665 × 730 + 0.5 × $0.00511 × 730 = **$12.07/month**

**Total Monthly Cost: ~$24.10/month** ✓

---

## Federal Holidays (No Trading)

These dates are excluded from trading:

```
2025:
- January 1 (New Year's Day)
- January 20 (MLK Jr. Day)
- February 17 (Presidents' Day)
- March 17 (Good Friday)
- May 26 (Memorial Day)
- June 19 (Juneteenth)
- July 4 (Independence Day)
- September 1 (Labor Day)
- November 27 (Thanksgiving)
- December 25 (Christmas)

2026:
- January 1 (New Year's Day)
- January 19 (MLK Jr. Day)
- February 16 (Presidents' Day)
- April 3 (Good Friday)
- May 25 (Memorial Day)
- June 19 (Juneteenth)
- July 4 (Independence Day)
- September 7 (Labor Day)
- November 26 (Thanksgiving)
- December 25 (Christmas)
```

### Note on Market Holidays
EventBridge doesn't natively support holiday exclusions. Options:

**Option 1 (Current):** EventBridge rules include all Mon-Fri dates  
→ Add logic in Lambda/Fargate to check holiday calendar  
→ Skip execution if holiday

**Option 2 (Future):** Create Lambda Layer with holiday calendar  
→ Return early if holiday detected

**Option 3 (Enterprise):** Use AWS Scheduler instead of EventBridge  
→ Native holiday support in cron expressions

---

## Monitoring & Alerts

### Key Metrics to Track

```
Per Execution:
- Task startup time (should be <30 seconds)
- Token validity at execution
- Trade count (SELL_AND_BUY cycles)
- G9/G10 guardrail triggers
- Execution duration

Daily:
- Total trades executed
- P&L summary
- Position count
- Account health
```

### CloudWatch Alarms

```bash
# Alert if trading system fails
aws cloudwatch put-metric-alarm \
  --alarm-name mcelveen-trading-system-failures \
  --alarm-description "Trading system task failures" \
  --metric-name TasksFailed \
  --namespace ECS/ContainerInsights \
  --statistic Sum \
  --period 60 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold

# Alert if token refresh stops
aws cloudwatch put-metric-alarm \
  --alarm-name mcelveen-token-refresh-heartbeat \
  --alarm-description "Token refresh service not responding" \
  --metric-name ServiceTaskCount \
  --namespace ECS/ContainerInsights \
  --statistic Minimum \
  --period 300 \
  --threshold 1 \
  --comparison-operator LessThanThreshold
```

---

## Performance Benchmarks

### Expected Execution Times

| Task | Startup | Execution | Total | Target |
|------|---------|-----------|-------|--------|
| Trading System | 15-30s | 20-40s | <90s | <2m |
| Daily Report | 10-20s | 30-60s | <90s | <2m |
| Token Refresh | <5s | 5-15s | <20s | Continuous |

### Concurrent Execution Limits

- **Trading System:** Up to 78 concurrent (one per 5-min window)
- **Token Refresh:** 1 task (continuous service)
- **Daily Report:** 1 task daily

---

## Deployment Commands for Market Hours

### Enable Trading (Before Market Open)
```bash
aws events put-rule --name mcelveen-trading-system-0930 --state ENABLED
aws events put-rule --name mcelveen-trading-system-10 --state ENABLED
# ... all rules
```

### Disable Trading (After Market Close)
```bash
aws events put-rule --name mcelveen-trading-system-0930 --state DISABLED
aws events put-rule --name mcelveen-trading-system-10 --state DISABLED
# ... all rules
```

### Quick Enable/Disable Script
```bash
#!/bin/bash
STATE=${1:-ENABLED}  # Default to ENABLED
for hour in 9 10 11 12 13 14 15 16; do
  aws events put-rule \
    --name mcelveen-trading-system-$hour \
    --state $STATE
done
```

---

**Last Updated:** 2026-10-14  
**Version:** 2.0 (Updated for 5-minute execution)
