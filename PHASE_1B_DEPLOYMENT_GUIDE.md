# McElveen v3.0.34 - Phase 1B Deployment Guide
## Forex Execution Layer & Order Management

**Timeline:** Oct 15 - Nov 5, 2026  
**Status:** Execution layer development  
**Objective:** Schwab API forex trading, order execution, P&L tracking, trade journaling

---

## Architecture Overview

```
v3.0.33 (Hybrid Router)
    ↓
[Trading Mode Decision]
    ├── EQUITY → mcelveen-trading-system (existing v3.0.31)
    └── FOREX → v3.0.34 (NEW - Execution Layer)
                    ↓
            [Schwab API Integration]
                    ├── Get forex quotes
                    ├── Place orders (BUY/SELL)
                    ├── Manage positions
                    └── Calculate P&L
                    ↓
            [Trade Journal + Metrics]
                    ├── DynamoDB logging
                    └── CloudWatch publishing
```

---

## Phase 1B Components

### 1. SchwabForexClient Class
**Purpose:** Low-level Schwab API communication for forex

**Methods:**
- `get_forex_quote(pair)` - Fetch bid/ask/last prices
- `place_forex_order(pair, direction, quantity, entry_price, order_type)` - Market or limit orders
- `get_position(pair)` - Query open positions
- `close_position(pair, exit_price)` - Reverse open position + calculate P&L

**Dependencies:**
- Schwab OAuth access token (from v3.0.32 refresh cycle)
- Network access to `api.schwabapi.com`

### 2. ForexTradeJournal Class
**Purpose:** Trade logging and metrics aggregation

**Methods:**
- `log_trade(trade_data)` - Write to DynamoDB mcelveen-forex-trades
- `calculate_daily_metrics()` - Win-rate, P&L, trade counts
- `publish_metrics_to_cloudwatch(metrics)` - CloudWatch metrics

**DynamoDB Integration:**
- Table: `mcelveen-forex-trades` (from Phase 1A)
- Attributes: Pair, Direction, Quantity, EntryPrice, ExitPrice, PipsGained, PnL, Status
- CloudWatch Namespace: `McElveen/Forex`

### 3. ForexExecutionOrchestrator Class
**Purpose:** High-level execution coordination

**Methods:**
- `execute_recommendation(pair, direction, quantity, conviction)` - Execute trade from macro analysis
- `close_recommendation(pair)` - Close open position

**Workflow:**
1. Receive macro recommendation from v3.0.33 router
2. Get quote for pair
3. Place order via SchwabForexClient
4. Log to DynamoDB
5. Return execution result

---

## Deployment Steps

### Step 1: Deploy v3.0.34 Lambda Function

**Configuration:**
```
Function Name: mcelveen-forex-execution-v3.0.34
Runtime: Python 3.11
Handler: index.lambda_handler
Timeout: 60 seconds
Memory: 512 MB
Region: us-east-2

Environment Variables (same as Phase 1A):
- SCHWAB_ACCOUNT_ID = 7720-9306
- SCHWAB_ACCESS_TOKEN = (fresh token from v3.0.32 refresh)
- FOREX_TRADES_TABLE = mcelveen-forex-trades
- FOREX_METRICS_TABLE = mcelveen-forex-metrics
```

**AWS CLI:**
```bash
# Package the function
zip -j mcelveen-forex-execution-v3.0.34.zip v3.0.34_forex_execution.py

# Create function
aws lambda create-function \
  --function-name mcelveen-forex-execution-v3.0.34 \
  --runtime python3.11 \
  --role arn:aws:iam::650589744593:role/service-role/Lambda-EventBridge-Role \
  --handler v3.0.34_forex_execution.lambda_handler \
  --zip-file fileb://mcelveen-forex-execution-v3.0.34.zip \
  --timeout 60 \
  --memory-size 512 \
  --environment Variables="{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=<fresh-token>,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
  --region us-east-2
```

### Step 2: Update v3.0.33 Router to Call v3.0.34

**Modification to v3.0.33_hybrid_forex_system.py:**

In the `lambda_handler`, when `FOREX_TRADING` mode detected, invoke v3.0.34 instead of returning routing status:

