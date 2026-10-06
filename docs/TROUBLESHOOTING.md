# Troubleshooting Guide — McElveen Autonomous Trading System

## Common Issues & Solutions

---

## Issue 1: Lambda Function Timeout (60-second deadline exceeded)

### Symptoms
```
errorMessage: "Task timed out after 60.00 seconds"
errorType: "TimeoutError"
```

### Root Causes
1. Claude API call taking > 5 seconds (network latency)
2. Schwab API connection slow (OAuth token refresh blocking)
3. DynamoDB write hitting partition limit (throttling)
4. CIO analysis fetching live market data (multiple API calls serialized)

### Diagnosis
```bash
# Check CloudWatch Logs for timing breakdown
aws logs tail /aws/lambda/mcelveen-trading-system --follow --region us-east-2

# Look for patterns like:
# [14:32:15] CIOCore: Analyzing market conditions
# [14:32:20] ClaudeEngine: Calling Claude API (5s latency)
# [14:32:28] SchwabTrader: Executing orders (3s latency)
# Total: 8 seconds (OK, within 60s timeout)
```

### Solutions

**Option A: Increase Timeout**
```bash
aws lambda update-function-configuration \
  --function-name mcelveen-trading-system \
  --timeout 120 \
  --region us-east-2
```

**Option B: Cache Market Data**
```python
# In cio_analysis.py
CACHE_TTL = 300  # 5 minutes

class CIOCore:
    def __init__(self):
        self.cache = {}
        self.cache_ts = {}
    
    def analyze_market_conditions(self):
        if time.time() - self.cache_ts.get('vix', 0) < CACHE_TTL:
            return self.cache['analysis']  # Return cached result
        
        # Fetch fresh data only if cache expired
        vix = self._fetch_vix()
        self.cache['analysis'] = {...}
        self.cache_ts['vix'] = time.time()
        return self.cache['analysis']
```

**Option C: Parallelize API Calls**
```python
import concurrent.futures

# Fetch VIX and interest rates in parallel
with concurrent.futures.ThreadPoolExecutor() as executor:
    vix_future = executor.submit(self._fetch_vix)
    rates_future = executor.submit(self._fetch_interest_rates)
    
    vix = vix_future.result(timeout=10)
    rates = rates_future.result(timeout=10)
```

**Option D: Async Processing**
Instead of blocking on all API calls, use SNS/SQS:
1. Lambda analyzes market, queues asset selection task
2. Second Lambda picks up queue, calls Claude
3. Third Lambda executes trades
- Total latency: 20s across 3 functions instead of blocking one function for 20s

---

## Issue 2: Guardrails Reject All Orders (FULL_FAIL)

### Symptoms
```json
{
    "validation_status": "FULL_FAIL",
    "rejected_orders": [
        {
            "symbol": "SPY",
            "reason": "Level 1 FAILED: Liquidity check"
        },
        {
            "symbol": "VEA",
            "reason": "Level 1 FAILED: Liquidity check"
        }
    ],
    "execution_status": "no_trades_executed"
}
```

### Root Causes
1. Guardrail thresholds too strict (concentration_limit: 0.05% instead of 15%)
2. Orders requesting unrealistic quantities (100k shares of illiquid stock)
3. Claude returning invalid JSON format
4. DynamoDB missing historical position data

### Diagnosis
```bash
# Check which guardrail level is failing
aws logs grep "FAILED" /aws/lambda/mcelveen-trading-system

# Look at specific order that failed
aws dynamodb get-item \
  --table-name mcelveen-trading-ledger \
  --key '{"execution_id": {"S": "exec_20261006_143215_a7f2"}}' \
  --region us-east-2 | jq .Item.rejected_orders
```

### Solutions

**Option A: Relax Guardrail Thresholds**
```python
# In config/settings.py
# Before (too strict):
CONCENTRATION_LIMIT = float(os.getenv('CONCENTRATION_LIMIT', 0.05))

# After (reasonable):
CONCENTRATION_LIMIT = float(os.getenv('CONCENTRATION_LIMIT', 0.15))

# Then update Lambda environment:
aws lambda update-function-configuration \
  --function-name mcelveen-trading-system \
  --environment Variables='{"CONCENTRATION_LIMIT":"0.15"}' \
  --region us-east-2
```

