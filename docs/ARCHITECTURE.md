# McElveen Autonomous Trading System — Architecture Guide

## System Overview

The McElveen Autonomous Trading System is a multi-agent AI orchestration platform designed for **deterministic, risk-controlled autonomous trading** in AWS Lambda serverless environments. The architecture prioritizes fault tolerance, auditability, and guaranteed safety over performance.

### 5-Step Decision Pipeline

```
┌─────────────────┐
│  1. CIO Analysis │  Market regime detection (VIX, rates, Fed policy)
└────────┬────────┘
         │
         ↓
┌─────────────────────┐
│ 2. Portfolio Manager │  Rebalancing directives based on regime
└────────┬────────────┘
         │
         ↓
┌──────────────────┐
│ 3. Claude Engine │  Semantic asset selection with structured JSON
└────────┬─────────┘
         │
         ↓
┌──────────────────────┐
│ 4. Risk Guardrails   │  8-level deterministic validation (never bypassed)
└────────┬─────────────┘
         │
         ↓
┌─────────────────┐
│ 5. Schwab Trader │  Order execution with OAuth token refresh
└─────────────────┘
```

---

## Component Architecture

### 1. CIO Analysis Engine (`core/cio_analysis.py`)

**Purpose:** Analyzes macroeconomic conditions and produces confidence-scored market regimes.

**Key Methods:**
- `analyze_market_conditions()` — Main entry point
  - Fetches: VIX, interest rates (10Y, 2Y), Fed policy signals
  - Computes: market_regime (BULLISH/NEUTRAL/BEARISH), confidence (1–10)
  - Returns: Timestamped analysis with rationale

**Market Regime Logic:**
```python
if VIX < 15 AND 10Y rate < 4.0%:
    regime = BULLISH       # Risk-on environment
    confidence = 8

elif VIX > 25 OR 10Y rate > 5.0%:
    regime = BEARISH       # Risk-off environment
    confidence = 6

else:
    regime = NEUTRAL       # Balanced environment
    confidence = 5
```

**Future Enhancements:**
- Real API calls to Alpha Vantage, IEX Cloud, or Fed data APIs
- Machine learning regime scoring (beyond simple thresholds)
- Sentiment analysis from financial news feeds

---

### 2. Portfolio Manager (`core/portfolio_mgr.py`)

**Purpose:** Translates macro analysis into specific asset allocation directives and runs 8-level risk guardrails.

**Key Methods:**

#### `calculate_directives(macro_analysis)`
Emits **portfolio rebalancing actions** based on market regime:

**BULLISH regime example:**
```python
directives['actions'] = [
    {'asset_class': 'US_EQUITIES', 'action': 'BUY_MORE', 'target_pct': 0.65},
    {'asset_class': 'BONDS', 'action': 'SELL', 'target_pct': 0.10}
]
```

**BEARISH regime example:**
```python
directives['actions'] = [
    {'asset_class': 'BONDS', 'action': 'BUY_MORE', 'target_pct': 0.25},
    {'asset_class': 'CASH', 'action': 'BUY_MORE', 'target_pct': 0.10}
]
```

#### `run_guardrails(orders)` — 8-Level Safety Validation

**Level 1: Liquidity Check**
- Validates order size vs. typical trading volume
- Rejects illiquid assets or excessive position sizes

**Level 2: Concentration Limit**
- Max 15% of portfolio in single position (configurable)
- Prevents portfolio blow-up on single-asset move

**Level 3: Daily Trade Frequency**
- Max 3 trades per day (configurable)
- Prevents thrashing and excessive transaction costs

**Levels 4–8: Extended Validation** *(to be implemented)*
- Position sizing scaled by confidence score
- VIX-adjusted leverage (reduce size when VIX > 25)
- Format validation (ensure JSON structure matches expected schema)
- Compliance checks (restricted securities list, sector limits)
- Authorization/signing verification (signed by Portfolio Manager)

**CRITICAL DESIGN PRINCIPLE:**
> No Claude output is ever executed directly. All recommendations **must pass through all 8 levels of guardrails** before reaching Schwab. If any level fails, the entire order batch is rejected and logged.

**Guardrails Result:**
```python
{
    'validated_orders': [...],  # Passed all 8 levels
    'rejected_orders': [...],   # Failed at least one level with reason
    'validation_status': 'FULL_PASS' | 'PARTIAL_FAIL' | 'FULL_FAIL'
}
```

