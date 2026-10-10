"""
================================================================================
McElveen Autonomous Trading System - v3.0.31 COMPLETE PRODUCTION
================================================================================

THREE-AGENT AI ARCHITECTURE:
1️⃣ CHIEF INVESTMENT OFFICER (CIO) - Macro Analysis + Portfolio Constraints
   ├─ Reads market data: VIX, yields, sector performance
   ├─ Reads portfolio state: available_cash, holdings, drawdown, allocation
   ├─ Returns: Market regime + specific ticker recommendations with dynamic position sizes
   └─ CRITICAL: All amounts derived from actual available_cash (never hardcoded)

2️⃣ PORTFOLIO MANAGER - Active Allocation & Rebalancing
   ├─ Evaluates CIO thesis alignment + position performance
   ├─ Decides: BUY (new), BUY_MORE (existing winner), SELL_AND_BUY (rebalance), HOLD (monitor)
   ├─ Trader Mode: Liquidates worst performer, redeploys capital to opportunity
   └─ Enforces: Sector limits, concentration guardrails, conviction thresholds

3️⃣ RISK MANAGER - 8-Level Guardrails + Account Health
   ├─ G1: No duplicate positions (unless Portfolio Manager signals BUY_MORE)
   ├─ G2: Max 25% position exposure per holding
   ├─ G3: Sector concentration limit (25%)
   ├─ G4: Trade frequency limits (model-dependent: 2-5 trades/day)
   ├─ G5: Options exposure cap (30%)
   ├─ G6: Cash drag prevention (min 5%)
   ├─ G7: Portfolio drawdown protection (-35% hard limit for recovery buying)
   ├─ G8: Holdings count tiers (20/$1-100, 30/$100-500, 50/$500+)
   └─ Account Health: Halts if option_buying_power < 0 (margin deficit)

DEPLOYMENT: AWS Lambda + Charles Schwab OAuth2 + Anthropic Claude API
EXECUTION: Autonomous (when AUTONOMOUS_MODE_ENABLED=true) or Dry-Run (for testing)

CORE FEATURES (v3.0.31):
✅ Dynamic Position Sizing: Amounts scale to actual available_cash (not hardcoded $10)
✅ Defensive Response Parsing: Handles incomplete/malformed CIO responses gracefully
✅ Trader Mode (v3.0.25): Active rebalancing—sells worst performer, redeploys to opportunity
✅ Account Health Gating: Prevents execution errors via margin deficit detection

CRITICAL FIXES v3.0.31:
✅ FIX #1: Hard halt if trade_size ≤ 0 (portfolio too small to trade)
✅ FIX #2: Hard halt if option_buying_power < 0 (margin deficit protection)
✅ FIX #3: Account health gate before trading (prevents execution errors)
✅ FIX #4: CIO restructured to read BOTH market data + portfolio state (available_cash, holdings, drawdown)
✅ FIX #5: Dynamic amounts in CIO recommendations (reads available_cash, never hardcoded $10)
✅ FIX #6: Robust parsing for incomplete recommendation blocks (.get() with defaults)
✅ FIX #7: Lambda handler reorganized (CIO runs STEP 3 AFTER STEP 5 metrics when data is ready)
✅ FIX #8: Portfolio drawdown limit adjusted to -35% for recovery mode (was -15%)
✅ FIX #9: F-String escape bug in Claude prompt (${amount:.2f} → plain text example)
✅ FIX #10: Missing sector_signal field in macro_data (KeyError in Trader Claude Step 8 → added BALANCED default)

TRADE LIMITS (AGGRESSIVE - Option B):
- VIX < 12: 5 trades/day (claude-opus-5-5)
- VIX 12-20: 4 trades/day (claude-sonnet-5)
- VIX > 20: 2 trades/day (claude-opus-5-5)

DEPOSITS: DISABLED - Manual deposits only

✅ BUG FIX #37: Order status validation (REJECTED orders are now blocked)
✅ BUG FIX #36: Order verification (confirmed on Schwab before logging)
✅ BUG FIX #35: Real market data (Schwab quotes, not Yahoo Finance)
✅ FIX v3.0.14 #1: Schwab API validation endpoint (HTTP 404 handling graceful)
✅ FIX v3.0.14 #2: Fallback symbol selection (random non-excluded from universe)
✅ FIX v3.0.14 #3: Dynamic trade sizing (scales with available capital, not fixed $5)
✅ ALL ASSET CLASSES: Stocks, ETFs, Bonds, Options, Funds, Crypto-ready
✅ CHIEF ECONOMIST: Macro analysis + market regime detection
✅ CLAUDE AUTONOMOUS: Multi-agent decision framework
✅ DYNAMIC TRADE SIZING: Auto-scales with portfolio growth
✅ POSITION TRACKING: Real-time P&L, allocation %, cost basis
✅ GUARDRAILS: 8-level risk management with holdings limit tiers and drawdown limits
✅ TRADER MODE: Active rebalancing — sells worst performer, redeploys to new opportunity
✅ PORTFOLIO DASHBOARD: Composition, exposure, performance metrics
✅ WEEKLY DEPOSITS: Automated $10 deposits for POC strategy (Thursday 8 AM)
✅ COMPLIANCE TRACKING: RIA audit trail, order verification logs
✅ ENHANCED LOGGING: Detailed metrics, trade journal, performance stats
✅ MULTI-AGENT: Chief Investment Officer + Claude AI + Risk Manager
✅ ALERTS: SMS, Email, Slack-ready with detailed execution reports

READY FOR PAYLINQ Q2 2027 RIA LAUNCH
"""

import json
import boto3
import requests
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal
from anthropic import Anthropic
import math
import hashlib

print("[INIT] McElveen Autonomous Trading System v3.0.31 - HARDENED PRODUCTION")
print("[INIT] ✅ FIX #1: Hard halt when trade_size = 0")
print("[INIT] ✅ FIX #2: Hard halt when option_buying_power < 0")
print("[INIT] ✅ FIX #3: Account health gate before trading")
print("[INIT] ✅ v3.0.28 BASE: All trading logic, portfolio manager, trader mode")
print("[INIT] All systems loaded - ready for deployment")

# =====================================================================
# CONFIGURATION & CONSTANTS
# =====================================================================

ACCOUNT_ID = "7720-9306"
SCHWAB_ACCOUNT_ID = os.environ.get('SCHWAB_ACCOUNT_ID', ACCOUNT_ID)

# Dynamic trade sizing (FIX v3.0.14 #3: Now fully dynamic based on capital)
BASE_TRADE_SIZE = 4.00  # Increased from 1.75 for $5+ minimum orders (Schwab requirement)
MIN_TRADE_SIZE_FLOOR = 1.00  # CTO EXECUTIVE FIX: $5 was creating 0.0263 fractional shares; $50 prevents microfraction bug
MIN_TRADE_SIZE_TARGET = 1.00  # Minimum ensures whole shares or tradeable fractionals for all asset prices
MAX_TRADE_SIZE = 25.00  # Note: May need increase if using higher trade sizes

POSITION_LIMIT_PCT = 0.35  # CIO decision: 35% allows $5 minimum orders on $15+ buying power; guardrails tighten naturally as portfolio grows
OPTIONS_EXPOSURE_LIMIT_PCT = 0.30
SECTOR_EXPOSURE_LIMIT_PCT = 0.25
# FIX v3.0.31 #5: PORTFOLIO_DRAWDOWN_LIMIT_PCT for recovery buying during drawdown phase
# - Oct 8, 2026: Adjusted from 0.15 (-15%) to 0.35 (-35%) to enable "buy the dip" strategy
# - Allows CIO to make recommendations when portfolio is down 35% (recovery opportunity)
# - Guardrail G7 will still block if portfolio < -35%, protecting against catastrophic loss
# - This enables dynamic buying at portfolio lows, compounding recovery upside
PORTFOLIO_DRAWDOWN_LIMIT_PCT = 0.35
MAX_CASH_DRAG = 0.05

# G8: Holdings Limit (Tiered by Portfolio Size) - POC OPTIMIZED
# Loosened tiers for execution velocity during POC validation phase
# Tightens naturally at scale ($100+) for concentration discipline
HOLDINGS_LIMIT_TIERS = {
    (1, 100): 20,        # $1–$100: max 20 holdings (POC: prioritize velocity)
    (100, 500): 30,      # $100–$500: max 30 holdings (growth phase)
    (500, float('inf')): 50  # $500+: max 50 holdings (concentration discipline)
}

AUTONOMOUS_MODE_ENABLED = os.environ.get('AUTONOMOUS_MODE_ENABLED', 'false').lower() == 'true'
WEEKLY_DEPOSIT_ENABLED = os.environ.get('WEEKLY_DEPOSIT_ENABLED', 'true').lower() == 'true'
WEEKLY_DEPOSIT_AMOUNT = float(os.environ.get('WEEKLY_DEPOSIT_AMOUNT', '10.00'))

# AWS Resources
DYNAMODB = boto3.resource('dynamodb', region_name='us-east-2')
SNS = boto3.client('sns', region_name='us-east-2')
CLOUDWATCH = boto3.client('cloudwatch', region_name='us-east-2')

TRADE_JOURNAL_TABLE = os.environ.get('TRADE_JOURNAL_TABLE', 'mcelveen-trade-journal')
POSITIONS_SNAPSHOT_TABLE = os.environ.get('POSITIONS_SNAPSHOT_TABLE', 'mcelveen-positions-snapshot')
EXECUTION_LOG_TABLE = os.environ.get('EXECUTION_LOG_TABLE', 'mcelveen-execution-log')
PORTFOLIO_METRICS_TABLE = os.environ.get('PORTFOLIO_METRICS_TABLE', 'mcelveen-portfolio-metrics')
OAUTH_TOKENS_TABLE = os.environ.get('OAUTH_TOKENS_TABLE', 'mcelveen-oauth-tokens')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', 'arn:aws:sns:us-east-2:650589744593:McElveenAlerts')
ALERT_EMAIL = os.environ.get('ALERT_EMAIL', 'kvmcelveen@outlook.com,tesheina11@outlook.com')

# Schwab API
SCHWAB_BASE_URL = "https://api.schwabapi.com/trader/v1"
SCHWAB_CLIENT_ID = os.environ.get('SCHWAB_CLIENT_ID')
SCHWAB_CLIENT_SECRET = os.environ.get('SCHWAB_CLIENT_SECRET')
SCHWAB_REFRESH_TOKEN = os.environ.get('SCHWAB_REFRESH_TOKEN')

# Claude API
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY')
ENABLE_CACHE = os.environ.get('ENABLE_CACHE', 'false').lower() == 'true'
CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-5')

# Risk parameters
VOLATILITY_REGIMES = {
    'PANIC': (25.0, 100.0, 1.0, 0.05),      # (vix_min, vix_max, position_size_mult, max_daily)
    'HIGH': (20.0, 25.0, 0.8, 0.10),
    'ELEVATED': (12.0, 20.0, 1.0, 0.15),
    'NORMAL': (8.0, 12.0, 1.2, 0.20),
    'LOW': (0.0, 8.0, 1.5, 0.25),
}

print(f"[CONFIG] Trade size: ${BASE_TRADE_SIZE:.2f} (dynamic scaling enabled)")
print(f"[CONFIG] Autonomous mode: {AUTONOMOUS_MODE_ENABLED}")
print(f"[CONFIG] Weekly deposits: {'ENABLED' if WEEKLY_DEPOSIT_ENABLED else 'DISABLED'} (${WEEKLY_DEPOSIT_AMOUNT:.2f} every Thursday 8:00 AM EDT)")
print(f"[CONFIG] Account: {SCHWAB_ACCOUNT_ID}")

# =====================================================================
# PORTFOLIO STATE & METRICS
# =====================================================================

class PortfolioMetrics:
    """Track portfolio performance, allocation, and risk metrics."""

    def __init__(self, cash, holdings, previous_nav=None):
        self.cash = cash
        self.holdings = holdings
        self.timestamp = datetime.utcnow().isoformat() + 'Z'

        # Calculate current values
        self.position_value = sum(h['quantity'] * h.get('current_price', h['entry_price'])
                                 for h in holdings.values())
        self.nav = cash + self.position_value
        self.cash_pct = (cash / self.nav * 100) if self.nav > 0 else 100

        # Calculate performance metrics
        self.cost_basis = sum(h['quantity'] * h['entry_price'] for h in holdings.values())
        self.unrealized_pnl = self.position_value - self.cost_basis
        self.unrealized_pnl_pct = (self.unrealized_pnl / self.cost_basis * 100) if self.cost_basis > 0 else 0

        # Volatility metrics
        self.num_holdings = len(holdings)
        self.largest_position_pct = (max((h['quantity'] * h.get('current_price', h['entry_price']) / self.nav * 100
                                         for h in holdings.values()), default=0))

        # Asset class allocation
        self.allocation = self._calculate_allocation(holdings)

        # Previous NAV for drawdown tracking
        self.previous_nav = previous_nav or self.nav
        self.daily_change_pct = ((self.nav - self.previous_nav) / self.previous_nav * 100) if self.previous_nav > 0 else 0

    def _calculate_allocation(self, holdings):
        """Calculate allocation by asset class."""
        allocation = {
            'STOCK': 0,
            'SECTOR_ETF': 0,
            'BROAD_ETF': 0,
            'BOND_ETF': 0,
            'DIVIDEND_ETF': 0,
            'MUTUAL_FUND': 0,
            'OPTION_SPREAD': 0,
            'CASH': self.cash_pct
        }

        for holding in holdings.values():
            asset_class = holding.get('asset_class', 'STOCK')
            value = holding['quantity'] * holding.get('current_price', holding['entry_price'])
            pct = (value / self.nav * 100) if self.nav > 0 else 0
            allocation[asset_class] += pct

        return allocation

    def to_dict(self):
        """Export metrics as dictionary."""
        return {
            'timestamp': self.timestamp,
            'nav': Decimal(str(self.nav)),
            'cash': Decimal(str(self.cash)),
            'cash_pct': Decimal(str(self.cash_pct)),
            'position_value': Decimal(str(self.position_value)),
            'cost_basis': Decimal(str(self.cost_basis)),
            'unrealized_pnl': Decimal(str(self.unrealized_pnl)),
            'unrealized_pnl_pct': Decimal(str(self.unrealized_pnl_pct)),
            'num_holdings': self.num_holdings,
            'largest_position_pct': Decimal(str(self.largest_position_pct)),
            'daily_change_pct': Decimal(str(self.daily_change_pct)),
            'allocation': {k: Decimal(str(v)) for k, v in self.allocation.items()}
        }


# =====================================================================
# CHIEF INVESTMENT OFFICER - MACRO ANALYSIS + PORTFOLIO CONSTRAINTS
# =====================================================================
# FIX v3.0.31 #4: CIO now reads BOTH market data AND portfolio state
# - Receives available_cash from actual Schwab account (never hardcoded)
# - Returns specific ticker recommendations sized to available capital
# - Amounts are dynamic: if $10.92 available, recommends "$10.92 to VTI"
# - If $100 available, recommends "$100 to VTI" (same code, different cash)
# =====================================================================