**Option B: Debug Liquidity Check**
```python
# In portfolio_mgr.py
def _check_liquidity(self, order):
    symbol = order.get('symbol')
    qty = order.get('quantity')
    
    # Placeholder: Check against actual trading volume
    avg_volume = self._get_avg_daily_volume(symbol)
    
    if qty > avg_volume * 0.20:  # More than 20% of daily volume
        logger.warning(f"Liquidity check FAILED: {qty} shares of {symbol}, avg volume {avg_volume}")
        return False
    
    return True

def _get_avg_daily_volume(self, symbol):
    # TODO: Fetch from Yahoo Finance, IEX Cloud, or Schwab API
    # For now, use reasonable defaults
    defaults = {
        'SPY': 100_000_000,   # 100M shares/day
        'VEA': 50_000_000,    # 50M shares/day
        'BND': 30_000_000,    # 30M shares/day
    }
    return defaults.get(symbol, 10_000_000)
```

**Option C: Fix Claude Response Format**
If Claude returns invalid JSON:
```python
# In claude_engine.py
def select_assets(self, directives, macro_analysis):
    try:
        response = client.messages.create(...)
        recommendations = json.loads(response.content[0].text)
    except json.JSONDecodeError as e:
        logger.error(f"Claude response not valid JSON: {e}")
        logger.error(f"Raw response: {response.content[0].text}")
        
        # Return empty recommendations (guardrails reject batch)
        return {
            'assets': [],
            'confidence_alignment': 0.0,
            'error': 'Failed to parse Claude response'
        }
```

---

## Issue 3: OAuth Token Refresh Failing (Schwab Authentication)

### Symptoms
```
errorMessage: "OAuth token refresh failed: 401 Unauthorized"
errorType: "AuthenticationError"
```

### Root Causes
1. Schwab OAuth credentials expired or revoked
2. Client secret changed on Schwab side
3. Redirect URI mismatch
4. Network connectivity issue (proxy blocking)

### Diagnosis
```bash
# Verify credentials in Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id mcelveen/schwab/oauth \
  --region us-east-2

# Check Lambda logs for auth error
aws logs tail /aws/lambda/mcelveen-trading-system --follow --grep "OAuth" --region us-east-2
```

### Solutions

**Option A: Refresh Schwab Credentials**
1. Log into Charles Schwab Developer Portal
2. Regenerate OAuth credentials
3. Update Secrets Manager:
```bash
aws secretsmanager update-secret \
  --secret-id mcelveen/schwab/oauth \
  --secret-string '{
    "client_id": "new-client-id",
    "client_secret": "new-client-secret"
  }' \
  --region us-east-2
```

**Option B: Implement Token Retry Logic**
```python
# In schwab_trader.py
def _refresh_oauth_token(self):
    max_retries = 3
    backoff = 1  # Start with 1 second
    
    for attempt in range(max_retries):
        try:
            token = self._fetch_token_from_schwab()
            logger.info("OAuth token refreshed successfully")
            return token
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"OAuth refresh attempt {attempt+1} failed, retrying in {backoff}s")
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
            else:
                logger.error(f"OAuth token refresh failed after {max_retries} attempts: {e}")
                raise
```

**Option C: Check Network Connectivity**
```bash
# From Lambda environment or local machine
curl -v https://api.schwab.com/oauth/token

# If proxy is blocking, check Lambda VPC settings
aws lambda get-function-configuration \
  --function-name mcelveen-trading-system \
  --region us-east-2 | jq .VpcConfig
```

---

## Issue 4: Claude API Rate Limiting (Too Many Requests)

### Symptoms
```
errorMessage: "Rate limit exceeded: 50 requests per minute"
errorType: "RateLimitError"
```

### Root Causes
1. EventBridge trigger firing too frequently
2. Multiple Lambda invocations running in parallel (concurrency > 1)
3. Anthropic account tier has lower rate limits

### Diagnosis
```bash
# Check EventBridge trigger schedule
aws events describe-rule --name mcelveen-trading-trigger --region us-east-2

# Check Lambda concurrent execution count
aws lambda get-function-concurrency \
  --function-name mcelveen-trading-system \
  --region us-east-2
```

### Solutions

**Option A: Reduce Execution Frequency**
```bash
# Change schedule from every 6 hours to every 8 hours
aws events put-rule \
  --name mcelveen-trading-trigger \
  --schedule-expression "cron(0 0,8,16 * * ? *)" \
  --state ENABLED \
  --region us-east-2
```