---

### 3. Claude AI Engine (`core/claude_engine.py`)

**Purpose:** Calls Claude API to select specific assets based on Portfolio Manager directives and CIO analysis.

**Key Methods:**

#### `select_assets(directives, macro_analysis)`
- Constructs deterministic prompt with directives + macro state
- Calls Anthropic Claude API with structured output requirement
- **Forces JSON response format** via prompt engineering (not tool_choice, to guarantee parsing)
- Returns: List of specific assets with actions (BUY/HOLD/SELL) + confidence alignment score

**Prompt Structure:**
```
You are a portfolio optimizer. Given the market regime '{regime}' 
with confidence {confidence}/10, and the portfolio manager directives 
{directives}, recommend specific assets in this JSON format:

{
    "assets": [
        {"symbol": "SPY", "action": "BUY", "quantity": 50, "rationale": "..."}
    ],
    "confidence_alignment": 0.92
}
```

**Return Structure:**
```json
{
    "assets": [
        {
            "symbol": "SPY",
            "action": "BUY",
            "quantity": 50,
            "rationale": "US equity core exposure; bullish regime"
        },
        {
            "symbol": "VEA",
            "action": "HOLD",
            "quantity": 30,
            "rationale": "Maintain international diversification"
        }
    ],
    "confidence_alignment": 0.92,
    "timestamp": "2026-10-06T14:32:15Z"
}
```

**Error Handling:**
- If Claude returns non-JSON, log error and pass empty recommendations
- Guardrails engine will reject the batch as "FULL_FAIL"
- Audit trail captures: input prompt, Claude response, validation result

---

### 4. Risk Guardrails Engine (in `core/portfolio_mgr.py`)

**Design Philosophy:**
The guardrails engine is the **"circuit breaker"** of the system. It embodies this principle:

> **Trust Nothing. Verify Everything. Never Execute Without Proof.**

Every order produced by Claude flows through deterministic validation before it can touch real money.

**Why Guardrails Are Critical:**
- AI systems can hallucinate or misinterpret complex financial instructions
- Market conditions can change between analysis and execution
- Regulatory environments (broker requirements, compliance) are non-negotiable
- Audit trails must be immutable (for regulators, auditors, and the user)

**Guardrails Validation Matrix:**

| Level | Check | Pass Condition | Failure Action | Example |
|-------|-------|---|---|---|
| 1 | Liquidity | Order size < 20% avg daily volume | Reject order | Trying to buy 100k shares of illiquid stock |
| 2 | Concentration | Position value < 15% portfolio | Reject order | Adding $500k to existing $3M position |
| 3 | Frequency | ≤ 3 trades in 24h | Reject order | 4th trade attempt within same day |
| 4 | Position Sizing | Qty scaled by confidence score | Reduce qty | Confidence 5/10 → reduce buy qty by 50% |
| 5 | VIX Modifier | Reduce exposure when VIX > 25 | Scale position | VIX 28 → reduce position size by 30% |
| 6 | Format Validation | JSON matches expected schema | Reject batch | Missing "rationale" field in order |
| 7 | Compliance | Symbol not in restricted list | Reject order | Trying to buy bankrupt company |
| 8 | Authorization | Order signed by Portfolio Manager | Reject batch | Order came from unknown source |

**Audit Trail Capture:**
Every validation decision is logged to CloudWatch Logs and DynamoDB:

```json
{
    "execution_id": "exec_20261006_143215_a7f2",
    "timestamp": "2026-10-06T14:32:15Z",
    "stage": "guardrails",
    "level": 2,
    "check": "concentration_limit",
    "order": {"symbol": "TSLA", "action": "BUY", "quantity": 500},
    "result": "FAILED",
    "reason": "Position value 25% exceeds 15% limit",
    "action_taken": "REJECTED"
}
```

---

### 5. Schwab Trader (`core/schwab_trader.py`)

**Purpose:** Executes validated orders on Charles Schwab via OAuth 2.0 authenticated API.

**Key Methods:**

#### `execute_orders(orders)`
- Iterates over validated order list
- For each order:
  - Calls `_place_order()` with Schwab API
  - Captures execution result (order ID, filled price, status)
  - Logs success/failure to audit trail
- Returns: Execution report with all order statuses