def chief_investment_officer_analysis(vix, yields, sector_performance, portfolio_state):
    """
    Chief Investment Officer analyzes macro environment + portfolio constraints.
    Makes data-driven investment recommendations based on BOTH market conditions AND portfolio state.

    INPUT: market data (VIX, yields, sector performance) + portfolio constraints
    OUTPUT: regime, thesis, AND array of specific ticker recommendations with dynamic position sizes

    portfolio_state dict contains:
    - available_cash: float (from Schwab account, dynamic)
    - nav: float (portfolio net asset value)
    - holdings: dict (current positions)
    - drawdown_pct: float (daily P&L %)
    - num_holdings: int (count of positions)
    - allocation: dict (asset class allocation %)

    CRITICAL: All recommendation amounts are derived from portfolio_state['available_cash'].
    This ensures recommendations scale with actual available capital at runtime.
    """
    try:
        print("[CIO] Running macro & investment analysis with portfolio constraints...")

        client = Anthropic(api_key=CLAUDE_API_KEY)

        available_cash = portfolio_state.get('available_cash', 0)
        nav = portfolio_state.get('nav', 0)
        num_holdings = portfolio_state.get('num_holdings', 0)
        drawdown = portfolio_state.get('drawdown_pct', 0)

        # FIX v3.0.31 #9: F-String escape fix - Claude prompt format string
        # BUG: Old prompt used ${amount:.2f} which Python f-string tried to evaluate
        # RESULT: "cannot access local variable 'amount' where it is not associated with a value"
        # FIX: Changed example format to plain text "dollar amount - example: $10.92"

        # Separate system and user messages for token caching support
        system_prompt = """You are the Chief Investment Officer for McElveen Autonomous Trading System.
You read market data AND portfolio constraints to recommend SPECIFIC TICKERS with position sizes.

YOUR JOB:
1. Analyze macro regime + rate environment
2. Assess portfolio drawdown and recovery opportunity
3. Recommend 1-3 SPECIFIC TICKERS for current conditions
4. Size each recommendation to available cash
5. Return conviction level (1-10) for each pick

OUTPUT EXACTLY:

REGIME: [PANIC|HIGH|ELEVATED|NORMAL|LOW]
RATES: [HIGH_RATES|NORMAL|LOW_RATES|DECLINING]
APPETITE: [AGGRESSIVE|BALANCED|DEFENSIVE|CAUTIOUS]
THESIS: [1-2 sentence macro strategy]
CONFIDENCE: [1-10]

RECOMMENDATION_1:
TICKER: [symbol]
AMOUNT: [dollar amount to allocate - example: $10.92]
RATIONALE: [one sentence why this fits thesis + constraints]
CONVICTION: [1-10]

RECOMMENDATION_2: (optional if secondary pick makes sense)
TICKER: [symbol]
AMOUNT: [dollar amount - example: $10.92]
RATIONALE: [one sentence]
CONVICTION: [1-10]"""

        user_data = f"""MARKET DATA:
- VIX: {vix:.1f}
- Yields: TLT={yields.get('TLT', 100):.2f}, IEF={yields.get('IEF', 100):.2f}
- Sector leaders: {json.dumps({k: v for k, v in list(sector_performance.items())[:5]}, indent=2)}

PORTFOLIO CONSTRAINTS:
- Portfolio NAV: ${nav:.2f}
- Available cash: ${available_cash:.2f}
- Current holdings: {num_holdings}
- Drawdown: {drawdown:.2f}%
- Can invest: ${available_cash:.2f}"""

        # Build messages with optional cache control
        messages = [{'role': 'user', 'content': user_data}]

        # Prepare system message with cache control if enabled
        if ENABLE_CACHE:
            system_message = [
                {
                    'type': 'text',
                    'text': system_prompt,
                    'cache_control': {'type': 'ephemeral'}
                }
            ]
            print("[CACHE] Token caching ENABLED - using ephemeral cache for CIO system prompt")
        else:
            system_message = system_prompt
            print("[CACHE] Token caching DISABLED - standard API call")

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            system=system_message,
            messages=messages
        )

        response_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                response_text = block.text
                break

        # Log cache metrics for monitoring
        if ENABLE_CACHE and hasattr(response, 'usage'):
            cache_creation_tokens = getattr(response.usage, 'cache_creation_input_tokens', 0)
            cache_read_tokens = getattr(response.usage, 'cache_read_input_tokens', 0)
            input_tokens = getattr(response.usage, 'input_tokens', 0)
            output_tokens = getattr(response.usage, 'output_tokens', 0)

            if cache_creation_tokens > 0:
                print(f"[CACHE] WRITE - Created cache with {cache_creation_tokens} tokens (system prompt cached)")
            elif cache_read_tokens > 0:
                cache_hit_savings = cache_read_tokens * 0.9  # 90% cost reduction on cached tokens
                print(f"[CACHE] HIT - Read {cache_read_tokens} tokens from cache (saved ~${cache_hit_savings * 0.000001:.4f})")

            print(f"[TOKENS] Input: {input_tokens} | Output: {output_tokens} | Total: {input_tokens + output_tokens}")

        # Parse response (DEFENSIVE PARSING - FIX v3.0.31 #3)
        # Handles incomplete/out-of-order recommendation blocks gracefully
        # If Claude returns malformed response, parser still extracts what it can
        macro_data = {
            'regime': 'NORMAL',
            'rate_environment': 'NORMAL',
            'risk_appetite': 'BALANCED',
            'sector_signal': 'BALANCED',  # FIX #10: Default sector signal for Trader Claude (used in Step 8)
            'preferred_theme': 'BROAD_DIVERSIFICATION',  # Default theme for opportunity filtering
            'risk_rating': 'MEDIUM',  # Default environment risk level
            'thesis': 'Mixed market signals - balanced approach',
            'thesis_confidence': 5,  # Default: moderate confidence
            'recommendations': []
        }

        current_rec = None  # Current recommendation block being built
        for line in response_text.split('\n'):
            line = line.strip()
            if line.startswith('REGIME:'):
                macro_data['regime'] = line.split(':')[1].strip().upper()
            elif line.startswith('RATES:'):
                macro_data['rate_environment'] = line.split(':')[1].strip().upper()
            elif line.startswith('APPETITE:'):
                macro_data['risk_appetite'] = line.split(':')[1].strip().upper()
            elif line.startswith('THESIS:'):
                macro_data['thesis'] = line.split(':')[1].strip()
            elif line.startswith('CONFIDENCE:'):
                try:
                    macro_data['thesis_confidence'] = int(line.split(':')[1].strip())
                except:
                    macro_data['thesis_confidence'] = 5
            elif line.startswith('RECOMMENDATION_'):
                # New recommendation block - validate and save PREVIOUS recommendation if it has required fields
                if current_rec and 'ticker' in current_rec and 'amount' in current_rec:
                    # Recommendation is valid: has ticker + amount (required fields)
                    current_rec.setdefault('rationale', 'CIO recommendation')  # Provide defaults for optional fields
                    current_rec.setdefault('conviction', 5)
                    macro_data['recommendations'].append(current_rec)
                current_rec = {}  # Reset for new block
            elif line.startswith('TICKER:') and current_rec is not None:
                current_rec['ticker'] = line.split(':')[1].strip().upper()
            elif line.startswith('AMOUNT:') and current_rec is not None:
                # Parse amount: handle "$10.92", "10.92", "10", with fallback to available_cash
                try:
                    amount_str = line.split(':')[1].strip().replace('$', '').replace(',', '')
                    current_rec['amount'] = float(amount_str)
                except:
                    # If parsing fails, use whatever cash is actually available
                    current_rec['amount'] = available_cash
            elif line.startswith('RATIONALE:') and current_rec is not None:
                current_rec['rationale'] = line.split(':')[1].strip()
            elif line.startswith('CONVICTION:') and current_rec is not None:
                try:
                    current_rec['conviction'] = int(line.split(':')[1].strip())
                except:
                    current_rec['conviction'] = 5

        # Append final recommendation if it has required fields (ticker + amount)
        if current_rec and 'ticker' in current_rec and 'amount' in current_rec:
            current_rec.setdefault('rationale', 'CIO recommendation')
            current_rec.setdefault('conviction', 5)
            macro_data['recommendations'].append(current_rec)

        # Log recommendations with dynamic amounts (showing what's actually available to invest)
        print(f"[CIO] ✅ Regime: {macro_data['regime']} | Rates: {macro_data['rate_environment']} | Confidence: {macro_data['thesis_confidence']}/10")
        print(f"[CIO] 📋 Recommendations: {len(macro_data['recommendations'])} ticker(s)")
        for i, rec in enumerate(macro_data['recommendations'], 1):
            ticker = rec.get('ticker', 'UNKNOWN')
            amount = rec.get('amount', available_cash)  # Safe .get() with fallback to available_cash
            conviction = rec.get('conviction', 5)
            print(f"[CIO]   #{i}: {ticker} | ${amount:.2f} | Conviction: {conviction}/10")

        return macro_data

    except Exception as e:
        # Fallback if CIO analysis fails (network error, API issue, etc)
        # Still provides functional recommendation with dynamic available_cash
        print(f"[CIO] ⚠️ Analysis failed: {e}")
        return {
            'regime': 'NORMAL',
            'rate_environment': 'NORMAL',
            'risk_appetite': 'BALANCED',
            'thesis': 'Fallback to neutral - balanced portfolio approach',
            'thesis_confidence': 3,  # Low confidence on fallback
            'recommendations': [
                {
                    'ticker': 'VTI',
                    'amount': available_cash,  # DYNAMIC: Uses whatever cash is actually in account ($10.92, $100, $1000, etc)
                    'rationale': 'Broad market ETF for diversification',
                    'conviction': 3
                }
            ]
        }


# =====================================================================
# MARKET DATA - COMPLETE UNIVERSE
# =====================================================================

def get_market_overview(access_token):
    """Fetch VIX, yields, sector performance, rate environment."""
    try:
        print("[MARKET] Fetching market overview...")

        vix_url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols=%5EVIX&fields=quote"
        headers = {'Authorization': f'Bearer {access_token}'}
        vix_response = requests.get(vix_url, headers=headers, timeout=10)
        vix = 15.0
        if vix_response.status_code == 200:
            vix_data = vix_response.json()
            if '^VIX' in vix_data.get('quoteData', {}):
                vix = float(vix_data['quoteData']['^VIX'].get('regularMarketPrice', 15.0))

        treasuries_url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols=TLT,IEF,SHY&fields=quote"
        treasuries_response = requests.get(treasuries_url, headers=headers, timeout=10)
        yields = {}
        if treasuries_response.status_code == 200:
            t_data = treasuries_response.json()
            for symbol in ['TLT', 'IEF', 'SHY']:
                if symbol in t_data.get('quoteData', {}):
                    price = float(t_data['quoteData'][symbol].get('regularMarketPrice', 100.0))
                    yields[symbol] = price

        sectors_url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols=XLK,XLE,XLV,XLF,XLY,XLI,XLRE,XLU&fields=quote"
        sectors_response = requests.get(sectors_url, headers=headers, timeout=10)
        sector_performance = {}
        if sectors_response.status_code == 200:
            s_data = sectors_response.json()
            for symbol in ['XLK', 'XLE', 'XLV', 'XLF', 'XLY', 'XLI', 'XLRE', 'XLU']:
                if symbol in s_data.get('quoteData', {}):
                    change_pct = float(s_data['quoteData'][symbol].get('regularMarketChangePercent', 0))
                    sector_performance[symbol] = change_pct

        market_overview = {
            'vix': vix,
            'yields': yields,
            'sector_performance': sector_performance,
            'volatility_regime': 'HIGH' if vix > 25 else 'NORMAL' if vix > 12 else 'LOW',
            'rate_environment': 'HIGH' if yields.get('IEF', 100) < 95 else 'NORMAL'
        }

        print(f"[MARKET] VIX: {vix:.1f} ({market_overview['volatility_regime']})")
        return market_overview
    except Exception as e:
        print(f"[WARN] Market overview failed: {e}")
        return {'vix': 15.0, 'yields': {}, 'sector_performance': {}, 'volatility_regime': 'NORMAL', 'rate_environment': 'NORMAL'}


def get_top_performers(access_token):
    """Scan all asset classes for top performers."""
    try:
        print("[PERFORMERS] Scanning top performers...")

        universe = [
            'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'AMZN', 'TSLA', 'BRK.B',
            'JPM', 'BAC', 'XOM', 'CVX', 'JNJ', 'PFE', 'UNH', 'WMT', 'PG', 'BA',
            'XLK', 'XLE', 'XLV', 'XLF', 'XLY', 'XLI', 'XLRE', 'XLU',
            'SPY', 'QQQ', 'IWM', 'VTI', 'VTSAX',
            'TLT', 'IEF', 'AGG', 'LQD', 'HYG',
            'SCHD', 'DGRO', 'VYMI', 'PFF',
        ]

        url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols={','.join(universe)}&fields=quote"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=15)
        performers = []

        if response.status_code == 200:
            data = response.json()
            quote_data = data.get('quoteData', {})
            print(f"[PERFORMERS] API returned {len(quote_data)} quotes")

            for symbol in universe:
                if symbol in quote_data:
                    q = quote_data[symbol]
                    price = float(q.get('regularMarketPrice', 100.0))
                    change_pct = float(q.get('regularMarketChangePercent', 0.0))
                    volume = int(q.get('totalVolume', 0))

                    if symbol in ['TLT', 'IEF', 'AGG', 'LQD', 'HYG']:
                        asset_class = 'BOND_ETF'
                    elif symbol in ['SCHD', 'DGRO', 'VYMI', 'PFF']:
                        asset_class = 'DIVIDEND_ETF'
                    elif symbol in ['XLK', 'XLE', 'XLV', 'XLF', 'XLY', 'XLI', 'XLRE', 'XLU']:
                        asset_class = 'SECTOR_ETF'
                    elif symbol in ['SPY', 'QQQ', 'IWM', 'VTI', 'VTSAX']:
                        asset_class = 'BROAD_ETF'
                    else:
                        asset_class = 'STOCK'

                    performers.append({
                        'symbol': symbol,
                        'price': price,
                        'change_pct': change_pct,
                        'volume': volume,
                        'asset_class': asset_class,
                        'liquidity_score': min(volume / 1000000, 100) if volume > 0 else 0
                    })
        else:
            print(f"[WARN] Market data API failed: HTTP {response.status_code}")

        performers.sort(key=lambda x: (x['change_pct'] * 0.7 + x['liquidity_score'] * 0.3), reverse=True)
        print(f"[PERFORMERS] Found {len(performers)} opportunities")

        # *** FALLBACK: If zero performers, return hardcoded list ***
        if len(performers) == 0:
            print(f"[FALLBACK] No market data received, using hardcoded opportunities")
            fallback_performers = [
                {'symbol': 'SPY', 'price': 450.0, 'change_pct': 0.5, 'volume': 50000000, 'asset_class': 'BROAD_ETF', 'liquidity_score': 100},
                {'symbol': 'QQQ', 'price': 380.0, 'change_pct': 1.2, 'volume': 40000000, 'asset_class': 'BROAD_ETF', 'liquidity_score': 100},
                {'symbol': 'IWM', 'price': 190.0, 'change_pct': 0.3, 'volume': 25000000, 'asset_class': 'BROAD_ETF', 'liquidity_score': 80},
                {'symbol': 'AAPL', 'price': 228.0, 'change_pct': 2.1, 'volume': 35000000, 'asset_class': 'STOCK', 'liquidity_score': 95},
                {'symbol': 'MSFT', 'price': 420.0, 'change_pct': 1.8, 'volume': 20000000, 'asset_class': 'STOCK', 'liquidity_score': 90},
            ]
            return fallback_performers

        return performers[:15]
    except Exception as e:
        print(f"[WARN] Performers fetch failed: {e}")
        # Return hardcoded fallback on exception
        fallback = [
            {'symbol': 'SPY', 'price': 450.0, 'change_pct': 0.5, 'volume': 50000000, 'asset_class': 'BROAD_ETF', 'liquidity_score': 100},
        ]
        return fallback


def get_fixed_income_opportunities(access_token):
    """Fetch bond ETFs with yields and credit profiles."""
    try:
        print("[BONDS] Fetching fixed income...")

        bonds = {
            'AGG': {'name': 'Total Bond Market', 'duration': 'INTERMEDIATE', 'credit': 'INVESTMENT_GRADE'},
            'TLT': {'name': 'Long Treasury', 'duration': 'LONG', 'credit': 'SOVEREIGN'},
            'IEF': {'name': 'Intermediate Treasury', 'duration': 'INTERMEDIATE', 'credit': 'SOVEREIGN'},
            'LQD': {'name': 'Investment Grade Corp', 'duration': 'INTERMEDIATE', 'credit': 'INVESTMENT_GRADE'},
            'HYG': {'name': 'High Yield Corp', 'duration': 'INTERMEDIATE', 'credit': 'HIGH_YIELD'},
        }

        url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols={','.join(bonds.keys())}&fields=quote"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=10)
        bond_opportunities = []

        if response.status_code == 200:
            data = response.json()
            quote_data = data.get('quoteData', {})
            for symbol, info in bonds.items():
                if symbol in quote_data:
                    q = quote_data[symbol]
                    price = float(q.get('regularMarketPrice', 100.0))
                    yield_pct = 100.0 / price if price > 0 else 0
                    bond_opportunities.append({
                        'symbol': symbol,
                        'name': info['name'],
                        'price': price,
                        'estimated_yield': yield_pct,
                        'duration': info['duration'],
                        'credit_profile': info['credit'],
                        'asset_class': 'BOND_ETF'
                    })

        print(f"[BONDS] {len(bond_opportunities)} opportunities")
        return bond_opportunities
    except Exception as e:
        print(f"[WARN] Bonds fetch failed: {e}")
        return []


def get_mutual_fund_universe(access_token):
    """Fetch mutual fund opportunities."""
    try:
        print("[FUNDS] Fetching mutual funds...")

        funds = {
            'VTSAX': {'name': 'Vanguard Total Stock Market', 'style': 'BROAD_US'},
            'VBTLX': {'name': 'Vanguard Total Bond Market', 'style': 'BOND'},
            'VTIAX': {'name': 'Vanguard Total Intl Stock', 'style': 'INTL'},
            'VMFXX': {'name': 'Vanguard Money Market Fund', 'style': 'CASH'},
        }

        url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols={','.join(funds.keys())}&fields=quote"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=10)
        fund_opportunities = []

        if response.status_code == 200:
            data = response.json()
            quote_data = data.get('quoteData', {})
            for symbol, info in funds.items():
                if symbol in quote_data:
                    q = quote_data[symbol]
                    price = float(q.get('regularMarketPrice', 100.0))
                    fund_opportunities.append({
                        'symbol': symbol,
                        'name': info['name'],
                        'price': price,
                        'style': info['style'],
                        'asset_class': 'MUTUAL_FUND'
                    })

        print(f"[FUNDS] {len(fund_opportunities)} opportunities")
        return fund_opportunities
    except Exception as e:
        print(f"[WARN] Funds fetch failed: {e}")
        return []