**Option B: Enforce Single Concurrent Execution**
```bash
# Set reserved concurrency to 1 (prevent parallel invocations)
aws lambda put-function-concurrency \
  --function-name mcelveen-trading-system \
  --reserved-concurrent-executions 1 \
  --region us-east-2
```

**Option C: Implement Request Queuing**
```python
import time

class ClaudeEngine:
    def __init__(self):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.last_request_time = 0
        self.min_interval = 1.2  # 50 requests/min = 1.2s per request
    
    def select_assets(self, directives, macro_analysis):
        # Wait if necessary to respect rate limits
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        
        # Make request
        response = client.messages.create(...)
        self.last_request_time = time.time()
        
        return response
```

**Option D: Upgrade Anthropic Account**
- Contact Anthropic sales to increase rate limits
- Mention production autonomous trading use case

---

## Issue 5: DynamoDB Throttling (Write Limit Exceeded)

### Symptoms
```
errorMessage: "ProvisionedThroughputExceededException"
errorType: "DynamoDBError"
```

### Root Causes
1. Multiple Lambda invocations writing to DynamoDB simultaneously
2. Provisioned write capacity too low (if using provisioned mode)
3. Audit trail logging too verbose (too many large items)

### Diagnosis
```bash
# Check DynamoDB metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedWriteCapacityUnits \
  --dimensions Name=TableName,Value=mcelveen-trading-ledger \
  --start-time 2026-10-06T00:00:00Z \
  --end-time 2026-10-06T23:59:59Z \
  --period 3600 \
  --statistics Sum \
  --region us-east-2
```

### Solutions

**Option A: Use On-Demand Billing (Already Configured)**
DynamoDB is already set to `PAY_PER_REQUEST`, so it should scale automatically. If you still see throttling:

**Option B: Increase Write Capacity (Provisioned Mode)**
```bash
# Switch to provisioned capacity (only if PAY_PER_REQUEST isn't working)
aws dynamodb update-billing-mode \
  --table-name mcelveen-trading-ledger \
  --billing-mode PROVISIONED \
  --provisioned-throughput ReadCapacityUnits=10,WriteCapacityUnits=10 \
  --region us-east-2
```

**Option C: Batch Writes**
```python
# Instead of individual PutItem for each order:
# Batch multiple audit log entries into single BatchWriteItem

def audit_log_batch(self, entries):
    with dynamodb.batch_writer() as batch:
        for entry in entries:
            batch.put_item(Item=entry)
    logger.info(f"Batch logged {len(entries)} items")
```

**Option D: Reduce Log Verbosity**
```python
# Instead of logging every order detail:
# Log only high-level summary + error details

def audit_log(self, execution_id, stage, result):
    # Keep JSON small
    item = {
        'execution_id': execution_id,
        'stage': stage,
        'result': result,  # 'success' or 'error'
        'timestamp': datetime.utcnow().isoformat(),
    }
    # Only include detailed error info if result == 'error'
    if result == 'error':
        item['error_details'] = {...}
    
    table.put_item(Item=item)
```

---

## Issue 6: Schwab Order Execution Fails (HTTP 404 or Invalid Symbol)

### Symptoms
```json
{
    "order_id": "12345678",
    "symbol": "INVALID",
    "status": "REJECTED",
    "error": "Symbol not found in Schwab API"
}
```

### Root Causes
1. Claude recommended delisted or invalid ticker symbol
2. Schwab API symbol format differs (e.g., mutual funds require suffix)
3. Schwab account not approved for certain asset classes (options, futures)

### Diagnosis
```bash
# Query audit trail for failed execution
aws dynamodb query \
  --table-name mcelveen-trading-ledger \
  --key-condition-expression "execution_id = :id" \
  --expression-attribute-values '{":id": {"S": "exec_20261006_143215_a7f2"}}' \
  --region us-east-2

# Check CloudWatch Logs for Schwab API response
aws logs tail /aws/lambda/mcelveen-trading-system --follow --grep "Schwab" --region us-east-2
```

### Solutions