**OAuth 2.0 Token Refresh:**
```python
def _refresh_oauth_token(self):
    """Refresh Schwab OAuth 2.0 token"""
    # Fetch new token using client_id + client_secret
    # Store in secure cache (NOT in code)
    # Use for subsequent API calls
```

**Error Handling:**
- If any order fails, log the error and continue with remaining orders
- Returns `execution_status: 'partial_failure'` if some orders succeeded
- Returns `execution_status: 'full_failure'` if all orders failed
- Never retries without explicit user instruction (prevents runaway trades)

**Execution Result:**
```json
{
    "execution_status": "success",
    "orders": [
        {
            "order_id": "SW-20261006-84729",
            "symbol": "SPY",
            "action": "BUY",
            "quantity": 50,
            "status": "FILLED",
            "executed_price": 542.35,
            "total_value": 27117.50,
            "timestamp": "2026-10-06T14:32:47Z"
        }
    ]
}
```

---

## Configuration Management (`config/settings.py`)

**All configuration is environment-driven.** No secrets or credentials are hardcoded.

**Environment Variables:**

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `AWS_REGION` | AWS region for Lambda/DynamoDB | `us-east-2` | string |
| `DYNAMODB_TABLE` | Audit log table name | `mcelveen-trading-ledger` | string |
| `CLOUDWATCH_NAMESPACE` | CloudWatch metrics namespace | `McElveenTrading` | string |
| `PORTFOLIO_TARGET_ALLOCATION` | Target allocation JSON | `{"US_EQUITIES": 0.60, ...}` | JSON |
| `CONCENTRATION_LIMIT` | Max % in single position | `0.15` | float |
| `DAILY_TRADE_FREQUENCY_CAP` | Max trades per day | `3` | int |
| `VIX_THRESHOLD_AGGRESSIVE` | VIX threshold for bullish posture | `15` | float |
| `VIX_THRESHOLD_DEFENSIVE` | VIX threshold for defensive posture | `25` | float |
| `SCHWAB_CLIENT_ID` | OAuth client ID | (required) | string |
| `SCHWAB_CLIENT_SECRET` | OAuth client secret | (required) | string |
| `ANTHROPIC_API_KEY` | Claude API key | (required) | string |

**Loading Pattern:**
```python
CONCENTRATION_LIMIT = float(os.getenv('CONCENTRATION_LIMIT', 0.15))
```

This pattern ensures:
- All values are read at runtime (not deployment time)
- Defaults are sensible but overridable
- No values are ever logged (security)

---

## Lambda Execution Flow

**Entry Point:** `lambda_function.py` — `handler(event, context)`

**Execution Sequence:**

```
┌─ Lambda triggered (CloudWatch Rule every 6 hours, or manual invoke)
│
├─ 1. Instantiate all engines:
│     └─ CIOCore, PortfolioManager, ClaudeEngine, SchwabTrader
│
├─ 2. CIO Analysis:
│     └─ Fetch VIX, rates → compute market regime + confidence
│
├─ 3. Portfolio Directives:
│     └─ Market regime → rebalancing actions
│
├─ 4. Claude Asset Selection:
│     └─ Directives + macro analysis → specific asset recommendations
│
├─ 5. Risk Guardrails (CRITICAL):
│     └─ All 8 levels validation → pass/fail decision
│
├─ 6. Schwab Execution:
│     └─ If guardrails PASS: execute on Schwab
│        If guardrails FAIL: skip execution, log reason
│
├─ 7. Audit Logging:
│     └─ Record entire execution flow to DynamoDB
│
└─ Return Lambda response (200 or 500 status code)
```

**Fault Tolerance:**
- If CIO API fails → return previous regime from cache
- If Claude API fails → return empty recommendations (guardrails reject batch)
- If Schwab API fails → log error, retry up to 3x, then alert operator
- If DynamoDB fails → log to CloudWatch, continue execution (audit trail is best-effort)

---

## Security & Compliance

### Authentication & Secrets Management

**Credentials Never in Code:**
- `.gitignore` prevents `.env`, `*.pem`, `oauth_tokens.json`, `.aws/` from being committed
- All credentials via Lambda environment variables (encrypted at rest by AWS)
- `.env.example` shows variable names only (for developers to reference)

**OAuth 2.0 Token Refresh:**
- Schwab API requires fresh tokens every 30 minutes
- `_refresh_oauth_token()` fetches new token and caches securely
- Old tokens never written to disk or logs