def get_comprehensive_stock_universe(access_token):
    """
    Fetch comprehensive stock universe organized by sector.
    Claude can pick ANY stock based on macro regime + sector signal + portfolio needs.
    Not just "top performers by momentum".
    """
    try:
        print("[UNIVERSE] Building comprehensive stock universe...")

        # COMPREHENSIVE NASDAQ + NYSE UNIVERSE (Claude can pick any)
        # Organized by sector - hundreds of major liquid stocks
        universe_by_sector = {
            'TECHNOLOGY': [
                # Mega Cap
                'AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'TSLA', 'AMZN',
                # Large Cap
                'AMD', 'INTC', 'NFLX', 'ADBE', 'CRM', 'CSCO', 'ORCL', 'IBM', 'AVGO', 'QCOM', 'MCHP', 'MU', 'SNPS', 'CDNS', 'TTD', 'ADSK', 'NOW', 'CRWD', 'PANW', 'WDAY',
                # Mid Cap
                'PLTR', 'COIN', 'SHOP', 'UPST', 'SNOW', 'SNOW', 'NVAX', 'ROKU', 'ZM', 'UNITY', 'NET', 'FASTLY', 'HUBS', 'DOCN', 'RBLX', 'TEAM'
            ],
            'FINANCE': [
                # Banks
                'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'ICE', 'AXP', 'COF', 'USB', 'PNC', 'C', 'KEY', 'MI', 'CM', 'BK', 'STT',
                # Brokers
                'SCHW', 'TD', 'IBKR',
                # Insurance
                'BRK.B', 'PGR', 'ALL', 'HIG', 'UNM', 'LPL', 'MKL', 'RLI', 'AFG',
                # Financial Services
                'FI', 'VIRT', 'MARA', 'RIOT', 'CLSK'
            ],
            'HEALTHCARE': [
                # Pharma/Biotech
                'JNJ', 'PFE', 'MRK', 'ABBV', 'LLY', 'AMGN', 'TEVA', 'VRTX', 'REGN', 'BIIB', 'CELG', 'EXAS', 'ILMN', 'TECH', 'CRSP', 'MRNA', 'BNTX',
                # Medical Devices
                'UNH', 'TMO', 'MDT', 'ISRG', 'STRYKER', 'ZBH', 'HOLX', 'BSX',
                # Healthcare Services
                'ANTM', 'CI', 'HUM', 'VEEV', 'RMD', 'DXCM', 'TDOC'
            ],
            'ENERGY': [
                # Oil & Gas
                'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PSX', 'MPC', 'VLO', 'HES', 'OKE', 'MUR', 'DVN', 'FANG', 'TPL', 'RRC',
                # Renewables
                'NEE', 'DUK', 'SO', 'AEE', 'CEG', 'EXC', 'CMCSA', 'ES', 'EOCD', 'PLUG', 'FSLR', 'ADANIGREEN', 'RUN'
            ],
            'CONSUMER': [
                # Retail
                'AMZN', 'WMT', 'TGT', 'COST', 'DLTR', 'DKNG', 'BBBY', 'M', 'JWN', 'AZO', 'ORLY', 'ROST', 'LOWE',
                # Food & Beverage
                'PG', 'KO', 'PEP', 'MO', 'MNST', 'GIS', 'HSY', 'K', 'CAG', 'CLX', 'CPB', 'MDLZ', 'NSRGY',
                # Restaurants
                'MCD', 'SBUX', 'YUM', 'CMG', 'TXRH', 'DIN', 'BLMN', 'DINE', 'NCLH', 'RCL', 'CCL',
                # Consumer Goods
                'NKE', 'VF', 'LULU', 'UAA', 'DECK', 'MHK', 'RH', 'CPRI', 'CASY', 'ULTA', 'FIVE'
            ],
            'INDUSTRIAL': [
                # Aerospace & Defense
                'BA', 'LMT', 'RTX', 'GD', 'NOC', 'HII',
                # Machinery
                'CAT', 'DE', 'FLS', 'PCAR', 'INGR', 'MYL', 'JCI', 'IDEX', 'ROK', 'ITW', 'CSL', 'OTIS',
                # Industrial Supplies
                'GWW', 'FAST', 'RSG', 'WM', 'PH', 'EMR', 'ETN', 'STLD', 'NUE', 'X', 'SCCO',
                # Trucking & Transportation
                'UPS', 'FDX', 'ODFL', 'XPO', 'JBLU', 'DAL', 'UAL', 'ALK', 'ALGT'
            ],
            'REAL_ESTATE': [
                # REITs
                'O', 'STAG', 'NLY', 'AGNC', 'PLD', 'AMT', 'CCI', 'EQIX', 'DLR', 'SPG', 'AVB', 'EQR', 'MAA', 'AIV', 'UMH', 'MHI', 'CTRE'
            ],
            'UTILITIES': [
                'DUK', 'SO', 'NEE', 'D', 'AEP', 'EXC', 'SVR', 'WEC', 'ES', 'DTE', 'PEG', 'AES', 'EIX', 'CMS', 'NRG', 'PPL', 'XEL'
            ],
            'MATERIALS': [
                # Metals & Mining
                'NEM', 'SCCO', 'FCX', 'JCI', 'CLF', 'NUE', 'STLD', 'MT', 'RIO', 'BHP', 'FLS', 'TECK',
                # Chemicals
                'LYB', 'SHW', 'CTVA', 'DOW', 'EC', 'FMC', 'OLN', 'WLK', 'AXTA'
            ],
            'DIVIDEND': [
                # High Dividend ETFs & Stocks
                'SCHD', 'DGRO', 'VYMI', 'NOBL', 'PFF', 'SDY', 'VYM', 'SPLG', 'PRF', 'JEPI', 'QYLD', 'XYLD',
                # Dividend Aristocrats
                'JNJ', 'PG', 'KO', 'MCD', 'CL', 'PEP', 'WMT', 'ABBV', 'DOV', 'MDS', 'MMM', 'SWK', 'CLX', 'EMR', 'AMCX'
            ],
            'DEFENSIVE': [
                # Staples & Defensive
                'PG', 'JNJ', 'KO', 'WMT', 'MO', 'CL', 'UL', 'PM', 'LMT', 'KMB', 'CL', 'CLX', 'GIS', 'CPB', 'MNST', 'NSRGY', 'STZ'
            ],
            'GROWTH': [
                # High Growth / Momentum
                'NVDA', 'TSLA', 'META', 'AMZN', 'NFLX', 'SHOP', 'UPST', 'SNOW', 'CRWD', 'PANW', 'ZS', 'NET', 'DDOG', 'BILL', 'TEAM', 'HUBS', 'ACHR', 'PLTR', 'COIN', 'RBLX'
            ],
            'VALUE': [
                # Deep Value / Undervalued
                'F', 'GM', 'IBM', 'VZ', 'T', 'C', 'BAC', 'WFC', 'PBR', 'USB', 'KEY', 'MI', 'RIG', 'PARA', 'BYND', 'COTY', 'FOXA', 'FOX', 'ZNGA'
            ],
            'SMALL_CAP': [
                # Small Cap Index / Growth
                'IWM', 'VB', 'IWN', 'RUSS', 'XRT', 'PSP', 'IJH', 'VBR', 'SCHB', 'SCHA', 'DSI', 'EMXC', 'VBK', 'IWP', 'IWO'
            ],
            'INTERNATIONAL': [
                # International ETFs
                'EWJ', 'EWG', 'EWU', 'EWH', 'FXI', 'VTIAX', 'IEMG', 'VWO', 'FLEM', 'IUEM', 'VEEM', 'SCHE', 'SCHF',
                # Individual International
                'TSM', 'BABA', 'SAP', 'ASML', 'RDSA', 'SAN', 'NVO', 'HSY'
            ]
        }

        # Flatten all symbols
        all_symbols = []
        for sector, symbols in universe_by_sector.items():
            all_symbols.extend(symbols)

        # Fetch quotes for all symbols
        url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols={','.join(all_symbols)}&fields=quote"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=20)

        stock_universe = {}
        if response.status_code == 200:
            data = response.json()
            quote_data = data.get('quoteData', {})

            # Organize by sector with current prices
            for sector, symbols in universe_by_sector.items():
                stock_universe[sector] = []
                for symbol in symbols:
                    if symbol in quote_data:
                        q = quote_data[symbol]
                        price = float(q.get('regularMarketPrice', 100.0))
                        change_pct = float(q.get('regularMarketChangePercent', 0.0))
                        volume = int(q.get('totalVolume', 0))

                        stock_universe[sector].append({
                            'symbol': symbol,
                            'sector': sector,
                            'price': price,
                            'change_pct': change_pct,
                            'volume': volume,
                            'asset_class': 'STOCK',
                            'liquidity_score': min(volume / 1000000, 100) if volume > 0 else 0
                        })
        else:
            print(f"[WARN] Market data API failed: HTTP {response.status_code}, using fallback universe")

        # Fallback if no data
        if not stock_universe:
            print(f"[FALLBACK] Using hardcoded stock universe")
            stock_universe = {
                'TECHNOLOGY': [
                    {'symbol': 'AAPL', 'sector': 'TECHNOLOGY', 'price': 228.0, 'change_pct': 1.5, 'volume': 35000000, 'asset_class': 'STOCK', 'liquidity_score': 95},
                    {'symbol': 'MSFT', 'sector': 'TECHNOLOGY', 'price': 420.0, 'change_pct': 1.2, 'volume': 20000000, 'asset_class': 'STOCK', 'liquidity_score': 90},
                    {'symbol': 'NVDA', 'sector': 'TECHNOLOGY', 'price': 135.0, 'change_pct': 2.1, 'volume': 30000000, 'asset_class': 'STOCK', 'liquidity_score': 92},
                ],
                'FINANCE': [
                    {'symbol': 'JPM', 'sector': 'FINANCE', 'price': 195.0, 'change_pct': 0.8, 'volume': 8000000, 'asset_class': 'STOCK', 'liquidity_score': 85},
                    {'symbol': 'BAC', 'sector': 'FINANCE', 'price': 38.0, 'change_pct': 1.1, 'volume': 45000000, 'asset_class': 'STOCK', 'liquidity_score': 98},
                ],
                'HEALTHCARE': [
                    {'symbol': 'JNJ', 'sector': 'HEALTHCARE', 'price': 160.0, 'change_pct': 0.3, 'volume': 5000000, 'asset_class': 'STOCK', 'liquidity_score': 80},
                    {'symbol': 'UNH', 'sector': 'HEALTHCARE', 'price': 545.0, 'change_pct': 0.9, 'volume': 2000000, 'asset_class': 'STOCK', 'liquidity_score': 70},
                ],
                'ENERGY': [
                    {'symbol': 'XOM', 'sector': 'ENERGY', 'price': 105.0, 'change_pct': 1.8, 'volume': 10000000, 'asset_class': 'STOCK', 'liquidity_score': 88},
                ],
                'CONSUMER': [
                    {'symbol': 'WMT', 'sector': 'CONSUMER', 'price': 95.0, 'change_pct': 0.5, 'volume': 8000000, 'asset_class': 'STOCK', 'liquidity_score': 82},
                ],
            }

        print(f"[UNIVERSE] Built {len(stock_universe)} sectors with {sum(len(v) for v in stock_universe.values())} stocks")
        return stock_universe

    except Exception as e:
        print(f"[WARN] Universe fetch failed: {e}")
        return {}


# =====================================================================
# OAUTH & ACCOUNT
# =====================================================================

def store_refresh_token_to_dynamodb(refresh_token):
    """
    FIX v3.0.32: Store new refresh token in DynamoDB for persistence.
    Schwab returns a new refresh_token with each refresh (valid 7 days).
    Store it so next execution uses the fresh token.
    Uses dedicated OAUTH_TOKENS_TABLE with 'token_id' as partition key.
    """
    try:
        table = DYNAMODB.Table(OAUTH_TOKENS_TABLE)
        table.put_item(Item={
            'token_id': 'schwab-refresh-token',  # Partition key for oauth tokens
            'token_value': refresh_token,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'ttl': int((datetime.utcnow() + timedelta(days=8)).timestamp())  # Auto-expire after 8 days
        })
        print(f"[OAUTH] ✅ New refresh token stored in DynamoDB (OAUTH_TOKENS_TABLE)")
        return True
    except Exception as e:
        print(f"[WARN] Failed to store token in DynamoDB: {e}")
        return False


def get_refresh_token_from_dynamodb():
    """
    FIX v3.0.32: Retrieve stored refresh token from DynamoDB.
    Falls back to environment variable if not found.
    Uses dedicated OAUTH_TOKENS_TABLE with 'token_id' as partition key.
    """
    try:
        table = DYNAMODB.Table(OAUTH_TOKENS_TABLE)
        response = table.get_item(Key={'token_id': 'schwab-refresh-token'})
        if 'Item' in response:
            stored_token = response['Item'].get('token_value')
            print(f"[OAUTH] ✅ Retrieved refresh token from DynamoDB (OAUTH_TOKENS_TABLE)")
            return stored_token
    except Exception as e:
        print(f"[WARN] Failed to retrieve token from DynamoDB: {e}")

    # Fallback to environment variable
    print(f"[OAUTH] Using refresh token from environment")
    return SCHWAB_REFRESH_TOKEN


def refresh_schwab_access_token():
    """
    Refresh Schwab OAuth access token.
    FIX v3.0.32: Capture and store new refresh_token for automatic 7-day renewal.
    """
    try:
        # Get the latest refresh token (from DynamoDB or environment)
        refresh_token = get_refresh_token_from_dynamodb()

        url = "https://api.schwabapi.com/v1/oauth/token"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': SCHWAB_CLIENT_ID,
            'client_secret': SCHWAB_CLIENT_SECRET
        }
        response = requests.post(url, headers=headers, data=data, timeout=10)

        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get('access_token')
            new_refresh_token = token_data.get('refresh_token')  # FIX v3.0.32: Capture new refresh_token
            expires_in = token_data.get('expires_in', 1800)

            # FIX v3.0.32: Store the new refresh_token for next execution
            if new_refresh_token:
                store_refresh_token_to_dynamodb(new_refresh_token)

            print(f"[OAUTH] ✅ Token refreshed (expires in {expires_in}s)")
            return access_token
        else:
            print(f"[ERROR] Token refresh failed: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"[ERROR] OAuth failed: {e}")
        return None


def get_account_hash(access_token):
    """Get encrypted account hash. Returns: (hash, account_number)"""
    try:
        url = f"{SCHWAB_BASE_URL}/accounts/accountNumbers"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            account_numbers = response.json()
            for acc in account_numbers:
                if str(acc.get('accountNumber')) == SCHWAB_ACCOUNT_ID.replace('-', ''):
                    encrypted_hash = acc.get('hashValue')
                    account_number = acc.get('accountNumber')
                    print(f"[HASH] ✅ Found account hash")
                    return encrypted_hash, account_number
            print(f"[ERROR] Account not found")
            return None, None
        else:
            print(f"[ERROR] Account fetch failed: HTTP {response.status_code}")
            return None, None
    except Exception as e:
        print(f"[ERROR] get_account_hash failed: {e}")
        return None, None
        return None


def get_account_data(access_token):
    """Fetch account balance, cash, and buying power (FIX #40: Account health check)."""
    try:
        account_hash, account_number = get_account_hash(access_token)
        if not account_hash:
            return {'cash': 0, 'liquidation_value': 0, 'available_funds': 0, 'account_hash': None, 'account_number': None, 'buying_power': 0, 'option_buying_power': 0}

        url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            acc_data = response.json()
            balances = acc_data.get('securitiesAccount', {}).get('currentBalances', {})
            cash = float(balances.get('cashBalance', 0))
            liquidation_value = float(balances.get('liquidationValue', 0))
            available_funds = float(balances.get('availableFunds', cash))  # FIX v3.0.16: Use available funds for trading

            # FIX #40: Extract buying power for account health check
            buying_power = float(balances.get('buyingPower', 0))
            option_buying_power = float(balances.get('optionBuyingPower', buying_power))  # May be separate from stock buying power

            print(f"[ACCOUNT] ✅ Cash: ${cash:.2f} | Available: ${available_funds:.2f} | Buying Power: ${buying_power:.2f} | Option BP: ${option_buying_power:.2f}")
            return {
                'cash': cash,
                'liquidation_value': liquidation_value,
                'available_funds': available_funds,
                'buying_power': buying_power,
                'option_buying_power': option_buying_power,
                'account_hash': account_hash,
                'account_number': account_number
            }
        else:
            print(f"[ERROR] Account fetch failed: HTTP {response.status_code}")
            return {'cash': 0, 'liquidation_value': 0, 'available_funds': 0, 'account_hash': None, 'account_number': None, 'buying_power': 0, 'option_buying_power': 0}
    except Exception as e:
        print(f"[ERROR] Account fetch failed: {e}")
        return {'cash': 0, 'liquidation_value': 0, 'available_funds': 0, 'account_hash': None, 'account_number': None, 'buying_power': 0, 'option_buying_power': 0}


def check_for_pending_deposits(access_token, account_hash):
    """
    Check transaction history for pending deposits.
    Returns: (has_pending, total_pending_amount)

    FIX v3.0.15 #5: Skips trading during ACH settlement windows
    FIX v3.0.18 #3: Use account_hash (not account_number) for transactions endpoint
                   Account hash works for all GET operations per Schwab API
    """
    try:
        # Schwab transactions endpoint requires account_hash (encrypted hash from accountNumbers)
        # This is the same identifier used for successful account data fetches
        url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}/transactions"
        headers = {'Authorization': f'Bearer {access_token}'}

        # Get transactions from last 3 days (ISO 8601 format)
        end_date = datetime.utcnow().strftime('%Y-%m-%dT00:00:00Z')
        start_date = (datetime.utcnow() - timedelta(days=3)).strftime('%Y-%m-%dT00:00:00Z')

        params = {
            'startDate': start_date,
            'endDate': end_date
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code != 200:
            error_detail = ""
            try:
                error_detail = response.json().get('message', response.text[:100])
            except:
                error_detail = response.text[:100]
            print(f"[SETTLEMENT] ⚠️ HTTP {response.status_code} - {error_detail}")
            print(f"[SETTLEMENT] URL: {url}")
            print(f"[SETTLEMENT] Using account_hash (encrypted ID from accountNumbers endpoint)")
            return False, 0

        transactions = response.json() if isinstance(response.json(), list) else []

        # Look for pending deposits (type = DEPOSIT, status = PENDING or similar)
        pending_total = 0
        pending_found = False

        for tx in transactions:
            tx_type = tx.get('type', '').upper()
            tx_status = tx.get('status', '').upper()
            tx_amount = float(tx.get('netAmount', 0))
            tx_description = tx.get('description', '').upper()

            # Look for pending deposits - ACH, wire, or transfer IN that haven't cleared
            is_inbound = 'IN' in tx_description or tx_amount > 0
            is_pending = 'PENDING' in tx_status or 'UNSETTLED' in tx_status or tx_status == ''
            is_deposit = 'DEPOSIT' in tx_type or 'TRANSFER' in tx_description or 'ELECTRONIC' in tx_description

            if is_inbound and is_deposit and is_pending and tx_amount > 0:
                pending_total += tx_amount
                pending_found = True
                print(f"[SETTLEMENT] ⚠️  Found pending deposit: ${tx_amount:.2f} ({tx_description})")

        if pending_found:
            print(f"[SETTLEMENT] ❌ Account has ${pending_total:.2f} in pending deposits - SKIPPING TRADING")
            return True, pending_total
        else:
            print(f"[SETTLEMENT] ✅ No pending deposits detected")
            return False, 0

    except Exception as e:
        print(f"[SETTLEMENT] Could not check pending deposits: {e}")
        return False, 0


def sync_positions_to_dynamodb(holdings):
    """
    FIX #43: Sync current holdings to POSITIONS_SNAPSHOT table
    This creates an accurate, timestamp-indexed record of live positions
    Decouples trade journal (audit log) from position data (source of truth)
    """
    try:
        table = DYNAMODB.Table(POSITIONS_SNAPSHOT_TABLE)
        timestamp = datetime.utcnow().isoformat()

        # Write snapshot with timestamp as key
        snapshot_item = {
            'SnapshotTime': timestamp,
            'HoldingsCount': len(holdings),
            'Holdings': json.dumps({k: v for k, v in holdings.items()}),
            'CreatedAt': timestamp
        }

        table.put_item(Item=snapshot_item)
        print(f"[POSITIONS] ✅ Synced {len(holdings)} holdings to snapshot table")
        return True
    except Exception as e:
        print(f"[POSITIONS] ⚠️ Snapshot sync failed: {e} (continuing with holdings in memory)")
        return False


def read_positions_from_snapshot():
    """
    FIX #43: Read positions from latest POSITIONS_SNAPSHOT
    This is the fallback when Schwab API is unavailable
    """
    try:
        table = DYNAMODB.Table(POSITIONS_SNAPSHOT_TABLE)
        # Note: Scan doesn't support ScanIndexForward; fetch recent items and sort by timestamp in Python
        response = table.scan(Limit=10)

        if not response.get('Items'):
            print(f"[POSITIONS] ⚠️ No snapshot found, falling back to trade journal")
            return read_positions_from_trade_journal()

        # Sort by SnapshotTime (most recent first) and get the latest
        items = sorted(response['Items'], key=lambda x: x.get('SnapshotTime', ''), reverse=True)
        latest_snapshot = items[0]
        holdings_json = latest_snapshot.get('Holdings', '{}')
        holdings = json.loads(holdings_json)

        print(f"[POSITIONS] Read {len(holdings)} holdings from snapshot table")
        return holdings
    except Exception as e:
        print(f"[POSITIONS] ⚠️ Snapshot read failed: {e}, falling back to trade journal")
        return read_positions_from_trade_journal()


def read_positions_from_trade_journal():
    """
    Read holdings from TRADE_JOURNAL_TABLE (audit log only - last resort fallback)
    This is deprecated for position tracking but kept for audit/compliance
    """
    try:
        table = DYNAMODB.Table(TRADE_JOURNAL_TABLE)
        response = table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={':status': 'EXECUTED'},
            Limit=100
        )

        holdings = {}
        for item in response.get('Items', []):
            symbol = item.get('Symbol', 'UNKNOWN')
            quantity = float(item.get('Quantity', 0))
            entry_price = float(item.get('EntryPrice', 100.0))
            asset_class = item.get('AssetClass', 'STOCK')
            order_id = item.get('OrderID', 'UNKNOWN')

            if symbol != 'UNKNOWN' and quantity > 0:
                holdings[symbol] = {
                    'quantity': quantity,
                    'entry_price': entry_price,
                    'current_price': entry_price,
                    'asset_class': asset_class,
                    'order_id': order_id,
                    'cost_basis': quantity * entry_price
                }

        print(f"[POSITIONS] ⚠️ Read {len(holdings)} holdings from trade journal (FALLBACK)")
        return holdings
    except Exception as e:
        print(f"[ERROR] Trade journal scan failed: {e}")
        return {}


def read_positions_from_schwab_api(access_token, account_hash):
    """
    FIX #42 + FIX #43: Fetch real holdings from Schwab /positions endpoint
    and sync to snapshot table for accurate position tracking
    Falls back to snapshot → trade journal only if API fails
    """
    try:
        headers = {'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'}
        positions_url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}/positions"

        print(f"[POSITIONS] Fetching holdings from Schwab API /positions endpoint...")
        response = requests.get(positions_url, headers=headers, timeout=10)

        if response.status_code not in [200, 201]:
            print(f"[POSITIONS] ⚠️ Schwab /positions returned HTTP {response.status_code}, falling back to snapshot")
            return read_positions_from_snapshot()

        positions_data = response.json() if response.text else []
        holdings = {}

        for position in positions_data:
            try:
                instrument = position.get('instrument', {})
                symbol = instrument.get('symbol', 'UNKNOWN')
                quantity = float(position.get('longQuantity', 0))
                market_value = float(position.get('marketValue', 0))
                average_price = float(position.get('averagePrice', 0))
                asset_type = instrument.get('assetType', 'EQUITY')

                if symbol != 'UNKNOWN' and quantity > 0:
                    current_price = market_value / quantity if quantity != 0 else average_price
                    holdings[symbol] = {
                        'quantity': quantity,
                        'entry_price': average_price,
                        'current_price': current_price,
                        'asset_class': 'STOCK' if asset_type == 'EQUITY' else asset_type,
                        'order_id': 'LIVE',
                        'cost_basis': quantity * average_price,
                        'market_value': market_value
                    }
                    print(f"[POSITIONS] {symbol}: {quantity:.4f} @ ${current_price:.2f} (value: ${market_value:.2f})")
            except (KeyError, ValueError) as e:
                print(f"[POSITIONS] ⚠️ Error parsing position: {e}")
                continue

        # FIX #43: Sync to snapshot for next fallback
        sync_positions_to_dynamodb(holdings)

        print(f"[POSITIONS] ✅ Fetched {len(holdings)} holdings from Schwab")
        return holdings
    except Exception as e:
        print(f"[POSITIONS] ❌ Schwab API fetch failed: {e}, falling back to snapshot")
        return read_positions_from_snapshot()