**Option A: Validate Symbol Before Trading**
```python
# In portfolio_mgr.py
VALID_SYMBOLS = {
    'SPY', 'QQQ', 'VEA', 'VWO', 'BND', 'AGG', 'VGSH', 'VMFXX'
}

def run_guardrails(self, orders):
    validated = []
    for order in orders:
        # New Level 0: Symbol validation
        if order.get('symbol') not in VALID_SYMBOLS:
            logger.warning(f"Guardrail FAILED: Invalid symbol - {order.get('symbol')}")
            continue
        
        # ... rest of guardrails ...
```

**Option B: Check Schwab Symbol Format**
```python
# Some Schwab mutual funds require special notation
SCHWAB_SYMBOL_MAP = {
    'VMFXX': 'VMFXX',      # Standard ticker
    'SPAXX': 'SPAXX',      # Money market fund
}

def normalize_symbol(self, symbol):
    return SCHWAB_SYMBOL_MAP.get(symbol, symbol)
```

**Option C: Implement Graceful Degradation**
```python
# If order execution fails, skip it and continue with others
def execute_orders(self, orders):
    results = {
        'orders': [],
        'execution_status': 'success',
        'errors': []
    }
    
    for order in orders:
        try:
            result = self._place_order(order)
            results['orders'].append(result)
        except Exception as e:
            logger.error(f"Order execution failed for {order}: {e}")
            results['errors'].append({
                'symbol': order.get('symbol'),
                'error': str(e)
            })
            continue  # Don't fail entire batch
    
    return results
```

---

## Issue 7: Lambda Out of Memory

### Symptoms
```
errorMessage: "Process exited before completing request"
errorType: "OutOfMemoryError"
```

### Root Causes
1. Lambda memory set too low (512 MB default)
2. Memory leak in trading logic (large objects not garbage collected)
3. Claude response too large (unusual response content)

### Diagnosis
```bash
# Check CloudWatch Logs for memory warnings
aws logs tail /aws/lambda/mcelveen-trading-system --follow --grep "memory" --region us-east-2

# Check current function configuration
aws lambda get-function-configuration \
  --function-name mcelveen-trading-system \
  --region us-east-2 | jq .MemorySize
```

### Solutions

**Option A: Increase Memory Allocation**
```bash
# Increase from 512 MB to 1024 MB
aws lambda update-function-configuration \
  --function-name mcelveen-trading-system \
  --memory-size 1024 \
  --region us-east-2
```
Note: Higher memory = higher CPU, faster execution, lower total cost

**Option B: Optimize Memory Usage**
```python
# Don't keep large objects in memory between invocations
class ClaudeEngine:
    def __init__(self):
        # Don't cache responses between invocations
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
    
    def select_assets(self, directives, macro_analysis):
        # Create client fresh each time
        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(...)
        
        # Parse and return
        recommendations = json.loads(response.content[0].text)
        return recommendations
        # response, client go out of scope and are garbage collected
```

---

## Quick Diagnostic Checklist

When something breaks, run this:

```bash
#!/bin/bash

echo "=== Lambda Status ==="
aws lambda get-function --function-name mcelveen-trading-system --region us-east-2 | jq .Configuration

echo "=== Recent Logs ==="
aws logs tail /aws/lambda/mcelveen-trading-system --max-items 50 --region us-east-2

echo "=== DynamoDB Audit Trail (Last 5 executions) ==="
aws dynamodb scan \
  --table-name mcelveen-trading-ledger \
  --limit 5 \
  --scan-index-forward false \
  --region us-east-2 | jq '.Items[] | {execution_id, stage, result, timestamp}'

echo "=== EventBridge Rule Status ==="
aws events describe-rule --name mcelveen-trading-trigger --region us-east-2

echo "=== CloudWatch Alarms ==="
aws cloudwatch describe-alarms --alarm-names mcelveen-daily-frequency-exceeded mcelveen-error-rate-spike --region us-east-2 | jq '.Alarms[] | {AlarmName, StateValue, StateReason}'
```

---

## When to Escalate to Schwab/Anthropic Support

### Contact Schwab Support if:
- OAuth token refresh consistently fails with 401
- Order execution returns 403 (permission denied)
- Symbol validation fails for multiple valid tickers
- API returns 5xx errors (server-side issue)

### Contact Anthropic Support if:
- Rate limits preventing legitimate usage (request higher quota)
- Claude API consistently returns invalid JSON
- Model behavior changed unexpectedly
- Need to discuss production trading use case

---

**Document Version:** 1.0  
**Last Updated:** 2026-10-06  
**Maintained By:** Kevin McElveen