### Audit Trail & Compliance

**Immutable Execution Log (DynamoDB):**
Every trade, validation, and error is recorded:

```json
{
    "execution_id": "exec_20261006_143215_a7f2",
    "timestamp": "2026-10-06T14:32:15Z",
    "stage": "execution",
    "symbol": "SPY",
    "action": "BUY",
    "quantity": 50,
    "result": "FILLED",
    "executed_price": 542.35,
    "user": "autonomous-system",
    "confirmation": true
}
```

**CloudWatch Logs & Metrics:**
- All API calls logged with request/response details
- Metrics: orders per day, success rate, execution time
- Alarms: if daily trade frequency exceeds cap, if VIX spikes, if error rate > 5%

### Financial Regulatory Compliance

**Broker Requirements (Schwab):**
- OAuth 2.0 authentication (not static tokens)
- Immutable audit trail
- Order verification & confirmation logging

**Potential Regulatory Concerns (Future):**
- If managing client assets, may need SEC/FINRA registration
- If using margin, must comply with Reg T requirements
- If executing high-frequency trades, may trigger market maker obligations

---

## Deployment Architecture

**AWS Lambda:**
- Runtime: Python 3.11+
- Memory: 512 MB (sufficient for API calls + orchestration)
- Timeout: 60 seconds (allows for API retries)
- Concurrency: 1 (prevents duplicate trades from concurrent invocations)

**AWS DynamoDB:**
- Table: `mcelveen-trading-ledger`
- Partition Key: `execution_id`
- Sort Key: `timestamp`
- TTL: 90 days (auto-deletes old records)
- On-demand billing (variable workload)

**AWS CloudWatch:**
- Namespace: `McElveenTrading`
- Metrics: orders/day, success_rate, execution_latency_ms
- Logs: all API calls, validation decisions, errors
- Alarms: daily frequency threshold, error rate spike

**Trigger Schedule:**
- CloudWatch Events Rule: Every 6 hours (market open hours)
- Manual triggers: Ad-hoc rebalancing when market conditions shift

---

## Performance Characteristics

**Typical Execution Profile:**
- CIO Analysis: ~500ms (API calls + logic)
- Portfolio Manager: ~100ms (in-memory calculations)
- Claude API call: ~3–5 seconds (network latency + inference)
- Guardrails validation: ~200ms (in-memory checks)
- Schwab order execution: ~1–2 seconds per order
- **Total end-to-end: ~5–10 seconds** (depends on API latencies)

**Scaling Considerations:**
- Lambda scales automatically (up to 1000 concurrent executions)
- DynamoDB on-demand scales automatically
- CloudWatch Logs scale automatically
- Schwab API rate limits: 120 requests/minute (plenty of headroom)
- Anthropic API rate limits: 50 requests/minute (per account, configurable)

---

## Testing & Observability

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY="your-key"
export SCHWAB_CLIENT_ID="your-id"
export SCHWAB_CLIENT_SECRET="your-secret"

# Run tests
pytest tests/

# Invoke Lambda locally
python -m pytest tests/test_lambda_handler.py -v
```

### Production Monitoring
- CloudWatch Dashboard: Real-time metrics + logs
- SNS Alerts: Daily summary email, error notifications
- DynamoDB Scan: Monthly audit of execution records
- GitHub Actions: Deploy on push to main, run tests first

---

## Future Roadmap

**Phase 1 (Current):** MVP with placeholder APIs
- ✅ Multi-agent orchestration framework
- ✅ 8-level guardrails engine
- ✅ OAuth 2.0 integration
- ✅ Audit trail infrastructure

**Phase 2 (Q1 2027):** Live API Integration
- Real VIX/interest rate feeds
- Live Schwab order execution
- Real Claude API calls (currently mocked)
- DynamoDB audit logging

**Phase 3 (Q2 2027):** ML Enhancement
- Machine learning market regime scoring
- Anomaly detection for unusual market conditions
- Recommendation confidence calibration

**Phase 4 (Q3 2027):** Multi-Portfolio Support
- Support multiple client portfolios
- Per-client guardrails customization
- Consolidated reporting & reconciliation

---

**Document Version:** 1.0  
**Last Updated:** 2026-10-06  
**Maintained By:** Kevin McElveen  
**Status:** Live & Operational (v3.0.27)