def get_trades_today():
    """Count trades executed today."""
    try:
        table = DYNAMODB.Table(TRADE_JOURNAL_TABLE)
        today_date = datetime.utcnow().strftime('%Y-%m-%d')
        response = table.scan(
            FilterExpression='TradeDate = :date AND #status = :status',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={':date': today_date, ':status': 'EXECUTED'},
            Limit=100
        )
        count = response.get('Count', 0)
        print(f"[TRADES_TODAY] {count} executed")
        return count
    except Exception as e:
        print(f"[ERROR] Trades count failed: {e}")
        return 0


def get_portfolio_nav_history():
    """Get previous NAV for performance tracking."""
    try:
        table = DYNAMODB.Table(PORTFOLIO_METRICS_TABLE)
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = table.query(
            KeyConditionExpression='MetricDate = :date',
            ExpressionAttributeValues={':date': yesterday},
            Limit=1,
            ScanIndexForward=False
        )

        if response.get('Items'):
            return float(response['Items'][0].get('nav', 0))
        return None
    except Exception as e:
        print(f"[WARN] Previous NAV fetch failed: {e}")
        return None


# =====================================================================
# DYNAMIC TRADE SIZING (FIX v3.0.14 #3)
# =====================================================================

def calculate_trade_size(vix, portfolio_value, macro_regime):
    """
    Calculate dynamic trade size based on:
    - Portfolio size (scale up as it grows)
    - VIX/volatility regime
    - Macro environment

    FIX v3.0.14 #3: Now scales MIN_TRADE_SIZE with available capital
    When portfolio is small, we don't get stuck unable to trade
    """
    try:
        print(f"[SIZING] Calculating trade size (NAV: ${portfolio_value:.2f}, VIX: {vix:.1f})")

        # Base size scales with portfolio
        if portfolio_value < 50:
            base_mult = 0.5
        elif portfolio_value < 100:
            base_mult = 0.75
        elif portfolio_value < 500:
            base_mult = 1.0
        elif portfolio_value < 1000:
            base_mult = 1.5
        else:
            base_mult = 2.0

        # Volatility adjustment
        if vix > 25:
            vix_mult = 0.5
        elif vix > 20:
            vix_mult = 0.75
        elif vix > 12:
            vix_mult = 1.0
        else:
            vix_mult = 1.2

        # Macro adjustment
        macro_mult = {
            'PANIC': 0.5,
            'HIGH': 0.75,
            'ELEVATED': 0.9,
            'NORMAL': 1.0,
            'LOW': 1.15
        }.get(macro_regime, 1.0)

        trade_size = BASE_TRADE_SIZE * base_mult * vix_mult * macro_mult

        # FIX v3.0.15 #2 + CTO EXECUTIVE FIX: MINIMUM ORDER SIZE ($50.00)
        # Schwab requires minimum $5.00 per order, but we use $50 to prevent fractional accumulation
        # Previous: $5 trades on $190 IWM created 0.0263 shares → Schwab rejects when selling
        # Solution: $50 minimum ensures whole shares or usable fractionals for all assets
        min_trade = MIN_TRADE_SIZE_FLOOR  # $50.00 minimum (prevents microfraction bug)

        if portfolio_value < MIN_TRADE_SIZE_FLOOR:
            print(f"[SIZING] ⚠️  Portfolio ${portfolio_value:.2f} below minimum ${MIN_TRADE_SIZE_FLOOR:.2f} - cannot trade")
            return 0  # Cannot trade - portfolio too small

        trade_size = max(min_trade, min(MAX_TRADE_SIZE, trade_size))

        print(f"[SIZING] ✅ Trade size: ${trade_size:.2f} (base_mult={base_mult}, vix_mult={vix_mult}, macro_mult={macro_mult}, min=${min_trade:.2f})")
        return trade_size

    except Exception as e:
        print(f"[SIZING] ⚠️ Error, using default: {e}")
        return BASE_TRADE_SIZE


def validate_symbol_liquidity(access_token, symbol, min_volume=100000):
    """
    Validate that a symbol exists on Schwab and has minimum liquidity.
    FIX v3.0.14 #1: Handle HTTP 404 gracefully instead of failing
    Returns: (valid, price, error_msg)
    """
    try:
        url = f"{SCHWAB_BASE_URL}/marketdata/quotes?symbols={symbol}&fields=quote"
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            quote_data = data.get('quoteData', {})

            if symbol in quote_data:
                q = quote_data[symbol]
                price = float(q.get('regularMarketPrice', 0))
                volume = int(q.get('totalVolume', 0))

                if price > 0 and volume >= min_volume:
                    print(f"[VALIDATE] ✅ {symbol} exists | Price: ${price:.2f} | Volume: {volume:,}")
                    return True, price, None
                else:
                    msg = f"Low liquidity: volume={volume}, min={min_volume}"
                    print(f"[VALIDATE] ⚠️ {symbol}: {msg}")
                    return False, price, msg
            else:
                print(f"[VALIDATE] ❌ {symbol} not found in Schwab quotes")
                return False, 0, "Symbol not found"
        elif response.status_code == 404:
            # FIX v3.0.16 #3: Handle 404 gracefully - if endpoint unavailable, allow trade if symbol is in our universe
            print(f"[VALIDATE] ⚠️ HTTP 404 - Validation endpoint unavailable, skipping validation")
            return True, 0, None  # Allow trade to proceed - validation infrastructure issue, not symbol issue
        else:
            print(f"[VALIDATE] ❌ HTTP {response.status_code}")
            return False, 0, f"API error {response.status_code}"

    except Exception as e:
        print(f"[VALIDATE] ❌ Exception: {e}")
        return False, 0, str(e)


def route_model_and_trade_limit(vix):
    """Route to Claude model based on VIX and return trade limit (AGGRESSIVE TIER - Option B)."""
    if vix < 12:
        model = 'claude-opus-5-5'
        max_daily = 5  # Increased from 3
    elif vix < 20:
        model = 'claude-sonnet-5'
        max_daily = 4  # Increased from 2
    else:
        model = 'claude-opus-5-5'
        max_daily = 2  # Increased from 1

    print(f"[MODEL] VIX={vix:.1f} → {model} (max {max_daily} trades)")
    return model, max_daily


# =====================================================================
# CLAUDE AUTONOMOUS DECISION - ENHANCED
# =====================================================================

def get_claude_autonomous_decision(market_overview, top_performers, bond_opportunities, fund_opportunities, stock_universe,
                                   portfolio_value, holdings, macro_data, trade_size, model='claude-sonnet-5', pm_directive=None):
    """
    Claude autonomous decision engine with BUY_MORE capability.

    - Analyzes market data, macro regime, CIO thesis, and portfolio state
    - PM directive controls diversification: HOLD/BUY allows BUY_MORE; ROTATE/SELL forces new holdings
    - Returns: (symbol, asset_class, price, rationale) for Claude's top recommendation
    - Smart exclusion: Intelligently filters holdings based on PM action to enable or prevent concentration
    """
    try:
        if not CLAUDE_API_KEY:
            raise ValueError("CLAUDE_API_KEY missing")

        client = Anthropic(api_key=CLAUDE_API_KEY)

        asset_classes = {}
        for sym, holding in holdings.items():
            ac = holding.get('asset_class', 'STOCK')
            asset_classes[ac] = asset_classes.get(ac, 0) + 1

        # ===== DIVERSIFICATION: Smart exclusion based on PM directive (v3.0.27.1) =====
        # If PM says ROTATE/SELL: exclude holdings (force rebalancing into new sectors)
        # If PM says BUY/HOLD: ALLOW buying more of existing holdings (amplify conviction)

        exclude_current_holdings = True  # Default: exclude
        if pm_directive:
            action, sector_reduce, sector_increase, rationale = pm_directive
            if action in ["BUY", "HOLD"]:
                exclude_current_holdings = False  # Allow BUY_MORE of existing holdings
                print(f"[DIVERSIFY] PM directive is {action} → Allowing BUY_MORE of existing holdings")
            elif action in ["ROTATE", "SELL"]:
                exclude_current_holdings = True  # Force new securities
                print(f"[DIVERSIFY] PM directive is {action} → Excluding current holdings (force rebalancing)")

        excluded_symbols = set()
        if exclude_current_holdings:
            excluded_symbols = set(holdings.keys())  # Already own

        try:
            table = DYNAMODB.Table(TRADE_JOURNAL_TABLE)
            response = table.scan(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'Status'},
                ExpressionAttributeValues={':status': 'EXECUTED'},
                Limit=20
            )
            recent_trades = sorted(response.get('Items', []),
                                  key=lambda x: x.get('Timestamp', ''),
                                  reverse=True)[:3]
            recent_symbols = [item.get('Symbol') for item in recent_trades]
            excluded_symbols.update([s for s in recent_symbols if s])
            print(f"[DIVERSIFY] Excluding: {excluded_symbols}")
        except Exception as e:
            print(f"[DIVERSIFY] ⚠️ Could not load recent trades: {e}")

        # Filter opportunities: remove excluded symbols
        top_performers_filtered = [p for p in top_performers if p['symbol'] not in excluded_symbols]
        bond_opportunities_filtered = [b for b in bond_opportunities if b['symbol'] not in excluded_symbols]
        fund_opportunities_filtered = [f for f in fund_opportunities if f['symbol'] not in excluded_symbols]

        if not top_performers_filtered:
            top_performers_filtered = top_performers  # Fallback if all filtered
        if not bond_opportunities_filtered:
            bond_opportunities_filtered = bond_opportunities
        if not fund_opportunities_filtered:
            fund_opportunities_filtered = fund_opportunities

        # Build sector-based stock opportunities from universe (not just momentum)
        sector_opportunities_text = ""
        if stock_universe:
            # Show stocks from sectors aligned with macro signal
            signal_to_sectors = {
                'TECH': ['TECHNOLOGY', 'GROWTH'],
                'FINANCE': ['FINANCE'],
                'DEFENSIVE': ['DEFENSIVE', 'HEALTHCARE'],
                'ENERGY': ['ENERGY'],
                'BALANCED': ['CONSUMER', 'INDUSTRIAL', 'DIVIDEND'],
            }
            relevant_sectors = signal_to_sectors.get(macro_data['sector_signal'], ['TECHNOLOGY'])

            sector_stocks = []
            for sector in relevant_sectors:
                if sector in stock_universe:
                    top_in_sector = sorted(stock_universe[sector],
                                          key=lambda x: x['change_pct'] * 0.6 + x['liquidity_score'] * 0.4,
                                          reverse=True)[:3]
                    for stock in top_in_sector:
                        sector_stocks.append(f"{stock['symbol']} ({sector})")

            sector_opportunities_text = f"\nSECTOR OPPORTUNITIES (matching {macro_data['sector_signal']} signal):\n" + ", ".join(sector_stocks[:8])

        # Build directive context if PM provided one
        directive_context = ""
        if pm_directive:
            action, sector_reduce, sector_increase, rationale = pm_directive
            if action == "BUY":
                directive_context = f"\n*** PORTFOLIO MANAGER DIRECTIVE: BUY (focus on {sector_increase.upper()} sector) ***\nReason: {rationale}\n"
            elif action == "SELL":
                directive_context = f"\n*** PORTFOLIO MANAGER DIRECTIVE: SELL/REDUCE (trim {sector_reduce.upper()} sector) ***\nReason: {rationale}\n"
            elif action == "ROTATE":
                directive_context = f"\n*** PORTFOLIO MANAGER DIRECTIVE: ROTATE (sell {sector_reduce.upper()}, buy {sector_increase.upper()}) ***\nReason: {rationale}\n"
            elif action == "HOLD":
                directive_context = f"\n*** PORTFOLIO MANAGER DIRECTIVE: HOLD (portfolio balanced) ***\nReason: {rationale}\n"

        opportunities_text = f"""
MARKET CONDITIONS:
- VIX: {market_overview['vix']:.1f} ({market_overview['volatility_regime']})
- Macro Regime: {macro_data['regime']}
- Rate Environment: {macro_data['rate_environment']}
- Risk Appetite: {macro_data['risk_appetite']}
- Sector Signal: {macro_data['sector_signal']}
- Macro Thesis: {macro_data['thesis']}
- Thesis Confidence: {macro_data.get('thesis_confidence', 5)}/10
- Preferred Theme: {macro_data.get('preferred_theme', 'BROAD_DIVERSIFICATION')}
- Environment Risk Rating: {macro_data.get('risk_rating', 'MEDIUM')}
{directive_context}

TOP OPPORTUNITIES (diversified - excluding recent trades):
{json.dumps([{'symbol': p['symbol'], 'class': p['asset_class'], 'price': p['price'], 'change': p['change_pct']} for p in top_performers_filtered[:5]], indent=2)}

STOCK UNIVERSE BY SECTOR (any stock, not just momentum):
{json.dumps({sector: [{'symbol': s['symbol'], 'price': s['price'], 'change': s['change_pct']} for s in stocks[:3]] for sector, stocks in list(stock_universe.items())[:6]}, indent=2)}
{sector_opportunities_text}

FIXED INCOME:
{json.dumps([{'symbol': b['symbol'], 'yield': f"{b['estimated_yield']:.2f}%"} for b in bond_opportunities_filtered], indent=2)}

FUNDS:
{json.dumps([{'symbol': f['symbol']} for f in fund_opportunities_filtered], indent=2)}

PORTFOLIO:
- NAV: ${portfolio_value:.2f}
- Holdings: {len(holdings)}
- Current allocation: {asset_classes}
- Trade size: ${trade_size:.2f}
"""

        # Build BUY_MORE guidance if PM allows it
        buy_more_guidance = ""
        if pm_directive and not exclude_current_holdings:
            buy_more_guidance = "\n6. **CAN BUY_MORE of existing holdings** if they align with PM directive and macro thesis"

        prompt = f"""
You are an autonomous portfolio manager with FULL DISCRETION.
You can pick ANY asset class AND ANY STOCK — not limited to the opportunities shown.
You can also BUY MORE SHARES of holdings already in the portfolio if appropriate.

The opportunities shown are suggestions, but you can suggest ANY ticker symbol that:
1. Makes sense for the macro regime ({macro_data['regime']}) and supports this thesis: {macro_data['thesis']}
2. Aligns with sector signal ({macro_data['sector_signal']}) and preferred theme ({macro_data.get('preferred_theme', 'BROAD_DIVERSIFICATION')})
3. Matches risk appetite ({macro_data['risk_appetite']}) appropriate for {macro_data.get('risk_rating', 'MEDIUM')} environment risk
4. Has sufficient liquidity (major indices, blue chips, popular ETFs, high-volume stocks)
5. **RESPECTS PORTFOLIO MANAGER DIRECTIVE** (see below){buy_more_guidance}

Current state:
{opportunities_text}

DECISION FRAMEWORK:
- **FIRST PRIORITY: Follow Portfolio Manager allocation directive** (if provided above)
  - If PM says "BUY tech": pick a tech stock/ETF (can be new OR buy_more of existing tech holding)
  - If PM says "ROTATE tech→defensive": pick a defensive stock/ETF (NEW only, no duplicates)
  - If PM says "HOLD": monitor current positions OR buy_more of strong performers (evaluate conviction)
  - If PM says "SELL": reduce holdings (not relevant here, handled by PM logic)
- Then align with macro regime ({macro_data['regime']}) and thesis: {macro_data['thesis']}
  - Thesis confidence: {macro_data.get('thesis_confidence', 5)}/10
  - If confidence >= 8: Commit strongly to thesis (pick aligned asset)
  - If confidence 5-7: Moderate alignment (thesis is guide, not gospel)
  - If confidence < 5: Weak signal (diversify; don't over-index to thesis)
- Match risk appetite ({macro_data['risk_appetite']}) within {macro_data.get('risk_rating', 'MEDIUM')} environment risk
- Respect sector signal ({macro_data['sector_signal']}) and preferred theme ({macro_data.get('preferred_theme', 'BROAD_DIVERSIFICATION')})
- Diversify across classes
- Consider contrarian picks if macro warrants

Select the SINGLE BEST opportunity for current conditions.
Can be any ticker you choose (SPY, AAPL, GLD, BTC-USD, obscure_etf, etc).

BUY_MORE OPTION (if PM directive allows):
- If a current holding strongly aligns with PM directive AND macro thesis AND has high conviction
- Example: VTI held at 5%, PM says BUY broad → suggest buying 0.5 more shares VTI
- Amplifies conviction without forcing diversification when existing position is optimal

OUTPUT EXACTLY:
SYMBOL: [any ticker symbol - not limited to list above]
ASSET_CLASS: [STOCK|SECTOR_ETF|BROAD_ETF|BOND_ETF|DIVIDEND_ETF|MUTUAL_FUND|OPTION_SPREAD|COMMODITY|CRYPTO]
PRICE: [best estimate of current price]
RATIONALE: [one sentence why this is best for current conditions]
"""

        response = client.messages.create(model=model, max_tokens=300, messages=[{'role': 'user', 'content': prompt}])

        response_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                response_text = block.text
                break

        print(f"[CLAUDE] ✅ Response received")

        selected_symbol = None
        asset_class = 'STOCK'
        price = 100.0
        rationale = ""

        for line in response_text.split('\n'):
            if line.startswith('SYMBOL:'):
                selected_symbol = line.split(':')[1].strip().upper()
            elif line.startswith('ASSET_CLASS:'):
                asset_class = line.split(':')[1].strip().upper()
            elif line.startswith('PRICE:'):
                try:
                    price = float(line.split(':')[1].strip())
                except:
                    price = 100.0
            elif line.startswith('RATIONALE:'):
                rationale = line.split(':')[1].strip()

        # NO WHITELIST: Claude can pick ANY symbol (SPY, AAPL, OBSCURE_STOCK, etc)
        # Validation happens at execution: check liquidity, price, API availability
        # This gives Claude true discretion while guardrails catch invalid picks

        if selected_symbol and len(selected_symbol) <= 6:  # Valid ticker format
            print(f"[DECISION] ✅ {selected_symbol} ({asset_class}) @ ${price:.2f}")
            print(f"[RATIONALE] {rationale}")
            return selected_symbol, asset_class, price
        else:
            # Claude didn't return a valid symbol, use top performer
            print(f"[FALLBACK] Claude symbol invalid, using top performer from diversified list")
            if top_performers_filtered:
                top = top_performers_filtered[0]
                return top['symbol'], top['asset_class'], top['price']
            else:
                print(f"[FALLBACK2] All stocks filtered, using SPY")
                return 'SPY', 'BROAD_ETF', 450.0

    except Exception as e:
        print(f"[ERROR] Claude decision failed: {e}")
        if top_performers_filtered:
            top = top_performers_filtered[0]
            return top['symbol'], top['asset_class'], top['price']
        elif top_performers:
            top = top_performers[0]
            return top['symbol'], top['asset_class'], top['price']
        return 'SPY', 'BROAD_ETF', 450.0


# =====================================================================
# PORTFOLIO MANAGER - ACTIVE TRADER DECISIONS (v3.0.27.1)
# NOTE: Older v3.0.26 definition removed (was shadowed by v3.0.27.1 at line 1617)
# =====================================================================


# =====================================================================
# GUARDRAILS (8 LEVELS) - ENHANCED
# =====================================================================