```python
elif trading_mode == TradingMode.FOREX_TRADING:
    print("[ROUTING] → FOREX TRADING (24/5 markets)")
    
    # Macro analysis (same as before)
    macro = analyze_forex_macro(mock_market_data)
    
    # NEW: Invoke v3.0.34 execution layer
    try:
        lambda_client = boto3.client('lambda', region_name='us-east-2')
        execution_event = {
            "mode": "FOREX",
            "macro_analysis": macro,
            "action": "EXECUTE"
        }
        
        response = lambda_client.invoke(
            FunctionName='mcelveen-forex-execution-v3.0.34',
            InvocationType='RequestResponse',
            Payload=json.dumps(execution_event)
        )
        
        execution_result = json.loads(response['Payload'].read())
        print(f"[EXECUTION] {execution_result['body']}")
        
        result = {
            "mode": "FOREX",
            "status": "EXECUTED",
            "macro_analysis": macro,
            "executions": json.loads(execution_result['body']).get('executions', [])
        }
    except Exception as e:
        print(f"[ERROR] Execution invocation failed: {e}")
        result = {
            "mode": "FOREX",
            "status": "ROUTING_ONLY",
            "error": str(e)
        }
```

**IAM Permission Required:**
Add to Lambda-EventBridge-Role:
```json
{
  "Effect": "Allow",
  "Action": ["lambda:InvokeFunction"],
  "Resource": "arn:aws:lambda:us-east-2:650589744593:function:mcelveen-forex-execution-v3.0.34"
}
```

### Step 3: Update EventBridge Rule Targets

**Modify mcelveen-forex-trading-15min rule:**
- Primary target: mcelveen-hybrid-trading-v3.0.33 (router)
- Secondary target: Optional dead-letter queue for failed invocations

```bash
# Update rule targets
aws events put-targets \
  --rule mcelveen-forex-trading-15min \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-2:650589744593:function:mcelveen-hybrid-trading-v3.0.33" \
            "Id"="2","Arn"="arn:sqs:us-east-2:650589744593:mcelveen-deadletter" \
  --region us-east-2
```

### Step 4: Testing Phase 1B

#### Test 4A: Direct Lambda Invocation

```bash
# Test v3.0.34 directly
aws lambda invoke \
  --function-name mcelveen-forex-execution-v3.0.34 \
  --region us-east-2 \
  --payload '{"mode":"FOREX","macro_analysis":{"regime":"NEUTRAL","conviction":0.5,"recommended_pairs":["EUR/USD","USD/CAD"]},"action":"EXECUTE"}' \
  /tmp/execution-response.json

cat /tmp/execution-response.json | jq .
```

Expected output:
```json
{
  "statusCode": 200,
  "body": {
    "mode": "FOREX",
    "executions": [
      {
        "success": true,
        "pair": "EURUSD",
        "direction": "BUY",
        "entry_price": 1.0950,
        "quantity": 0.05,
        "status": "OPEN"
      }
    ],
    "metrics": {
      "daily_pnl": 0.0,
      "win_rate": 0.0,
      "trades_completed": 0,
      "trades_open": 1,
      "avg_pips": 0.0
    }
  }
}
```

#### Test 4B: Router → Execution Chain

```bash
# Test v3.0.33 calling v3.0.34
aws lambda invoke \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 \
  /tmp/router-response.json

cat /tmp/router-response.json | jq .body
```

Expected flow:
```
[MODE] FOREX
[ROUTING] → FOREX TRADING (24/5 markets)
[MACRO ANALYSIS] Regime: NEUTRAL, Conviction: 0.50
[EXECUTION] v3.0.34 invoked...
```

#### Test 4C: CloudWatch Logs & Metrics

```bash
# Monitor v3.0.34 logs
aws logs tail /aws/lambda/mcelveen-forex-execution-v3.0.34 --follow

# Query CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace McElveen/Forex \
  --metric-name DailyPnL \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region us-east-2
```

#### Test 4D: DynamoDB Trade Journal

```bash
# Scan trade log for today
aws dynamodb query \
  --table-name mcelveen-forex-trades \
  --key-condition-expression "Date = :date" \
  --expression-attribute-values "{\":date\":{\"S\":\"2026-10-15\"}}" \
  --region us-east-2

# Expected output: Array of logged trades with Pair, Direction, EntryPrice, Status
```

### Step 5: Guardrail Validation (G1-G4)

**Before execution, v3.0.34 should validate guardrails from v3.0.33:**

Add to `ForexExecutionOrchestrator.execute_recommendation()`:

```python
# Validate guardrails before order placement
guardrail_result = validate_forex_guardrails(
    position_size=quantity * 100000,  # Lots to units
    total_forex_nav=metrics.forex_nav,
    pair_exposure=quantity * 100000 * entry_price,
    portfolio_metrics=metrics
)

if not guardrail_result["guardrails_pass"]:
    print(f"[GUARDRAIL] ❌ Trade blocked: {guardrail_result['guardrails']}")
    return {"success": False, "error": "Guardrail violation"}
```

---

## Integration with Phase 1A

| Component | Phase 1A | Phase 1B |
|-----------|----------|----------|
| **Routing** | v3.0.33 ✅ | Uses v3.0.33 output |
| **Schwab Auth** | v3.0.32 token refresh | Consumes access token |
| **DynamoDB Tables** | Created ✅ | mcelveen-forex-trades logged to |
| **EventBridge Rules** | Created ✅ | mcelveen-forex-trading-15min triggers v3.0.33→v3.0.34 |
| **IAM Role** | Lambda-EventBridge-Role ✅ | Expanded with lambda:InvokeFunction |
| **CloudWatch Logs** | /aws/lambda/mcelveen-hybrid-trading-v3.0.33 | /aws/lambda/mcelveen-forex-execution-v3.0.34 (new) |
| **CloudWatch Metrics** | McElveen/Forex namespace ✅ | DailyPnL, WinRate, TradesCompleted (Phase 1B publishes) |

---

## Monitoring & Alerts

### CloudWatch Dashboard (Optional Phase 1B Enhancement)

Create dashboard with:
- Daily P&L (CloudWatch metric)
- Win-rate % (CloudWatch metric)
- Open positions count (CloudWatch metric)
- Trade execution latency (Lambda duration)
- Failed orders % (custom metric from errors)

### SNS Alerts

Subscribe to McElveenAlerts topic for:
- Order execution failures
- Guardrail violations
- DynamoDB errors
- Access token expiration warnings

---

## Phase 1B Success Criteria

- ✅ v3.0.34 function deployed and operational
- ✅ SchwabForexClient successfully fetches quotes
- ✅ Orders placed and logged to DynamoDB
- ✅ Trades appear in mcelveen-forex-trades table
- ✅ CloudWatch metrics updated with each execution
- ✅ Daily P&L calculated and published
- ✅ Router → Execution chain working end-to-end
- ✅ Guardrail validation preventing over-sized trades
- ✅ 7+ days of baseline data collection by Nov 5

---

## Phase 1C (Future): Machine Learning Integration

Once Phase 1B baseline is running (Nov 5+):
1. Feed DynamoDB trade data to ML training pipeline
2. Implement regime detection model (RISK_ON/NEUTRAL/RISK_OFF)
3. Dynamic conviction scoring based on model confidence
4. A/B test: macro analysis vs ML recommendations
5. Gradual transition to ML-driven execution

---

## Troubleshooting Phase 1B

### Issue: "No access token available"
**Solution:** Verify v3.0.32 token refresh ran successfully; check DynamoDB for stored refresh token

### Issue: "Quote unavailable" or HTTP 403 from Schwab API
**Solution:** Verify OAuth token is fresh (< 30 min old); run v3.0.32 token refresh manually

### Issue: Orders placed but P&L calculation shows $0
**Solution:** Verify contract multiplier in pip-to-PnL calculation (standard = $10/pip for major pairs)

### Issue: "RequestTimeout" on position queries
**Solution:** Increase Lambda timeout from 60s to 90s if positions are numerous

### Issue: DynamoDB write errors ("ValidationException")
**Solution:** Verify table schema matches (Date=PK/String, Timestamp=SK/String)

---

## Deployment Checklist

- [ ] v3.0.34 function code finalized
- [ ] Dependencies verified (boto3, requests, zoneinfo)
- [ ] v3.0.34 Lambda function created (mcelveen-forex-execution-v3.0.34)
- [ ] Environment variables configured (SCHWAB_ACCOUNT_ID, SCHWAB_ACCESS_TOKEN, table names)
- [ ] IAM role updated with lambda:InvokeFunction permission
- [ ] v3.0.33 router modified to invoke v3.0.34 on FOREX_TRADING mode
- [ ] Manual test passed (direct Lambda invocation)
- [ ] Router → Execution chain test passed
- [ ] CloudWatch logs show successful executions
- [ ] DynamoDB trades table populated with test data
- [ ] CloudWatch metrics showing DailyPnL, WinRate
- [ ] SLA: Execution latency < 10 seconds per trade

---

**v3.0.34 Phase 1B: Forex Execution Layer Ready for Deployment** 🚀