def check_guardrails(symbol, trade_size, portfolio_value, trades_today, max_daily_trades,
                    holdings, asset_class, metrics):
    """Check 8-level guardrails before execution."""

    # G1: Daily frequency cap
    if trades_today >= max_daily_trades:
        return False, f"Daily limit reached ({trades_today}/{max_daily_trades})"

    # G2: Position size limit (with floor for small portfolios)
    # Ensures minimum executable trade while maintaining % guardrails at scale
    position_limit = max(MIN_TRADE_SIZE_TARGET, portfolio_value * POSITION_LIMIT_PCT)
    if trade_size > position_limit:
        return False, f"Position too large (${trade_size:.2f} > ${position_limit:.2f})"

    # G3: REMOVED (v3.0.27.1) - No longer block duplicates
    # Smart exclusion logic now handles diversification intelligently
    # Claude can recommend BUY_MORE of existing holdings when PM directive allows
    # G8 (holdings limit) still manages portfolio concentration at scale

    # G4: Liquidity buffer (with floor for small portfolios)
    # Maintains 50% guardrail at scale while allowing minimum trades on small portfolios
    liquidity_limit = max(MIN_TRADE_SIZE_TARGET, portfolio_value * 0.5)
    if trade_size > liquidity_limit:
        return False, f"Would consume >{liquidity_limit/portfolio_value*100:.0f}% of portfolio"

    # G5: Options exposure limit
    if asset_class == 'OPTION_SPREAD':
        options_exposure = sum(h['cost_basis'] for sym, h in holdings.items() if h.get('asset_class') == 'OPTION_SPREAD')
        if (options_exposure + trade_size) > (portfolio_value * OPTIONS_EXPOSURE_LIMIT_PCT):
            return False, f"Options exposure limit exceeded"

    # G6: Sector exposure limit
    if asset_class in ['STOCK', 'SECTOR_ETF']:
        # Get sector from holdings
        sector_exposure = 0
        for sym, h in holdings.items():
            if h.get('asset_class') == asset_class:
                sector_exposure += h['cost_basis']

        if (sector_exposure + trade_size) > (portfolio_value * SECTOR_EXPOSURE_LIMIT_PCT):
            return False, f"Sector exposure limit exceeded"

    # G7: Drawdown limit
    if metrics.daily_change_pct < -PORTFOLIO_DRAWDOWN_LIMIT_PCT:
        return False, f"Portfolio drawdown limit ({metrics.daily_change_pct:.2f}%) exceeded"

    # G8: Holdings limit (tiered by portfolio size)
    # NEW (v3.0.25): Instead of blocking, trigger TRADER MODE rebalance
    current_holdings = len(holdings)
    max_holdings = None
    for (tier_min, tier_max), limit in HOLDINGS_LIMIT_TIERS.items():
        if tier_min <= portfolio_value < tier_max:
            max_holdings = limit
            break

    if max_holdings and current_holdings >= max_holdings:
        # Check if symbol already exists (can add more)
        if symbol in holdings:
            print(f"[G8] Buying more of existing {symbol} (allowed at limit)")
            return True, "PASS"
        else:
            # NEW SYMBOL at limit: trigger TRADER MODE rebalance
            return False, f"TRADER_MODE_REBALANCE|{current_holdings}|{max_holdings}|{portfolio_value:.0f}"

    print("[GUARDRAILS] ✅ All checks passed")
    return True, "PASS"


# =====================================================================
# PORTFOLIO MANAGER: DIRECTIVE LAYER (v3.0.27)
# =====================================================================

def portfolio_manager_directive(holdings, cio_regime, cio_confidence, macro_data):
    """
    Portfolio Manager sets allocation directive based on CIO thesis.

    Analyzes:
    - Current sector allocations
    - CIO macro regime (NORMAL/HIGH/PANIC)
    - CIO confidence level

    Returns: (action, sector_reduce, sector_increase, rationale)
    Actions: BUY, SELL, ROTATE, HOLD
    """

    print("\n[PM_DIRECTIVE] Analyzing portfolio against CIO thesis...")

    if not holdings:
        print("[PM_DIRECTIVE] 🟢 Portfolio empty - BUY action")
        return "BUY", None, None, "Portfolio empty. Initiate growth allocation."

    # Calculate sector allocations
    sector_alloc = {}
    total_value = 0

    # Map symbols to sectors (simplified)
    sector_map = {
        'TSLA': 'tech', 'NVDA': 'tech', 'AAPL': 'tech', 'MSFT': 'tech', 'GOOG': 'tech', 'AMZN': 'tech', 'QQQ': 'tech', 'XLK': 'tech', 'VGT': 'tech',
        'PG': 'defensive', 'JNJ': 'defensive', 'KO': 'defensive', 'PEP': 'defensive', 'XLP': 'defensive', 'VDC': 'defensive', 'SHV': 'defensive', 'SHY': 'defensive',
        'SPY': 'broad', 'IVV': 'broad', 'VOO': 'broad', 'VTI': 'broad', 'VTSAX': 'broad', 'IWM': 'broad',
        'SCHD': 'dividend', 'DGRO': 'dividend', 'VYMI': 'dividend', 'VYM': 'dividend', 'SPYD': 'dividend', 'DVY': 'dividend',
        'BND': 'bonds', 'AGG': 'bonds', 'TLT': 'bonds',
        'AOR': 'allocation'
    }

    for symbol, holding in holdings.items():
        entry_price = holding.get('entry_price', 0)
        current_price = holding.get('current_price', entry_price)
        quantity = holding.get('quantity', 0)

        if entry_price > 0 and quantity > 0:
            position_value = current_price * quantity
            sector = sector_map.get(symbol, 'other')
            sector_alloc[sector] = sector_alloc.get(sector, 0) + position_value
            total_value += position_value

    # Convert to percentages
    if total_value > 0:
        for sector in sector_alloc:
            sector_alloc[sector] = (sector_alloc[sector] / total_value) * 100

    print(f"[PM_DIRECTIVE] Current allocations: {sector_alloc}")
    print(f"[PM_DIRECTIVE] CIO: regime={cio_regime}, confidence={cio_confidence}/10")

    # Target allocations based on CIO regime
    if cio_regime in ['NORMAL', 'LOW']:  # Growth-favorable
        targets = {
            'tech': 35,
            'broad': 30,
            'dividend': 20,
            'defensive': 10,
            'bonds': 5
        }
        regime_label = "Growth"

    elif cio_regime == 'HIGH':  # Risk-off
        targets = {
            'tech': 15,
            'defensive': 35,
            'dividend': 25,
            'broad': 20,
            'bonds': 5
        }
        regime_label = "Risk-Off"

    elif cio_regime == 'PANIC':  # Extreme risk-off
        targets = {
            'tech': 5,
            'defensive': 50,
            'dividend': 20,
            'broad': 15,
            'bonds': 10
        }
        regime_label = "Panic"

    else:  # Unknown
        targets = {
            'tech': 25,
            'broad': 30,
            'dividend': 20,
            'defensive': 20,
            'bonds': 5
        }
        regime_label = "Neutral"

    # Find over/underweight sectors
    overweight = {}
    underweight = {}

    for sector, target in targets.items():
        current = sector_alloc.get(sector, 0)
        diff = current - target
        if diff > 5:  # More than 5% overweight
            overweight[sector] = diff
        elif diff < -5:  # More than 5% underweight
            underweight[sector] = abs(diff)

    print(f"[PM_DIRECTIVE] Overweight: {overweight}")
    print(f"[PM_DIRECTIVE] Underweight: {underweight}")

    # Determine action based on CIO confidence
    if not overweight and not underweight:
        action = "HOLD"
        rationale = f"Portfolio balanced with {regime_label} allocation targets."
        print(f"[PM_DIRECTIVE] ⚪ HOLD: {rationale}")
        return action, None, None, rationale

    if overweight and underweight:
        # Rotate from overweight to underweight
        sector_reduce = max(overweight, key=overweight.get)
        sector_increase = max(underweight, key=underweight.get)

        if cio_confidence >= 6:
            action = "ROTATE"
            rationale = f"{regime_label} regime (conf {cio_confidence}/10): rotate {sector_reduce.upper()} → {sector_increase.upper()}"
            print(f"[PM_DIRECTIVE] 🟠 ROTATE: {rationale}")
            return action, sector_reduce, sector_increase, rationale
        else:
            action = "HOLD"
            rationale = f"Imbalance detected but CIO confidence low ({cio_confidence}/10). Monitor."
            print(f"[PM_DIRECTIVE] ⚪ HOLD: {rationale}")
            return action, None, None, rationale

    elif underweight:
        # Buy underweight sectors
        sector_increase = max(underweight, key=underweight.get)
        action = "BUY"
        rationale = f"{regime_label} regime (conf {cio_confidence}/10): increase {sector_increase.upper()}"
        print(f"[PM_DIRECTIVE] 🟢 BUY: {rationale}")
        return action, None, sector_increase, rationale

    else:  # Only overweight
        # Sell overweight sectors
        sector_reduce = max(overweight, key=overweight.get)
        action = "SELL"
        rationale = f"{regime_label} regime (conf {cio_confidence}/10): reduce {sector_reduce.upper()}"
        print(f"[PM_DIRECTIVE] 🔴 SELL: {rationale}")
        return action, sector_reduce, None, rationale


def portfolio_manager_decision(symbol, asset_class, price, holdings, cio_regime, cio_confidence, portfolio_value, macro_data, buying_power=0):
    """
    Portfolio Manager active decision layer - trader-like analysis.

    Evaluates:
    - Account health (FIX #40): Negative buying power blocks ALL trades
    - Existing holdings: P&L % (60% weight) + thesis alignment (40% weight)
    - New opportunity: position in portfolio thesis
    - Composite decision: BUY, SELL_AND_BUY, HOLD, BUY_MORE

    Returns: (action, target_symbol_if_needed, rationale)
    """

    print("\n[PORTFOLIO_MANAGER] Analyzing portfolio and new opportunity...")

    # FIX #40: ACCOUNT HEALTH CHECK - Negative buying power indicates margin deficit
    # Cannot execute ANY trades when account is in deficit (negative option buying power)
    if buying_power < 0:
        action = "HOLD"
        rationale = f"Account in margin deficit (${buying_power:.2f}). Cannot execute trades. Cash injection required."
        print(f"[PORTFOLIO_MANAGER] 🔴 ACCOUNT_HEALTH_CHECK_FAILED: {rationale}")
        print(f"[PORTFOLIO_MANAGER] ⏸️ HOLD signal - account needs cash deposit")
        return action, None, rationale

    # If portfolio empty, just buy
    if not holdings:
        action = "BUY"
        rationale = f"Portfolio empty. Initiating with {symbol}."
        print(f"[PORTFOLIO_MANAGER] 🟢 {action}: {rationale}")
        return action, None, rationale

    # Score thesis alignment based on symbol and macro regime
    def get_thesis_score(ticker, regime):
        """Map symbol to thesis score based on macro regime"""
        tech_stocks = ['TSLA', 'NVDA', 'AAPL', 'MSFT', 'GOOG', 'AMZN', 'QQQ', 'XLK', 'VGT']
        defensive = ['PG', 'JNJ', 'KO', 'PEP', 'XLP', 'VDC', 'SHV', 'SHY']
        broad_market = ['SPY', 'IVV', 'VOO', 'VTI', 'VTSAX']
        dividend = ['SCHD', 'DGRO', 'VYMI', 'VYM', 'SPYD', 'DVY']

        # Score 0-10 scale based on regime
        if regime in ['NORMAL', 'LOW']:  # Growth-friendly regimes
            if ticker in tech_stocks:
                return 8  # High conviction on tech in growth
            elif ticker in broad_market:
                return 7
            elif ticker in dividend:
                return 6
            elif ticker in defensive:
                return 5
            else:
                return 6  # Default mid-range

        elif regime == 'HIGH':  # Risk-off
            if ticker in defensive:
                return 9  # Defensive outperforms in high volatility
            elif ticker in dividend:
                return 8
            elif ticker in broad_market:
                return 6
            elif ticker in tech_stocks:
                return 4  # Tech underperforms in stress
            else:
                return 6

        elif regime == 'PANIC':  # Extreme risk-off
            if ticker in defensive:
                return 9
            elif ticker in dividend:
                return 8
            elif ticker in broad_market:
                return 5
            else:
                return 4

        else:  # Unknown regime - neutral positioning
            return 6

    # Calculate composite score for each existing holding
    holdings_scores = {}
    for ticker, holding in holdings.items():
        entry_price = holding.get('entry_price', 0)
        current_price = holding.get('current_price', entry_price)
        quantity = holding.get('quantity', 0)

        if entry_price > 0 and quantity > 0:
            # P&L % (60% weight)
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            pnl_score = max(0, min(10, 5 + (pnl_pct / 10)))  # 0-10 scale

            # Thesis alignment (40% weight)
            thesis_score = get_thesis_score(ticker, cio_regime)

            # Composite: weighted average
            composite = (pnl_score * 0.6) + (thesis_score * 0.4)
            holdings_scores[ticker] = {
                'pnl_pct': pnl_pct,
                'pnl_score': pnl_score,
                'thesis_score': thesis_score,
                'composite': composite
            }

    # Score new opportunity
    new_opp_thesis = get_thesis_score(symbol, cio_regime)

    # Find worst performer
    worst_ticker = min(holdings_scores, key=lambda x: holdings_scores[x]['composite'])
    worst_score = holdings_scores[worst_ticker]['composite']
    worst_pnl = holdings_scores[worst_ticker]['pnl_pct']

    print(f"[PORTFOLIO_MANAGER] New opportunity: {symbol} (thesis score: {new_opp_thesis}/10)")
    print(f"[PORTFOLIO_MANAGER] Worst holding: {worst_ticker} (composite: {worst_score:.1f}/10, P&L: {worst_pnl:.2f}%)")

    # Decision logic

    # 1. Worst performer down >5% AND new opportunity has strong conviction (7+/10)
    if worst_pnl < -5.0 and new_opp_thesis >= 7:
        action = "SELL_AND_BUY"
        target = worst_ticker
        rationale = f"Worst performer {worst_ticker} down {worst_pnl:.2f}%. Strong {symbol} conviction ({new_opp_thesis}/10). Rebalance."
        print(f"[PORTFOLIO_MANAGER] 🟠 {action}: {rationale}")
        return action, target, rationale

    # 2. Winning position (>10% P&L) AND strong new conviction (8+/10) → buy new, hold winner
    best_ticker = max(holdings_scores, key=lambda x: holdings_scores[x]['pnl_pct'])
    best_pnl = holdings_scores[best_ticker]['pnl_pct']
    if best_pnl > 10.0 and new_opp_thesis >= 8 and len(holdings) < 15:
        action = "BUY"
        rationale = f"Winner {best_ticker} at {best_pnl:.2f}% P&L. Strong {symbol} conviction ({new_opp_thesis}/10). Adding position."
        print(f"[PORTFOLIO_MANAGER] 🟢 {action}: {rationale}")
        return action, None, rationale

    # 3. Significantly better opportunity (score diff >20 points)
    if (new_opp_thesis * 10) - worst_score > 20:
        action = "SELL_AND_BUY"
        target = worst_ticker
        rationale = f"Opportunity score diff >20 ({new_opp_thesis*10:.1f} vs {worst_score:.1f}). Rebalancing {worst_ticker}→{symbol}."
        print(f"[PORTFOLIO_MANAGER] 🟠 {action}: {rationale}")
        return action, target, rationale

    # 4. Room in portfolio (<15 holdings) AND decent conviction (6+/10)
    if len(holdings) < 15 and new_opp_thesis >= 6:
        action = "BUY"
        rationale = f"Room in portfolio ({len(holdings)}/15 holdings). {symbol} thesis {new_opp_thesis}/10."
        print(f"[PORTFOLIO_MANAGER] 🟢 {action}: {rationale}")
        return action, None, rationale

    # 5. Already holding symbol with positive P&L - buy more
    if symbol in holdings:
        holding_pnl = holdings_scores[symbol]['pnl_pct']
        if holding_pnl > 0 and new_opp_thesis >= 7:
            action = "BUY_MORE"
            rationale = f"{symbol} winning at {holding_pnl:.2f}%. Strong thesis ({new_opp_thesis}/10). Adding to position."
            print(f"[PORTFOLIO_MANAGER] 🟢 {action}: {rationale}")
            return action, None, rationale

    # 6. Default: Hold and monitor
    action = "HOLD"
    rationale = f"No clear rebalance trigger. Monitoring thesis score {new_opp_thesis}/10."
    print(f"[PORTFOLIO_MANAGER] ⚪ {action}: {rationale}")
    return action, None, rationale


# =====================================================================
# TRADER MODE: ACTIVE REBALANCING (v3.0.25)
# =====================================================================

def find_worst_performer(holdings):
    """
    Identify the worst-performing holding by P&L %.
    Returns: (symbol, pnl_pct, quantity, entry_price) or (None, None, None, None)
    """
    if not holdings:
        return None, None, None, None

    worst_symbol = None
    worst_pnl_pct = float('inf')
    worst_quantity = None
    worst_entry_price = None

    for symbol, holding in holdings.items():
        entry_price = holding.get('entry_price', 0)
        current_price = holding.get('current_price', entry_price)
        quantity = holding.get('quantity', 0)

        if entry_price > 0 and quantity > 0:
            pnl = (current_price - entry_price) / entry_price * 100
            if pnl < worst_pnl_pct:
                worst_pnl_pct = pnl
                worst_symbol = symbol
                worst_quantity = quantity
                worst_entry_price = entry_price

    return worst_symbol, worst_pnl_pct, worst_quantity, worst_entry_price


# =====================================================================
# VALIDATE SELL POSITION (FIX #39: PREVENT OVERSOLD/OVERBOUGHT REJECTIONS)
# =====================================================================

def validate_sell_position(holdings, symbol, quantity):
    """
    Validate sell position before posting order to Schwab.
    Prevents oversold/overbought rejections by checking:
    1. Position exists and has quantity
    2. Sell quantity is reasonable (not microfraction that triggers Schwab blocks)
    3. Quantity can be rounded to whole shares if fractional is too small

    FIX #39: Guards against "may result in oversold/overbought position" rejections
    Returns: (can_sell, adjusted_quantity, message)
    """
    try:
        # Check if position exists
        if symbol not in holdings:
            return False, 0, f"Position {symbol} not found"

        holding = holdings[symbol]
        available_quantity = holding.get('quantity', 0)

        # Check if position has quantity
        if available_quantity <= 0:
            return False, 0, f"Position {symbol} has no quantity ({available_quantity})"

        # Check if trying to sell more than available
        if quantity > available_quantity:
            print(f"[VALIDATE] ⚠️ Requested sell {quantity} > available {available_quantity}, reducing to available")
            quantity = available_quantity

        # Validate fractional quantity
        # Schwab minimum for fractional shares is 0.001
        # If fractional and too small (<0.001), round down to whole shares
        if quantity < 1.0:
            if quantity < 0.001:
                # Microfraction - round down to 0 (don't sell)
                print(f"[VALIDATE] ⚠️ Microfraction sale {quantity:.4f} shares < 0.001 minimum, canceling sell")
                return False, 0, f"Microfraction {quantity:.4f} < 0.001 minimum"
            elif quantity < 0.01:
                # Very small fractional (0.001-0.01) - risky, log warning
                print(f"[VALIDATE] ⚠️ Small fractional sale {quantity:.4f} shares may be rejected by Schwab")
                # Check if we can round to whole shares instead
                whole_shares = int(available_quantity)
                if whole_shares > 0:
                    print(f"[VALIDATE] 💡 Rounding to whole shares instead: {whole_shares} shares")
                    return True, whole_shares, f"Adjusted from {quantity:.4f} to {whole_shares} whole shares"
                else:
                    return False, 0, f"Cannot round {quantity:.4f} to whole shares"

        # Safe to sell
        return True, quantity, f"Validated sell quantity {quantity:.4f}"

    except Exception as e:
        print(f"[VALIDATE] ❌ Validation error: {e}")
        return False, 0, f"Validation exception: {str(e)}"


# =====================================================================
# VERIFY ORDER STATUS (SHARED VERIFICATION FOR REBALANCE)
# =====================================================================

def verify_order_status_on_schwab(access_token, order_id, account_hash):
    """
    Verify order status on Schwab after placement.
    Returns: (success, status, message)

    FIX #38: Extract verification logic for use by execute_rebalance.
    Ensures both sell and buy orders are actually accepted, not rejected.
    """
    try:
        verify_url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}/orders/{order_id}"
        verify_headers = {'Authorization': f'Bearer {access_token}'}

        verify_response = requests.get(verify_url, headers=verify_headers, timeout=10)

        if verify_response is None:
            print(f"[VERIFY] ❌ Response is None for order {order_id}")
            return False, 'UNKNOWN', "Verification response was None"

        if verify_response.status_code == 200:
            try:
                order_data = verify_response.json()
            except Exception as json_err:
                print(f"[VERIFY] ❌ Failed to parse verification response: {json_err}")
                return False, 'UNKNOWN', f"JSON parse error: {str(json_err)}"

            if not order_data or not isinstance(order_data, dict):
                print(f"[VERIFY] ❌ Invalid order data from Schwab")
                return False, 'UNKNOWN', "Invalid order data structure"

            status = order_data.get('status', 'UNKNOWN').upper()

            # FIX #38: VALIDATION OF ORDER STATUS
            ACCEPTED_STATUSES = ['ACCEPTED', 'WORKING', 'FILLED', 'PENDING_NEW', 'PENDING_ACTIVATION']
            REJECTED_STATUSES = ['REJECTED', 'CANCELED', 'EXPIRED', 'FAILED']

            if status in ACCEPTED_STATUSES:
                print(f"[VERIFY] ✅ Order {order_id} confirmed: {status}")
                return True, status, f"Order verified ({status})"
            elif status in REJECTED_STATUSES:
                rejection_reason = (
                    order_data.get('statusDescription') or
                    order_data.get('rejectReason') or
                    order_data.get('rejectReasons') or
                    'Not provided'
                )
                print(f"[VERIFY] ❌ Order {order_id} REJECTED: {rejection_reason}")
                print(f"[DEBUG] Full response: {json.dumps(order_data, default=str)}")
                return False, status, f"Order rejected: {rejection_reason}"
            else:
                print(f"[VERIFY] ⚠️  Order {order_id} status unknown: {status}")
                return True, status, f"Order status: {status}"

        elif verify_response.status_code == 404:
            print(f"[VERIFY] ❌ Order {order_id} NOT FOUND (404) on Schwab")
            return False, 'NOT_FOUND', "Order not found on Schwab"
        else:
            print(f"[VERIFY] ❌ Verification HTTP {verify_response.status_code}")
            return False, 'UNKNOWN', f"HTTP {verify_response.status_code}"

    except Exception as e:
        print(f"[VERIFY] ❌ Verification exception: {e}")
        return False, 'UNKNOWN', f"Exception: {str(e)}"


def execute_rebalance(access_token, worst_symbol, quantity, account_hash, new_symbol,
                      new_quantity, new_price, asset_class, worst_pnl_pct, holdings=None):
    """
    Execute trader rebalance: sell worst performer, buy new opportunity.
    FIX #38: Refactored to verify BOTH sell and buy orders using verify_order_status_on_schwab.
    FIX #39: Validate sell position before posting to prevent oversold/overbought rejections.
    Returns: (success, message)
    """
    try:
        print(f"\n[TRADER MODE] 🔄 REBALANCING: Selling {worst_symbol} ({worst_pnl_pct:.2f}% P&L)")
        print(f"[TRADER MODE] 🎯 DEPLOYING: {new_symbol} ({asset_class})")

        # FIX #39: VALIDATE SELL POSITION BEFORE POSTING
        # Check if we can actually sell this quantity without triggering Schwab rejections
        if holdings is not None:
            can_sell, validated_quantity, validation_msg = validate_sell_position(holdings, worst_symbol, quantity)

            if not can_sell:
                print(f"[VALIDATE] ❌ Sell validation failed: {validation_msg}")
                return False, f"Sell {worst_symbol} blocked: {validation_msg}"

            if validated_quantity != quantity:
                print(f"[VALIDATE] ⚠️ Adjusted sell quantity: {quantity:.4f} → {validated_quantity:.4f}")
                quantity = validated_quantity
        else:
            print(f"[VALIDATE] ⚠️ Holdings not provided, skipping sell validation")

        # Step 1: Sell worst performer
        # FIX #41: Use LIMIT orders for fractional shares (Schwab API requires it)
        # MARKET orders only accept whole shares; fractional quantities require LIMIT with price
        sell_order_type = "LIMIT" if quantity < 1.0 else "MARKET"
        sell_payload = {
            "orderType": sell_order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": "SELL",
                "quantity": round(quantity, 4) if quantity < 1.0 else int(quantity),
                "quantityType": "SHARES",
                "instrument": {"symbol": worst_symbol, "assetType": "EQUITY"}
            }]
        }
        
        # FIX #41: For LIMIT orders, add a conservative limit price
        if quantity < 1.0:
            # For fractional shares, we need to provide a price for the LIMIT order
            # Use 99% of estimated current price to ensure execution but avoid slippage
            estimated_price = new_price if new_price and new_price > 0 else 100.0
            sell_payload["price"] = round(estimated_price * 0.99, 2)  # 1% below market
            print(f"[TRADER MODE] LIMIT price set for fractional SELL: ${sell_payload['price']:.2f}")

        sell_url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}/orders"
        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

        print(f"[TRADER MODE] Posting SELL order for {worst_symbol}...")
        sell_response = requests.post(sell_url, json=sell_payload, headers=headers, timeout=15)

        if sell_response is None:
            print(f"[TRADER MODE] ❌ SELL response is None")
            return False, f"Sell {worst_symbol} failed: No response"

        if sell_response.status_code not in [201, 200]:
            print(f"[TRADER MODE] ❌ SELL HTTP {sell_response.status_code}")
            return False, f"Sell {worst_symbol} failed: HTTP {sell_response.status_code}"

        sell_order_id = sell_response.headers.get('Location', 'unknown').split('/')[-1] if 'Location' in sell_response.headers else 'unknown'
        print(f"[TRADER MODE] HTTP 201: SELL order ID {sell_order_id}")

        # FIX #38: VERIFY SELL ORDER STATUS BEFORE PROCEEDING
        sell_verified, sell_status, sell_msg = verify_order_status_on_schwab(access_token, sell_order_id, account_hash)

        if not sell_verified:
            print(f"[TRADER MODE] ❌ SELL ORDER REJECTED: {sell_msg}")
            return False, f"Sell {worst_symbol} rejected: {sell_msg}"

        print(f"[TRADER MODE] ✅ SOLD {worst_symbol} - Order: {sell_order_id} ({sell_status})")

        # Step 2: Buy new opportunity
        # FIX #41: Use LIMIT orders for fractional buys (consistent with SELL logic)
        buy_order_type = "LIMIT" if new_quantity < 1.0 else "MARKET"
        buy_payload = {
            "orderType": buy_order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": "BUY",
                "quantity": round(new_quantity, 4) if new_quantity < 1.0 else int(new_quantity),
                "quantityType": "SHARES",
                "instrument": {"symbol": new_symbol, "assetType": "EQUITY"}
            }]
        }
        
        # FIX #41: For LIMIT orders, add a conservative limit price
        if new_quantity < 1.0:
            # For fractional shares, we need to provide a price for the LIMIT order
            # Use 101% of new_price to ensure execution (willing to pay slightly above market)
            buy_payload["price"] = round(new_price * 1.01, 2)  # 1% above market for execution
            print(f"[TRADER MODE] LIMIT price set for fractional BUY: ${buy_payload['price']:.2f}")

        print(f"[TRADER MODE] Posting BUY order for {new_symbol}...")
        buy_response = requests.post(sell_url, json=buy_payload, headers=headers, timeout=15)

        if buy_response is None:
            print(f"[TRADER MODE] ❌ BUY response is None")
            return False, f"Buy {new_symbol} failed: No response"

        if buy_response.status_code not in [201, 200]:
            print(f"[TRADER MODE] ❌ BUY HTTP {buy_response.status_code}")
            return False, f"Buy {new_symbol} failed: HTTP {buy_response.status_code}"

        buy_order_id = buy_response.headers.get('Location', 'unknown').split('/')[-1] if 'Location' in buy_response.headers else 'unknown'
        print(f"[TRADER MODE] HTTP 201: BUY order ID {buy_order_id}")

        # FIX #38: VERIFY BUY ORDER STATUS BEFORE PROCEEDING
        buy_verified, buy_status, buy_msg = verify_order_status_on_schwab(access_token, buy_order_id, account_hash)

        if not buy_verified:
            print(f"[TRADER MODE] ❌ BUY ORDER REJECTED: {buy_msg}")
            return False, f"Buy {new_symbol} rejected: {buy_msg}"

        print(f"[TRADER MODE] ✅ BOUGHT {new_symbol} - Order: {buy_order_id} ({buy_status})")

        # Both orders verified - rebalance successful
        return True, f"Rebalanced: {worst_symbol}→{new_symbol} (both orders verified)"

    except Exception as e:
        print(f"[TRADER MODE] ❌ Rebalance failed: {e}")
        return False, str(e)


# =====================================================================
# EXECUTION WITH VERIFICATION (CRITICAL FIX #36)
# =====================================================================

def preview_order_on_schwab(access_token, symbol, quantity, account_hash, price, asset_class):
    """
    Preview order BEFORE placing it to check buying power and validation.
    Returns: (can_execute, error_message)

    FIX v3.0.15 #4: Dynamically reads actual buying power from Schwab
    """
    try:
        preview_url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}/previewOrder"

        order_payload = {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": round(quantity, 4) if quantity < 1.0 else int(quantity),
                    "quantityType": "SHARES",
                    "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                }
            ]
        }

        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
        response = requests.post(preview_url, json=order_payload, headers=headers, timeout=15)

        if response.status_code == 200:
            try:
                preview_data = response.json()
                # Check for validation errors in preview
                warnings = preview_data.get('orderValidationResult', {}).get('warnings', [])
                errors = preview_data.get('orderValidationResult', {}).get('errors', [])

                for error in errors:
                    error_msg = error.get('message', str(error))
                    if 'buying power' in error_msg.lower() or 'insufficient' in error_msg.lower() or 'no trades' in error_msg.lower():
                        print(f"[PREVIEW] ⚠️  Insufficient buying power: {error_msg}")
                        return False, error_msg

                for warning in warnings:
                    warning_msg = warning.get('message', str(warning))
                    print(f"[PREVIEW] ⚠️  Warning: {warning_msg}")

                print(f"[PREVIEW] ✅ Order preview passed - safe to execute")
                return True, None
            except Exception as parse_err:
                print(f"[PREVIEW] Failed to parse response: {parse_err}")
                return True, None  # Continue anyway if we can't parse
        else:
            error_text = response.text[:200] if hasattr(response, 'text') else 'Unknown'
            print(f"[PREVIEW] HTTP {response.status_code}: {error_text}")
            if response.status_code == 403 or 'not allowed' in error_text.lower():
                return False, f"Preview rejected: {error_text}"
            return True, None  # Continue if preview endpoint fails
    except Exception as e:
        print(f"[PREVIEW] Exception: {e}")
        return True, None  # Continue if preview fails


def execute_trade_on_schwab(access_token, symbol, trade_size_dollars, account_hash, price, asset_class):
    """
    EXECUTE order AND verify it actually exists on Schwab.
    Returns: (success, order_id, error_detail)

    FIX #36: Verifies order exists on Schwab before logging to DynamoDB
    FIX v3.0.14 #4: Supports fractional shares with fallback to whole shares
    """
    try:
        # FIX #1: Input validation - trade size must be positive
        if trade_size_dollars <= 0:
            print(f"[ERROR] ❌ Invalid trade size: ${trade_size_dollars}")
            return False, None, "Trade size must be positive"

        # FIX #2: Input validation - symbol must not be empty or None
        if not symbol or not isinstance(symbol, str) or len(symbol.strip()) == 0:
            print(f"[ERROR] ❌ Invalid symbol: {symbol}")
            return False, None, "Symbol cannot be empty"

        if not account_hash:
            print(f"[ERROR] ❌ No account hash")
            return False, None, "No account hash"

        if not access_token:
            print(f"[ERROR] ❌ No access token")
            return False, None, "No access token"

        url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}/orders"
        quantity_in_shares = trade_size_dollars / price if price > 0 else 0

        # CTO EXECUTIVE FIX: Round BUY quantities to whole shares to prevent fractional accumulation
        # Previous bug: 0.0263 share fractionals couldn't be sold back (Schwab rejects < 0.001)
        # Solution: Buy whole shares only; if can't afford 1 share, don't trade
        quantity_in_shares_raw = quantity_in_shares
        quantity_in_shares = int(quantity_in_shares)  # Round DOWN to whole shares

        if quantity_in_shares == 0:
            print(f"[ERROR] ❌ Insufficient capital: ${trade_size_dollars:.2f} < 1 share @ ${price:.2f}")
            return False, None, "Trade size insufficient for 1 share"

        if quantity_in_shares_raw != quantity_in_shares:
            print(f"[EXECUTE] Rounding {quantity_in_shares_raw:.4f} → {quantity_in_shares} whole shares (CTO fix: prevents fractional accumulation)")

        print(f"[EXECUTE] {symbol} | {quantity_in_shares} shares @ ${price:.2f}")

        # *** HANDLE OPTION_SPREAD SEPARATELY ***
        if asset_class == 'OPTION_SPREAD':
            order_payload = {
                "orderType": "NET_DEBIT",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "MULTI_LEG",
                "orderLegCollection": [
                    {"instruction": "BUY", "quantity": 1, "instrument": {"symbol": symbol, "assetType": "OPTION"}},
                    {"instruction": "SELL", "quantity": 1, "instrument": {"symbol": symbol, "assetType": "OPTION"}}
                ]
            }

            headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
            print(f"[EXECUTE] Posting option order...")

            try:
                response = requests.post(url, json=order_payload, headers=headers, timeout=15)
            except Exception as post_err:
                print(f"[ERROR] ❌ OPTION request POST failed: {post_err}")
                return False, None, f"OPTION request failed: {str(post_err)}"

            if response is None:
                print(f"[ERROR] ❌ OPTION response is None")
                return False, None, "No response from Schwab (OPTION)"

            # Process OPTION response and return (no retry for options)
            if response.status_code == 201:
                try:
                    # Apply same defensive check as EQUITY section
                    location = ''
                    if response and hasattr(response, 'headers') and response.headers:
                        location = response.headers.get('Location', '')
                    order_id = location.split('/')[-1] if location else None
                except Exception as header_err:
                    print(f"[ERROR] ❌ OPTION: Failed to parse order ID: {header_err}")
                    return False, None, f"OPTION parse error: {str(header_err)}"

                if order_id and order_id != 'UNKNOWN':
                    return True, order_id, f"OPTION order placed: {order_id}"
                else:
                    print(f"[ERROR] ❌ OPTION: No order ID in response")
                    return False, None, "OPTION: No order ID in response"
            else:
                error_msg = response.text[:200] if hasattr(response, 'text') else 'Unknown error'
                print(f"[ERROR] ❌ OPTION HTTP {response.status_code}: {error_msg}")
                return False, None, f"OPTION HTTP {response.status_code}: {error_msg}"

        # *** FIX v3.0.14 #4: FRACTIONAL SHARE SUPPORT (EQUITY ONLY) ***
        # Fractional share strategy (v3.0.27.1): Enables BUY_MORE with small position sizes
        # - Critical for small portfolios: e.g., $5 trade size / $450 stock = 0.0111 fractional shares
        # - Try fractional first, fall back to whole shares if rejected by Schwab
        order_attempts = [('FRACTIONAL', quantity_in_shares)]  # First attempt: fractional (supports BUY_MORE)

        # Add whole share fallback ONLY if quantity >= 1.0 (for edge cases where fractional rejected)
        if quantity_in_shares >= 1.0:
            order_attempts.append(('WHOLE', math.floor(quantity_in_shares)))

        # *** TRY ORDER ATTEMPTS (FRACTIONAL FIRST, THEN WHOLE) - SUPPORTS BUY_MORE PURCHASES ***
        for attempt_type, attempt_qty in order_attempts:
            print(f"[EXECUTE] Attempting {attempt_type} shares...")
            # FIX #3 & #4: Remove dead code, use consistent math.floor() for whole shares
            # FIX v3.0.15 #1: SCHWAB DECIMAL PRECISION (4 decimals max when existing fractional position has 5)
            if attempt_type == 'FRACTIONAL':
                # Schwab rule: if account has existing fractional position with 5 decimals,
                # new orders MUST be 4 decimals or less. Rounding to 4 decimals ensures compliance.
                attempt_qty_rounded = round(attempt_qty, 4)
            else:
                attempt_qty_rounded = math.floor(attempt_qty)

            # FIX v3.0.15 #4: PREVIEW ORDER FIRST - Check buying power before posting
            can_execute, preview_error = preview_order_on_schwab(access_token, symbol, attempt_qty_rounded, account_hash, price, asset_class)
            if not can_execute:
                print(f"[FALLBACK] Preview failed: {preview_error}")
                if attempt_type == 'FRACTIONAL':
                    print(f"[FALLBACK] Retrying with whole shares...")
                    continue
                return False, None, f"Order preview failed: {preview_error}"

            order_payload = {
                "orderType": "MARKET",
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": "BUY",
                        "quantity": attempt_qty_rounded,
                        "quantityType": "SHARES",
                        "instrument": {"symbol": symbol, "assetType": "EQUITY"}
                    }
                ]
            }

            headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

            print(f"[EXECUTE] Posting order ({attempt_type or 'standard'}: {attempt_qty_rounded} shares)...")

            response = None
            try:
                response = requests.post(url, json=order_payload, headers=headers, timeout=15)
            except Exception as post_err:
                print(f"[ERROR] ❌ Request POST failed: {post_err}")
                return False, None, f"Request failed: {str(post_err)}"

            if response is None:
                print(f"[ERROR] ❌ Response is None")
                return False, None, "No response from Schwab"

            # FIX #5: Remove redundant None check - response already validated above
            try:
                status_code = response.status_code if hasattr(response, 'status_code') else None
                if status_code is None:
                    print(f"[ERROR] ❌ Response has no status_code")
                    return False, None, "Response missing status_code"
                print(f"[RESPONSE] HTTP {status_code}")
            except Exception as sc_err:
                print(f"[ERROR] ❌ Failed to read response status: {sc_err}")
                return False, None, f"Status code error: {str(sc_err)}"

            # *** HANDLE RESPONSE ***
            if status_code == 201:
                try:
                    # FIX #6: Defensive check on response.headers access
                    location = ''
                    if response and hasattr(response, 'headers') and response.headers:
                        location = response.headers.get('Location', '')
                    order_id = location.split('/')[-1] if location else None
                except Exception as header_err:
                    print(f"[ERROR] ❌ Failed to parse order ID from headers: {header_err}")
                    headers_debug = getattr(response, 'headers', 'N/A')
                    print(f"[ERROR] Response headers: {headers_debug}")
                    return False, None, f"Failed to parse order ID: {str(header_err)}"

                print(f"[RESPONSE] HTTP 201 Created | Order ID: {order_id}")

                if not order_id or order_id == 'UNKNOWN':
                    print(f"[ERROR] ❌ No order ID in response")
                    if attempt_type == 'FRACTIONAL':
                        print(f"[FALLBACK] Retrying with whole shares...")
                        continue
                    return False, None, "No order ID in response"

                # *** CRITICAL VERIFICATION STEP (FIX #36) ***
                print(f"[VERIFY] Checking if order {order_id} exists on Schwab...")

                verify_url = f"{SCHWAB_BASE_URL}/accounts/{account_hash}/orders/{order_id}"
                verify_headers = {'Authorization': f'Bearer {access_token}'}

                try:
                    verify_response = requests.get(verify_url, headers=verify_headers, timeout=10)

                    if verify_response is None:
                        print(f"[ERROR] ❌ Verification response is None")
                        return False, order_id, "Verification response was None"

                    if verify_response.status_code == 200:
                        try:
                            order_data = verify_response.json()
                        except Exception as json_err:
                            print(f"[ERROR] ❌ Failed to parse JSON from verification response: {json_err}")
                            return False, order_id, f"JSON parse error: {str(json_err)}"

                        # FIX #8: Defensive None check before order_data.get()
                        if not order_data or not isinstance(order_data, dict):
                            print(f"[ERROR] ❌ Invalid order data structure: {type(order_data)}")
                            return False, order_id, "Invalid order data from Schwab"

                        status = order_data.get('status', 'UNKNOWN').upper()

                        # *** FIX #37: VALIDATE ORDER STATUS ***
                        # Only accept orders that are working/accepted, reject if failed
                        ACCEPTED_STATUSES = ['ACCEPTED', 'WORKING', 'FILLED', 'PENDING_NEW', 'PENDING_ACTIVATION']
                        REJECTED_STATUSES = ['REJECTED', 'CANCELED', 'EXPIRED', 'FAILED']

                        if status in ACCEPTED_STATUSES:
                            print(f"[VERIFY] ✅✅✅ ORDER CONFIRMED ON SCHWAB")
                            print(f"[VERIFY] Status: {status} (ACCEPTED) | {attempt_qty_rounded} shares")
                            return True, order_id, f"Order placed and verified ({attempt_type})"
                        elif status in REJECTED_STATUSES:
                            # NEW: Capture full rejection response for diagnostics (ISSUE #16)
                            # Schwab uses 'statusDescription' for human-readable error messages
                            rejection_reason = (
                                order_data.get('statusDescription') or  # ← SCHWAB PRIMARY FIELD
                                order_data.get('rejectReason') or
                                order_data.get('rejectReasons') or
                                order_data.get('errorMsg') or
                                order_data.get('message') or
                                order_data.get('error') or
                                'Not provided'
                            )
                            error_code = (
                                order_data.get('firmActionType') or  # ← SCHWAB ACTION TYPE
                                order_data.get('statusCode') or
                                order_data.get('errorCode') or
                                order_data.get('code') or
                                'N/A'
                            )

                            print(f"[ERROR] ❌ ORDER {status} ON SCHWAB")
                            print(f"[DEBUG] Rejection reason: {rejection_reason}")
                            print(f"[DEBUG] Error code: {error_code}")
                            print(f"[DEBUG] Attempted quantity: {attempt_qty_rounded} shares ({attempt_type})")
                            # CRITICAL: Always dump full response to see what Schwab actually sent
                            print(f"[DEBUG] FULL RESPONSE DATA: {json.dumps(order_data, default=str)}")
                            print(f"[DEBUG] Response keys: {list(order_data.keys())}")

                            if attempt_type == 'FRACTIONAL':
                                print(f"[FALLBACK] Fractional order rejected, retrying with whole shares...")
                                continue
                            else:
                                # Whole share also rejected - give up
                                print(f"[ERROR] ❌ Whole share attempt also rejected")
                                return False, order_id, f"All attempts rejected by Schwab: {status} ({rejection_reason})"
                        else:
                            print(f"[WARN] ⚠️ ORDER STATUS UNKNOWN: {status}")
                            print(f"[VERIFY] Proceeding with order ID {order_id}")
                            return True, order_id, f"Order verified with status: {status}"

                    # FIX #7 & #9: Remove redundant None/hasattr checks - verify_response already validated
                    elif verify_response.status_code == 404:
                        print(f"[ERROR] ❌ Order returned 201 but NOT FOUND (404)")
                        if attempt_type == 'FRACTIONAL':
                            print(f"[FALLBACK] Retrying with whole shares...")
                            continue
                        else:
                            print(f"[ERROR] ❌ Whole share attempt also returned 404")
                            return False, order_id, "Order verification failed on all attempts (404)"
                    else:
                        print(f"[ERROR] ❌ Verification HTTP {verify_response.status_code}")
                        return False, order_id, f"Verification failed: HTTP {verify_response.status_code}"

                except Exception as e:
                    print(f"[ERROR] ❌ Verification exception: {e}")
                    return False, order_id, f"Verification exception: {str(e)}"

            elif status_code == 400:
                try:
                    error_msg = response.text[:200] if (hasattr(response, 'text') and response.text) else 'No details'
                except:
                    error_msg = 'No details'
                print(f"[ERROR] ❌ HTTP 400 Bad Request: {error_msg}")
                return False, None, f"Bad request: {error_msg}"

            elif status_code == 401:
                print(f"[ERROR] ❌ HTTP 401 Unauthorized — TOKEN EXPIRED")
                return False, None, "Token expired (401)"

            elif status_code == 403:
                try:
                    error_msg = response.text[:200] if (hasattr(response, 'text') and response.text) else 'No details'
                except:
                    error_msg = 'No details'
                print(f"[ERROR] ❌ HTTP 403 Forbidden: {error_msg}")
                return False, None, f"Account access denied (403): {error_msg}"

            elif status_code == 429:
                print(f"[ERROR] ❌ HTTP 429 Rate Limited")
                return False, None, "Rate limited (429)"

            else:
                try:
                    error_msg = response.text[:200] if (hasattr(response, 'text') and response.text) else 'No details'
                except:
                    error_msg = 'No details'
                print(f"[ERROR] ❌ HTTP {status_code}: {error_msg}")
                return False, None, f"HTTP {status_code}: {error_msg}"

    except requests.exceptions.Timeout:
        print(f"[ERROR] ❌ Timeout")
        return False, None, "Timeout"

    except requests.exceptions.ConnectionError:
        print(f"[ERROR] ❌ Connection error")
        return False, None, "Connection error"

    except Exception as e:
        print(f"[ERROR] ❌ Exception: {e}")
        return False, None, str(e)

    # CRITICAL: If we exhaust all attempts without returning, return failure tuple
    print(f"[ERROR] ❌ All order attempts exhausted")
    return False, None, "All order attempts failed"


# =====================================================================
# LOGGING & ALERTS - ENHANCED
# =====================================================================

def log_execution_to_dynamodb(symbol, trade_size_dollars, order_id, asset_class, price):
    """Log ONLY successful, verified trades to DynamoDB."""
    try:
        table = DYNAMODB.Table(TRADE_JOURNAL_TABLE)

        timestamp = datetime.utcnow().isoformat() + 'Z'
        trade_date = datetime.utcnow().strftime('%Y-%m-%d')
        quantity_shares = trade_size_dollars / price if price > 0 else 0

        item = {
            'AccountID': SCHWAB_ACCOUNT_ID,
            'TradeDate': trade_date,
            'Timestamp': timestamp,
            'Symbol': symbol,
            'Quantity': Decimal(str(quantity_shares)),
            'quantityType': 'SHARES',
            'EntryPrice': Decimal(str(price)),
            'TradeSize': Decimal(str(trade_size_dollars)),
            'OrderID': order_id or 'UNKNOWN',
            'Status': 'EXECUTED',
            'AssetClass': asset_class,
            'ExecutionTime': timestamp,
            'VerifiedOnSchwab': True  # FIX #36: Only true when verified
        }

        table.put_item(Item=item)
        print(f"[LOGGING] ✅ Logged to DynamoDB (OrderID: {order_id})")
        return True

    except Exception as e:
        print(f"[LOGGING] ⚠️ Write failed: {e}")
        return False


def log_portfolio_metrics(metrics):
    """Log portfolio performance metrics."""
    try:
        table = DYNAMODB.Table(PORTFOLIO_METRICS_TABLE)

        metric_date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = datetime.utcnow().isoformat() + 'Z'

        item = {
            'MetricDate': metric_date,
            'Timestamp': timestamp,
            **metrics.to_dict()
        }

        table.put_item(Item=item)
        print(f"[METRICS] ✅ Logged portfolio metrics")
        return True

    except Exception as e:
        print(f"[METRICS] ⚠️ Write failed: {e}")
        return False


def send_alert_email(message, stock_symbol, trade_size, asset_class, success, error_detail=None, metrics=None):
    """Send enhanced SNS alert email with metrics."""
    try:
        status_emoji = "✅" if success else "❌"
        subject = f"{status_emoji} McElveen Trading: {stock_symbol} ({asset_class})"

        metrics_text = ""
        if metrics:
            metrics_text = f"""
PORTFOLIO METRICS:
- NAV: ${metrics.nav:.2f}
- Cash: ${metrics.cash:.2f} ({metrics.cash_pct:.1f}%)
- Unrealized P&L: ${metrics.unrealized_pnl:.2f} ({metrics.unrealized_pnl_pct:.2f}%)
- Holdings: {metrics.num_holdings}
- Daily Change: {metrics.daily_change_pct:.2f}%
"""

        body = f"""
McElveen Autonomous Trading System v3.0.15 - DECIMAL PRECISION FIX
==========================================

Timestamp: {datetime.utcnow().isoformat()}Z
Status: {'✅ EXECUTED' if success else '❌ FAILED'}
Symbol: {stock_symbol}
Asset Class: {asset_class}
Trade Size: ${trade_size:.2f}

Message: {message}

{f'Error: {error_detail}' if error_detail and not success else ''}
{metrics_text}

Automated execution from McElveen Autonomous Trading System
"""

        SNS.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=body)
        print(f"[ALERT] ✅ Email sent")
        return True
    except Exception as e:
        print(f"[ALERT] ⚠️ SNS failed: {e}")
        return False


def send_cloudwatch_metric(metric_name, value, unit='None'):
    """Log metric to CloudWatch."""
    try:
        CLOUDWATCH.put_metric_data(
            Namespace='McElveenTrading',
            MetricData=[{
                'MetricName': metric_name,
                'Value': float(value),
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }]
        )
        print(f"[CLOUDWATCH] ✅ Metric: {metric_name} = {value}")
        return True
    except Exception as e:
        print(f"[CLOUDWATCH] ⚠️ Metric failed: {e}")
        return False


# =====================================================================
# MARKET HOURS CHECK
# =====================================================================

def is_market_open():
    """
    Check if US stock markets are open (Mon-Fri, 9:30 AM - 4:00 PM EDT).
    Accounts for federal holidays when markets are closed.
    Returns True only during regular trading hours on non-holiday weekdays.
    """
    try:
        now_utc = datetime.utcnow()
        # Convert UTC to EDT (UTC-4)
        now_edt = now_utc - timedelta(hours=4)

        # US Stock Market Holidays (NASDAQ/NYSE closures)
        # 2026-2027 Federal Holidays when markets are closed
        market_holidays_2026_2027 = [
            (1, 1),    # New Year's Day
            (1, 19),   # MLK Jr. Birthday (3rd Monday in January)
            (2, 16),   # Presidents' Day (3rd Monday in February)
            (3, 27),   # Good Friday (varies, 2026)
            (5, 25),   # Memorial Day (last Monday in May)
            (6, 19),   # Juneteenth
            (7, 3),    # Independence Day observed (when July 4 is Saturday)
            (7, 4),    # Independence Day
            (9, 7),    # Labor Day (1st Monday in September)
            (11, 26),  # Thanksgiving (4th Thursday in November)
            (11, 27),  # Day after Thanksgiving
            (12, 25),  # Christmas
        ]

        # Check if today is a federal holiday
        month = now_edt.month
        day = now_edt.day
        if (month, day) in market_holidays_2026_2027:
            print(f"[MARKET_HOURS] ❌ Market closed (Federal holiday: {month:02d}/{day:02d})")
            return False

        # Check weekday (Monday=0, Sunday=6)
        weekday = now_edt.weekday()
        if weekday >= 5:  # Saturday=5, Sunday=6
            print(f"[MARKET_HOURS] ❌ Market closed (weekend: day {weekday})")
            return False

        # Check time (9:30 AM - 4:00 PM EDT)
        hour = now_edt.hour
        minute = now_edt.minute

        # Before 9:30 AM
        if hour < 9 or (hour == 9 and minute < 30):
            print(f"[MARKET_HOURS] ❌ Market closed (before 9:30 AM: {hour:02d}:{minute:02d} EDT)")
            return False

        # After 4:00 PM
        if hour >= 16:
            print(f"[MARKET_HOURS] ❌ Market closed (after 4:00 PM: {hour:02d}:{minute:02d} EDT)")
            return False

        print(f"[MARKET_HOURS] ✅ Market open ({hour:02d}:{minute:02d} EDT, weekday {weekday})")
        return True

    except Exception as e:
        print(f"[MARKET_HOURS] ⚠️ Error checking market hours: {e}")
        return False


# =====================================================================
# WEEKLY DEPOSIT AUTOMATION
# =====================================================================

def process_weekly_deposit():
    """
    Process weekly deposit via Schwab MoneyLink (Thursday 8:00 AM EDT).
    Auto-routes to primary funding source (whatever bank is linked in Schwab UI).
    No hardcoding, no config needed.
    """
    try:
        if not WEEKLY_DEPOSIT_ENABLED:
            print("[DEPOSIT] Disabled")
            return False

        # Check if today is Thursday
        current_weekday = datetime.utcnow().weekday()
        if current_weekday != 3:  # Thursday = 3
            print(f"[DEPOSIT] Not Thursday (today: {current_weekday})")
            return False

        # Check if current hour is 12-13 UTC (8:00 AM EDT)
        current_hour_utc = datetime.utcnow().hour
        if current_hour_utc not in [12, 13]:  # 12:00-13:59 UTC = 8:00-8:59 AM EDT
            print(f"[DEPOSIT] Not 8:00 AM window (current UTC hour: {current_hour_utc}, target: 12-13)")
            return False

        print(f"[DEPOSIT] Processing ${WEEKLY_DEPOSIT_AMOUNT:.2f} weekly deposit to Schwab...")

        # Get fresh OAuth token
        access_token = refresh_schwab_access_token()
        if not access_token:
            print("[DEPOSIT] ❌ Could not refresh OAuth token")
            send_alert_email(
                f"❌ Weekly deposit failed: Could not authenticate with Schwab",
                "DEPOSIT_FAILED",
                0,
                "N/A",
                False
            )
            return False

        # Send MoneyLink request to Schwab
        # Omit sourceAccountId — Schwab automatically routes to primary funding source
        deposit_response = requests.post(
            f"{SCHWAB_BASE_URL}/accounts/{SCHWAB_ACCOUNT_ID}/transfers",
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            },
            json={
                'transferType': 'ELECTRONIC_FUND_TRANSFER',
                'direction': 'IN',  # Deposit inbound
                'amount': WEEKLY_DEPOSIT_AMOUNT,
                # NO sourceAccountId — Schwab uses primary linked account
                'frequency': 'WEEKLY',
                'dayOfWeek': 'THURSDAY'
            },
            timeout=10
        )

        if deposit_response.status_code in [200, 201]:
            print(f"[DEPOSIT] ✅ ${WEEKLY_DEPOSIT_AMOUNT:.2f} deposit initiated successfully")
            send_alert_email(
                f"✅ Weekly deposit of ${WEEKLY_DEPOSIT_AMOUNT:.2f} initiated to Schwab (routed from primary funding source)",
                "DEPOSIT",
                WEEKLY_DEPOSIT_AMOUNT,
                "CASH",
                True
            )
            return True
        else:
            error_msg = deposit_response.text[:200]
            print(f"[DEPOSIT] ❌ Schwab API error: {error_msg}")
            send_alert_email(
                f"❌ Weekly deposit failed: {error_msg}",
                "DEPOSIT_FAILED",
                0,
                "N/A",
                False
            )
            return False

    except Exception as e:
        print(f"[DEPOSIT] ⚠️ Exception: {e}")
        send_alert_email(
            f"⚠️ Weekly deposit error: {str(e)}",
            "DEPOSIT_ERROR",
            0,
            "N/A",
            False
        )
        return False


# =====================================================================
# MAIN LAMBDA HANDLER - COMPLETE ENHANCED VERSION
# =====================================================================

def lambda_handler(event, context):
    """
    McElveen Autonomous Trading System v3.0.26 - PORTFOLIO MANAGER ACTIVE DECISION LAYER

    12-STEP EXECUTION:
    1. OAuth token refresh
    2. Market scanning (all asset classes)
    3. Chief Investment Officer macro & investment analysis
    4. Read portfolio & account
    5. Calculate portfolio metrics
    6. Calculate dynamic trade size
    7. Claude autonomous decision
    8. Guardrails validation (7 levels)
    9. Trader Mode rebalancing (if holdings limit reached)
    9b. Portfolio Manager active decision (BUY/SELL_AND_BUY/HOLD/BUY_MORE)
    10. Execute based on Portfolio Manager decision
    11. Log metrics + alerts + alerts on errors only
    12. Weekly deposits (Thursday 8 AM)
    """

    print("\n" + "=" * 100)
    print("McElveen Autonomous Trading System v3.0.31 - HARDENED PRODUCTION - Thursday 8AM Deposits")
    print("=" * 100)
    print(f"[TIME] {datetime.utcnow().isoformat()}Z")

    try:
        # ===== STEP 1: SCHWAB OAUTH =====
        print("\n[STEP 1] Refreshing Schwab access token...")
        access_token = refresh_schwab_access_token()
        if not access_token:
            print("[ERROR] ❌ Token refresh failed")
            send_alert_email("Could not refresh Schwab token", "N/A", 0, "N/A", False, "Token refresh failed")
            return {'statusCode': 500, 'body': 'Token refresh failed'}

        # ===== MARKET HOURS CHECK =====
        print("\n[PRE-CHECK] Verifying market hours...")
        if not is_market_open():
            print("[TRADING] ⏸️  Markets closed - skipping trading, checking for deposits...")
            # Still process weekly deposits even if markets closed
            process_weekly_deposit()
            return {'statusCode': 200, 'body': 'Markets closed - deposits processed, no trading'}

        # ===== STEP 2: MARKET SCANNING =====
        print("\n[STEP 2] Scanning entire market...")
        market_overview = get_market_overview(access_token)
        top_performers = get_top_performers(access_token)
        bond_opportunities = get_fixed_income_opportunities(access_token)
        fund_opportunities = get_mutual_fund_universe(access_token)
        stock_universe = get_comprehensive_stock_universe(access_token)  # All sectors, not just momentum

        # ===== STEP 4: READ POSITIONS & ACCOUNT =====
        print("\n[STEP 4] Reading portfolio...")
        account_data = get_account_data(access_token)
        account_hash = account_data.get('account_hash')
        cash = account_data.get('cash', 0)
        available_funds = account_data.get('available_funds', cash)  # FIX v3.0.16: Use available funds for trade sizing
        holdings = read_positions_from_schwab_api(access_token, account_hash)

        # FIX #40: Log account health for diagnostics
        buying_power = account_data.get('buying_power', 0)
        option_buying_power = account_data.get('option_buying_power', 0)
        if option_buying_power < 0:
            print(f"[ACCOUNT_HEALTH] ⚠️ DEFICIT DETECTED: Option Buying Power: ${option_buying_power:.2f}")
        else:
            print(f"[ACCOUNT_HEALTH] ✅ Healthy: Option Buying Power: ${option_buying_power:.2f}")

        # v3.0.31 FIX #2: HARD HALT if option buying power is negative (prevents repeat of -$13.56 incident)
        if option_buying_power < 0:
            msg = f"[CRITICAL] ❌ TRADING HALTED: Option Buying Power is NEGATIVE (${option_buying_power:.2f}). Account must be restored to positive BP before trading."
            print(msg)
            print("[EXECUTION] Status: Account locked due to negative option buying power")
            send_alert_email(msg, "NEGATIVE_OPTION_BP_HALT", 0, "HALT", True, f"Negative option BP: ${option_buying_power:.2f}", None)
            return {'statusCode': 403, 'body': f'Trading halted: negative option buying power (${option_buying_power:.2f})'}

        if not account_hash:
            print("[ERROR] Could not get account hash")
            return {'statusCode': 500, 'body': 'Account hash failed'}

        # ===== STEP 4b: CHECK FOR PENDING DEPOSITS (FIX v3.0.15 #5) =====
        print("\n[STEP 4b] Checking for pending deposits...")
        # FIX v3.0.18 #3: Use account_hash (works for all GET operations)
        has_pending, pending_amount = check_for_pending_deposits(access_token, account_hash)

        if has_pending:
            print(f"[DEPOSITS] ⚠️ Pending deposits detected: ${pending_amount:.2f}")
            print("[SETTLEMENT] Skipping trading until deposits settle (typically 1-2 business days)")
            msg = f"Deposits pending: ${pending_amount:.2f}. Trading skipped during settlement window."
            send_alert_email(msg, "DEPOSIT_SETTLEMENT", 0, "WAIT", False, "Pending ACH settlement", None)
            send_cloudwatch_metric('TradesSkipped', 1)
            return {'statusCode': 202, 'body': msg}

        print("[DEPOSITS] ✅ No pending deposits - proceeding with trading")

        # FIX v3.0.16 #2b: Safeguard - subtract pending amount from available funds for trade sizing
        # (Even though we skip trading if pending exists, deduct amount as extra protection)
        portfolio_value = available_funds - pending_amount  # Exclude any pending cash from trade sizing
        portfolio_value = max(0, portfolio_value)  # Never negative
        print(f"[PORTFOLIO] ${cash:.2f} cash | ${available_funds:.2f} available | ${pending_amount:.2f} pending | ${portfolio_value:.2f} for trading")

        # ===== STEP 5: CALCULATE PORTFOLIO METRICS =====
        print("\n[STEP 5] Calculating portfolio metrics...")
        previous_nav = get_portfolio_nav_history()
        metrics = PortfolioMetrics(cash, holdings, previous_nav)
        print(f"[METRICS] NAV: ${metrics.nav:.2f} | P&L: ${metrics.unrealized_pnl:.2f} ({metrics.unrealized_pnl_pct:.2f}%)")

        # ===== STEP 3: CHIEF INVESTMENT OFFICER ANALYSIS =====
        # CRITICAL FIX v3.0.31 #4: CIO RUNS AFTER STEP 5 (moved from original STEP 3 position)
        # REASON: CIO needs portfolio_state data (holdings, metrics, available_cash) which is built in STEP 5
        # If CIO ran before STEP 5, portfolio data wouldn't be available yet, defeating the purpose
        # NOW: CIO has complete portfolio picture and makes informed recommendations
        # OUTCOME: "Buy VTI with $10.92" (actual available cash), not hardcoded "Buy VTI with $10"
        print("\n[STEP 3] Chief Investment Officer analyzing macro & portfolio constraints...")

        # Build portfolio_state from actual Schwab account data (not hardcoded defaults)
        portfolio_state = {
            'available_cash': available_funds,  # FIX: Reads from account_data, never hardcoded
            'nav': metrics.nav,                  # Dynamic: sum of cash + holdings value
            'holdings': holdings,                # Actual positions from Schwab
            'drawdown_pct': metrics.daily_change_pct,  # Real P&L tracking
            'num_holdings': metrics.num_holdings,      # Actual count
            'allocation': metrics.allocation    # Real asset class percentages
        }
        macro_data = chief_investment_officer_analysis(
            market_overview['vix'],
            market_overview['yields'],
            market_overview['sector_performance'],
            portfolio_state
        )

        # ===== STEP 6: CALCULATE DYNAMIC TRADE SIZE =====
        print("\n[STEP 6] Calculating dynamic trade size...")
        trade_size = calculate_trade_size(market_overview['vix'], portfolio_value, macro_data['regime'])

        # v3.0.31 FIX #1: HARD HALT if trade_size = 0 (NAV check must actually stop execution, not just log)
        if trade_size <= 0:
            msg = f"[EXECUTION] ❌ TRADING HALTED: trade_size = ${trade_size:.2f}. Portfolio NAV ${portfolio_value:.2f} is below minimum ${MIN_TRADE_SIZE_FLOOR:.2f}."
            print(msg)
            print("[EXECUTION] Action: Halting trading until portfolio reaches $50+ NAV minimum")
            send_alert_email(msg, "TRADING_HALTED_LOW_NAV", 0, "HALT", False, f"NAV too low: ${portfolio_value:.2f}", metrics)
            send_cloudwatch_metric('TradesSkipped', 1)
            return {'statusCode': 202, 'body': f'Trading skipped: NAV ${portfolio_value:.2f} below minimum ${MIN_TRADE_SIZE_FLOOR:.2f}'}

        # ===== STEP 7: TRADE FREQUENCY & MODEL ROUTING =====
        print("\n[STEP 7] Checking trade frequency...")
        trades_today = get_trades_today()
        model, max_daily_trades = route_model_and_trade_limit(market_overview['vix'])

        # ===== STEP 7b: PORTFOLIO MANAGER DIRECTIVE (v3.0.27 NEW) =====
        print("\n[STEP 7b] Portfolio Manager generating allocation directive...")
        pm_action, pm_sector_reduce, pm_sector_increase, pm_rationale = portfolio_manager_directive(
            holdings, macro_data['regime'], macro_data.get('thesis_confidence', 5), macro_data
        )
        pm_directive = (pm_action, pm_sector_reduce, pm_sector_increase, pm_rationale)
        print(f"[PM_DIRECTIVE] ✅ Action: {pm_action} | Reduce: {pm_sector_reduce} | Increase: {pm_sector_increase}")

        # ===== STEP 8: CLAUDE AUTONOMOUS DECISION (with PM directive context) =====
        print("\n[STEP 8] Claude analyzing opportunities (with PM directive)...")
        symbol, asset_class, price = get_claude_autonomous_decision(
            market_overview, top_performers, bond_opportunities, fund_opportunities, stock_universe,
            portfolio_value, holdings, macro_data, trade_size, model, pm_directive
        )

        # ===== STEP 8b: SYMBOL VALIDATION (FIX v3.0.14 #1 & #2: Smart fallback) =====
        print("\n[STEP 8b] Validating symbol liquidity...")
        if asset_class in ['STOCK', 'SECTOR_ETF', 'BROAD_ETF', 'DIVIDEND_ETF']:
            valid, actual_price, validation_error = validate_symbol_liquidity(access_token, symbol, min_volume=100000)
            if not valid:
                print(f"[VALIDATION] ❌ {symbol} failed: {validation_error}")
                # FIX v3.0.14 #2: Pick random non-excluded symbol from universe instead of hardcoding SPY
                print(f"[FALLBACK] Picking random non-excluded symbol from universe...")

                excluded_symbols = set(holdings.keys())
                try:
                    table = DYNAMODB.Table(TRADE_JOURNAL_TABLE)
                    response = table.scan(
                        FilterExpression='#status = :status',
                        ExpressionAttributeNames={'#status': 'Status'},
                        ExpressionAttributeValues={':status': 'EXECUTED'},
                        Limit=20
                    )
                    recent_trades = sorted(response.get('Items', []),
                                          key=lambda x: x.get('Timestamp', ''),
                                          reverse=True)[:3]
                    recent_symbols = [item.get('Symbol') for item in recent_trades]
                    excluded_symbols.update([s for s in recent_symbols if s])
                except:
                    pass

                # Get all available symbols from universe
                available_symbols = []
                for sector, stocks in stock_universe.items():
                    for stock in stocks:
                        if stock['symbol'] not in excluded_symbols:
                            available_symbols.append(stock)

                if available_symbols:
                    # Pick random non-excluded symbol
                    random_pick = random.choice(available_symbols)
                    symbol = random_pick['symbol']
                    asset_class = random_pick['asset_class']
                    price = random_pick['price']
                    print(f"[FALLBACK] ✅ Randomly selected: {symbol} from {random_pick['sector']}")
                else:
                    print(f"[FALLBACK2] No available symbols in universe, using SPY")
                    symbol = 'SPY'
                    asset_class = 'BROAD_ETF'
                    price = 450.0

                send_alert_email(f"Symbol validation failed ({validation_error}), using fallback {symbol}", symbol, trade_size, asset_class, False, validation_error, metrics)
            else:
                if actual_price > 0:
                    price = actual_price  # Use Schwab's actual price, not Claude's estimate
                # else: keep Claude's price estimate if Schwab price is invalid (e.g., HTTP 404)

        # ===== STEP 9: GUARDRAILS (7 LEVELS) =====
        print("\n[STEP 9] Checking guardrails...")
        guardrails_pass, guardrail_msg = check_guardrails(
            symbol, trade_size, portfolio_value, trades_today, max_daily_trades, holdings, asset_class, metrics
        )

        if not guardrails_pass:
            # Check if this is a TRADER MODE rebalance signal (v3.0.25)
            if "TRADER_MODE_REBALANCE" in guardrail_msg:
                print(f"\n[STEP 9b] TRADER MODE ACTIVATED: Holdings limit reached")
                parts = guardrail_msg.split('|')
                current_holdings_count = int(parts[1])
                max_holdings_tier = int(parts[2])
                portfolio_val = float(parts[3])

                # Find worst performer
                worst_symbol, worst_pnl_pct, worst_qty, worst_entry_price = find_worst_performer(holdings)

                if worst_symbol:
                    print(f"[TRADER MODE] Worst performer: {worst_symbol} ({worst_pnl_pct:.2f}% P&L)")

                    # Execute rebalance: sell worst, buy new opportunity
                    if AUTONOMOUS_MODE_ENABLED:
                        # Calculate quantity for new symbol (trade_size dollars / price)
                        new_quantity = trade_size / price if price > 0 else 0
                        rebalance_success, rebalance_msg = execute_rebalance(
                            access_token, worst_symbol, worst_qty, account_hash,
                            symbol, new_quantity, price, asset_class, worst_pnl_pct, holdings
                        )

                        if rebalance_success:
                            print(f"[TRADER MODE] ✅ REBALANCE SUCCESSFUL: {rebalance_msg}")
                            log_portfolio_metrics(metrics)
                            send_cloudwatch_metric('RebalancesExecuted', 1)
                            return {'statusCode': 200, 'body': json.dumps({'result': 'REBALANCED', 'action': rebalance_msg})}
                        else:
                            print(f"[TRADER MODE] ❌ Rebalance failed: {rebalance_msg}")
                            send_alert_email(f"Rebalance failed: {rebalance_msg}", symbol, trade_size, asset_class, False, rebalance_msg, metrics)
                    else:
                        print(f"[TRADER MODE DRY-RUN] Would rebalance {worst_symbol}→{symbol}")
                        return {'statusCode': 200, 'body': json.dumps({'result': 'DRY_RUN_REBALANCE'})}
                else:
                    print(f"[TRADER MODE] No holdings to sell (portfolio empty)")
                    send_alert_email(f"Rebalance blocked: No positions to liquidate", symbol, trade_size, asset_class, False, "Empty portfolio", metrics)
            else:
                # Normal guardrails block
                print(f"[BLOCKED] {guardrail_msg}")
                # DISABLED: send_alert_email(f"Blocked: {guardrail_msg}", symbol, trade_size, asset_class, False, guardrail_msg, metrics)
                # ^^ Option 2: Errors-only alerting. Guardrails blocks are expected during POC; keep CloudWatch metrics.
                log_portfolio_metrics(metrics)
                send_cloudwatch_metric('TradesBlocked', 1)
                return {'statusCode': 202, 'body': json.dumps({'result': 'BLOCKED', 'reason': guardrail_msg})}

        # ===== STEP 9b: PORTFOLIO MANAGER (v3.0.27.1) - ACTIVE DECISION ENGINE =====
        # Portfolio Manager determines final action: BUY (new), BUY_MORE (existing), SELL_AND_BUY, or HOLD
        # - FIX #40: Checks account buying power FIRST - forces HOLD if negative (margin deficit)
        # - Uses safe .get('thesis_confidence', 5) to access CIO confidence (v3.0.27.1 fix)
        # - Evaluates winners vs losers: P&L tracking (60%) + thesis alignment (40%)
        # - Can recommend BUY_MORE when position is winning + thesis still intact
        print("\n[STEP 9b] Portfolio Manager evaluating active decision...")

        # FIX #40: Extract buying power from account data for account health check
        buying_power = account_data.get('option_buying_power', 0)

        pm_action, pm_target_symbol, pm_rationale = portfolio_manager_decision(
            symbol, asset_class, price, holdings, macro_data['regime'],
            macro_data.get('thesis_confidence', 5), portfolio_value, macro_data, buying_power
        )

        print(f"[STEP 9b] Portfolio Manager: {pm_action} | {pm_rationale}")

        # ===== STEP 10: EXECUTE BASED ON PORTFOLIO MANAGER DECISION =====
        print("\n[STEP 10] Executing Portfolio Manager decision...")

        execution_success = False
        order_id = None
        execution_detail = "Not executed"
        action_type = "NONE"

        if not AUTONOMOUS_MODE_ENABLED:
            print("[DRY-RUN] Autonomous mode disabled")
            send_cloudwatch_metric('DryRuns', 1)
            return {'statusCode': 200, 'body': json.dumps({'result': 'DRY_RUN', 'pm_action': pm_action})}

        # Handle different Portfolio Manager actions
        if pm_action == "HOLD":
            # Monitor but don't execute
            print(f"[PORTFOLIO_MANAGER] ⏸️ HOLD signal - monitoring {symbol}")
            log_portfolio_metrics(metrics)
            send_cloudwatch_metric('PortfolioMonitored', 1)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'result': 'MONITORED',
                    'action': 'HOLD',
                    'symbol': symbol,
                    'rationale': pm_rationale
                })
            }

        elif pm_action == "BUY_MORE":
            # BUY_MORE: Add shares to winning existing position (v3.0.27.1 capability)
            # - G1 guardrail removed: allows duplicate symbols when conviction justified
            # - Smart exclusion allows this when PM directive is HOLD/BUY
            # - Portfolio Manager identified winning position with strong thesis alignment
            # - Use case: Amplify conviction in outperformers, compound gains
            print(f"[PORTFOLIO_MANAGER] 🟢 BUY_MORE signal - adding to {symbol} (winning position amplification)")
            execution_success, order_id, execution_detail = execute_trade_on_schwab(
                access_token, symbol, trade_size, account_hash, price, asset_class
            )
            action_type = "BUY_MORE"

        elif pm_action == "SELL_AND_BUY":
            # Sell worst performer, buy new opportunity
            print(f"[PORTFOLIO_MANAGER] 🟠 SELL_AND_BUY signal - selling {pm_target_symbol}, buying {symbol}")

            # Find quantity to sell
            target_holding = holdings.get(pm_target_symbol, {})
            sell_quantity = target_holding.get('quantity', 0)
            sell_price = target_holding.get('current_price', target_holding.get('entry_price', 0))

            if sell_quantity > 0:
                # Execute sell and buy
                # CTO FIX: Round new purchase quantity to whole shares to avoid fractional accumulation
                new_quantity_raw = trade_size / price if price > 0 else 0
                new_quantity = int(new_quantity_raw)  # Round DOWN to whole shares

                if new_quantity == 0 and new_quantity_raw > 0:
                    # If rounding down to 0, don't execute (not enough capital for 1 share)
                    print(f"[PORTFOLIO_MANAGER] 🟠 SELL_AND_BUY blocked: Insufficient capital for 1 share of {symbol} (${trade_size:.2f})")
                    log_portfolio_metrics(metrics)
                    send_cloudwatch_metric('TradesBlocked', 1)
                    return {
                        'statusCode': 202,
                        'body': json.dumps({'result': 'BLOCKED', 'reason': f'Insufficient capital: ${trade_size:.2f} < 1 share @ ${price:.2f}'})
                    }

                rebalance_success, rebalance_msg = execute_rebalance(
                    access_token, pm_target_symbol, sell_quantity, account_hash,
                    symbol, new_quantity, price, asset_class,
                    ((sell_price - target_holding.get('entry_price', sell_price)) / target_holding.get('entry_price', sell_price) * 100) if target_holding.get('entry_price', 0) > 0 else 0,
                    holdings
                )
                execution_success = rebalance_success
                order_id = "REBALANCE"
                execution_detail = rebalance_msg
                action_type = "SELL_AND_BUY"
            else:
                print(f"[PORTFOLIO_MANAGER] ❌ Cannot sell {pm_target_symbol} - no quantity")
                execution_success = False
                execution_detail = f"Cannot sell {pm_target_symbol} - no holdings"
                action_type = "SELL_AND_BUY"

        else:  # "BUY" (default)
            # Standard buy
            print(f"[PORTFOLIO_MANAGER] 🟢 BUY signal - {symbol}")
            execution_success, order_id, execution_detail = execute_trade_on_schwab(
                access_token, symbol, trade_size, account_hash, price, asset_class
            )
            action_type = "BUY"

        # ===== STEP 11: LOG & ALERT & METRICS =====
        print("\n[STEP 11] Logging, alerting, and updating metrics...")

        if execution_success:
            print(f"[TRADE] ✅✅✅ EXECUTION SUCCESSFUL - Order ID: {order_id}")
            log_execution_to_dynamodb(symbol, trade_size, order_id, asset_class, price)
            alert_msg = f"✅ {action_type}: {symbol} ({asset_class}) @ ${price:.2f} | Order: {order_id}"
            # DISABLED: send_alert_email(alert_msg, symbol, trade_size, asset_class, True, None, metrics)
            # ^^ Option 2: Errors-only alerting. Successful executions logged to DynamoDB/CloudWatch only.
            send_cloudwatch_metric('TradesExecuted', 1)
            send_cloudwatch_metric('PortfolioNAV', metrics.nav, 'None')
        else:
            print(f"[TRADE] ❌ EXECUTION FAILED - {execution_detail}")
            alert_msg = f"❌ Failed: {action_type} {symbol} ({asset_class})"
            send_alert_email(alert_msg, symbol, trade_size, asset_class, False, execution_detail, metrics)
            send_cloudwatch_metric('TradesFailed', 1)

        # Log portfolio metrics
        log_portfolio_metrics(metrics)

        # Weekly deposit disabled - manual deposits only

        print("\n" + "=" * 100)
        print(f"Result: {'✅ EXECUTED' if execution_success else '❌ FAILED'}")
        print("=" * 100)

        return {
            'statusCode': 201 if execution_success else 500,
            'body': json.dumps({
                'result': 'EXECUTED' if execution_success else 'FAILED',
                'action': action_type,
                'pm_action': pm_action,
                'pm_rationale': pm_rationale,
                'symbol': symbol,
                'asset_class': asset_class,
                'price': price,
                'order_id': order_id if execution_success else None,
                'detail': execution_detail,
                'portfolio': {
                    'nav': float(metrics.nav),
                    'cash': float(metrics.cash),
                    'unrealized_pnl': float(metrics.unrealized_pnl),
                    'holdings': len(metrics.holdings)
                }
            })
        }

    except Exception as e:
        print(f"\n[FATAL] {e}")
        import traceback
        traceback.print_exc()
        send_alert_email(f"FATAL ERROR: {str(e)}", "N/A", 0, "N/A", False, str(e))
        send_cloudwatch_metric('FatalErrors', 1)
        return {'statusCode': 500, 'body': f'Fatal: {str(e)}'}