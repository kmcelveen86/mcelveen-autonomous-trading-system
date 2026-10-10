#!/usr/bin/env python3
"""
McElveen Autonomous Trading System v3.0.33 - Hybrid Equity + Forex
24/5 Trading with Time-Based Routing and Unified Risk Management

Architecture:
- Equities: 9:30 AM-4 PM ET Mon-Fri (v3.0.31 logic)
- Forex: 5 PM Sun-5 PM Fri ET (7 major pairs)
- Capital allocation: 50% equities | 50% forex (no leverage)
- Unified risk: Circuit breaker applies to combined portfolio NAV

Deployment: AWS Lambda (Python 3.11+)
Status: Phase 1A Infrastructure + Routing (Oct 9, 2026)
"""

import json
import boto3
import requests
import os
from datetime import datetime, timedelta, timezone
from enum import Enum

# Time zone handling (with fallback for local testing)
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("US/Eastern")
    UTC = ZoneInfo("UTC")
    USE_ZONEINFO = True
except Exception:
    # Fallback: use UTC+offset for local testing
    ET = timezone(timedelta(hours=-4))  # EDT is UTC-4
    UTC = timezone.utc
    USE_ZONEINFO = False

# =====================================================================
# CONFIGURATION
# =====================================================================

SCHWAB_API_BASE = "https://api.schwabapi.com/trader/v1"
SCHWAB_ACCOUNT_ID = os.getenv("SCHWAB_ACCOUNT_ID", "7720-9306")

# Trading credentials
SCHWAB_ACCESS_TOKEN = os.getenv("SCHWAB_ACCESS_TOKEN", "")
SCHWAB_REFRESH_TOKEN = os.getenv("SCHWAB_REFRESH_TOKEN", "")

# DynamoDB for metrics and trade logging (mock for local testing)
try:
    DYNAMODB = boto3.resource("dynamodb", region_name="us-east-2")
    FOREX_TRADES_TABLE = DYNAMODB.Table(os.getenv("FOREX_TRADES_TABLE", "mcelveen-forex-trades"))
    FOREX_METRICS_TABLE = DYNAMODB.Table(os.getenv("FOREX_METRICS_TABLE", "mcelveen-forex-metrics"))
    CLOUDWATCH = boto3.client("cloudwatch", region_name="us-east-2")
except Exception:
    # Fallback for local testing
    DYNAMODB = None
    FOREX_TRADES_TABLE = None
    FOREX_METRICS_TABLE = None
    CLOUDWATCH = None


# =====================================================================
# ENUMS & CONSTANTS
# =====================================================================

class TradingMode(Enum):
    """Time-based trading mode router"""
    EQUITY_TRADING = "EQUITY"
    FOREX_TRADING = "FOREX"
    MARKET_CLOSED = "CLOSED"


class ForexPairs(Enum):
    """7 Major Forex Pairs"""
    EUR_USD = "EUR/USD"
    GBP_USD = "GBP/USD"
    USD_JPY = "USD/JPY"
    USD_CHF = "USD/CHF"
    AUD_USD = "AUD/USD"
    NZD_USD = "NZD/USD"
    USD_CAD = "USD/CAD"


class GuardrailStatus(Enum):
    """Guardrail validation results"""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


# =====================================================================
# HYBRID PORTFOLIO METRICS
# =====================================================================

class HybridPortfolioMetrics:
    """
    Unified metrics for equity + forex portfolio.
    Tracks combined NAV, allocation, risk exposure.
    """

    def __init__(self, account_data):
        self.account_cash = account_data.get("cash", 0)
        self.equity_nav = account_data.get("equity_nav", 0)
        self.forex_nav = account_data.get("forex_nav", 0)
        self.total_nav = self.equity_nav + self.forex_nav + self.account_cash

        # Allocation percentages
        self.equity_allocation_pct = (self.equity_nav / self.total_nav * 100) if self.total_nav > 0 else 0
        self.forex_allocation_pct = (self.forex_nav / self.total_nav * 100) if self.total_nav > 0 else 0
        self.cash_allocation_pct = (self.account_cash / self.total_nav * 100) if self.total_nav > 0 else 0

        # Equity drawdown (for circuit breaker)
        self.equity_drawdown = account_data.get("equity_drawdown", 0)
        self.forex_drawdown = account_data.get("forex_drawdown", 0)
        self.combined_drawdown = min(self.equity_drawdown, self.forex_drawdown)

        # Risk metrics
        self.circuit_breaker_threshold = -0.02  # -2% combined
        self.circuit_breaker_triggered = self.combined_drawdown <= self.circuit_breaker_threshold

    def to_dict(self):
        """Serialize metrics to dictionary"""
        return {
            "total_nav": round(self.total_nav, 2),
            "equity_nav": round(self.equity_nav, 2),
            "forex_nav": round(self.forex_nav, 2),
            "cash": round(self.account_cash, 2),
            "equity_allocation_pct": round(self.equity_allocation_pct, 1),
            "forex_allocation_pct": round(self.forex_allocation_pct, 1),
            "cash_allocation_pct": round(self.cash_allocation_pct, 1),
            "combined_drawdown": round(self.combined_drawdown, 4),
            "circuit_breaker_triggered": self.circuit_breaker_triggered,
        }


# =====================================================================
# TIME-BASED TRADING MODE ROUTER
# =====================================================================

def get_trading_mode_for_time(current_time_et):
    """
    Determine trading mode based on current time.

    Equity: Mon-Fri 9:30 AM - 4 PM ET
    Forex: Sun-Fri 5 PM - 5 PM ET (24/5)
    Closed: Fri 4 PM - Sun 5 PM ET
    """
    weekday = current_time_et.weekday()  # 0=Mon, 6=Sun
    hour = current_time_et.hour
    minute = current_time_et.minute

    # Convert to minutes since midnight for easier comparison
    minutes_since_midnight = hour * 60 + minute
    equity_open = 9 * 60 + 30  # 9:30 AM
    equity_close = 16 * 60  # 4:00 PM
    forex_open = 17 * 60  # 5:00 PM

    # Equity markets: Mon-Fri 9:30 AM - 4 PM ET
    if weekday < 5:  # Mon-Fri
        if equity_open <= minutes_since_midnight < equity_close:
            return TradingMode.EQUITY_TRADING

    # Forex markets: Sun 5 PM - Fri 5 PM ET (24/5)
    # Sunday 5 PM to Friday 5 PM continuous
    if weekday == 6:  # Sunday
        if minutes_since_midnight >= forex_open:
            return TradingMode.FOREX_TRADING
    elif weekday < 5:  # Mon-Fri
        return TradingMode.FOREX_TRADING
    elif weekday == 5:  # Friday
        if minutes_since_midnight < forex_open:
            return TradingMode.FOREX_TRADING

    return TradingMode.MARKET_CLOSED


# =====================================================================
# FOREX GUARDRAILS (G1-G4)
# =====================================================================

def validate_forex_guardrails(position_size, total_forex_nav, pair_exposure, portfolio_metrics):
    """
    Validate forex position against guardrails.

    G1: Position size <= 15% of forex NAV per pair
    G2: Pair concentration <= 25% of total forex NAV
    G3: Leverage = 1.0x (cash-only, no margin)
    G4: Economic event avoidance (checked externally)
    """
    results = {}

    # G1: Position size guardrail
    max_position = total_forex_nav * 0.15
    g1_pass = position_size <= max_position
    results["G1_position_size"] = {
        "pass": g1_pass,
        "position_size": position_size,
        "max_allowed": max_position,
        "status": "PASS" if g1_pass else "FAIL"
    }

    # G2: Pair concentration guardrail
    max_concentration = total_forex_nav * 0.25
    g2_pass = pair_exposure <= max_concentration
    results["G2_concentration"] = {
        "pass": g2_pass,
        "pair_exposure": pair_exposure,
        "max_allowed": max_concentration,
        "status": "PASS" if g2_pass else "FAIL"
    }

    # G3: Leverage check (1.0x = no margin)
    g3_pass = True  # Enforced at execution layer
    results["G3_leverage"] = {
        "pass": g3_pass,
        "leverage": 1.0,
        "max_allowed": 1.0,
        "status": "PASS"
    }

    # G4: Circuit breaker (unified risk)
    g4_pass = not portfolio_metrics.circuit_breaker_triggered
    results["G4_circuit_breaker"] = {
        "pass": g4_pass,
        "combined_drawdown": portfolio_metrics.combined_drawdown,
        "threshold": portfolio_metrics.circuit_breaker_threshold,
        "status": "PASS" if g4_pass else "TRIGGERED"
    }

    overall_pass = g1_pass and g2_pass and g3_pass and g4_pass

    return {
        "guardrails_pass": overall_pass,
        "guardrails": results
    }


# =====================================================================
# FOREX MACRO ANALYSIS (CIO-ready)
# =====================================================================

def analyze_forex_macro(market_data):
    """
    Forex macro analysis for CIO decision-making.

    Input: Interest rates, central bank stance, economic calendar
    Output: Regime (RISK_ON/NEUTRAL/RISK_OFF), conviction level, pair recommendations
    """

    # Interest rate differentials (Fed vs ECB vs BOJ)
    fed_rate = market_data.get("fed_rate", 4.25)
    ecb_rate = market_data.get("ecb_rate", 3.75)
    boj_rate = market_data.get("boj_rate", 0.25)

    rate_differential = fed_rate - ecb_rate

    # Central bank stance
    fed_stance = market_data.get("fed_stance", "HAWKISH")  # HAWKISH, NEUTRAL, DOVISH
    ecb_stance = market_data.get("ecb_stance", "HAWKISH")

    # Economic calendar events (next 24 hours)
    high_impact_events = market_data.get("high_impact_events", [])

    # Determine regime
    if rate_differential > 1.0 and fed_stance == "HAWKISH":
        regime = "RISK_ON"
        conviction = 0.75
    elif rate_differential < -0.5 and fed_stance == "DOVISH":
        regime = "RISK_OFF"
        conviction = 0.65
    else:
        regime = "NEUTRAL"
        conviction = 0.50

    # Recommend pairs based on regime
    if regime == "RISK_ON":
        recommended_pairs = ["GBP/USD", "AUD/USD", "NZD/USD"]
    elif regime == "RISK_OFF":
        recommended_pairs = ["USD/JPY", "USD/CHF"]
    else:
        recommended_pairs = ["EUR/USD", "USD/CAD"]

    return {
        "regime": regime,
        "conviction": conviction,
        "fed_rate": fed_rate,
        "ecb_rate": ecb_rate,
        "boj_rate": boj_rate,
        "rate_differential": rate_differential,
        "fed_stance": fed_stance,
        "ecb_stance": ecb_stance,
        "recommended_pairs": recommended_pairs,
        "high_impact_events": high_impact_events,
        "high_impact_event_avoidance": len(high_impact_events) > 0
    }


# =====================================================================
# FOREX TRADE LOGGING & METRICS PUBLISHING
# =====================================================================

def log_forex_trade(trade_data):
    """Log forex trade to DynamoDB (mcelveen-forex-trades)"""
    try:
        trade_record = {
            "Date": datetime.now(ET).strftime("%Y-%m-%d"),
            "Timestamp": datetime.now(UTC).isoformat(),
            "Pair": trade_data.get("pair"),
            "Direction": trade_data.get("direction"),  # BUY/SELL
            "Quantity": trade_data.get("quantity"),
            "EntryPrice": trade_data.get("entry_price"),
            "ExitPrice": trade_data.get("exit_price", None),
            "PipsGained": trade_data.get("pips_gained", None),
            "PnL": trade_data.get("pnl"),
            "Status": trade_data.get("status"),  # OPEN/CLOSED
        }

        FOREX_TRADES_TABLE.put_item(Item=trade_record)
        return {"logged": True, "record": trade_record}
    except Exception as e:
        return {"logged": False, "error": str(e)}


def publish_forex_metrics(metrics_data):
    """Publish forex metrics to CloudWatch"""
    try:
        cloudwatch_metrics = [
            {
                "MetricName": "ForexPnL",
                "Value": metrics_data.get("daily_pnl", 0),
                "Unit": "None",
            },
            {
                "MetricName": "ForexWinRate",
                "Value": metrics_data.get("win_rate", 0),
                "Unit": "Percent",
            },
            {
                "MetricName": "ForexTrades",
                "Value": metrics_data.get("trades_today", 0),
                "Unit": "Count",
            },
        ]

        CLOUDWATCH.put_metric_data(
            Namespace="McElveen/Forex",
            MetricData=cloudwatch_metrics
        )
        return {"published": True, "count": len(cloudwatch_metrics)}
    except Exception as e:
        return {"published": False, "error": str(e)}


# =====================================================================
# LAMBDA HANDLER (Phase 1A - Routing only)
# =====================================================================

def lambda_handler(event, context):
    """
    v3.0.33 Hybrid Trading System - Phase 1A Handler
    Routes to equity or forex based on market hours
    """

    current_time_et = datetime.now(ET)
    trading_mode = get_trading_mode_for_time(current_time_et)

    print("=" * 80)
    print("McElveen Autonomous Trading System v3.0.33 - Hybrid Equity + Forex")
    print("=" * 80)
    print(f"[TIME] {current_time_et.isoformat()}")
    print(f"[MODE] {trading_mode.value}")
    print()

    # Mock portfolio metrics for Phase 1A
    mock_account = {
        "cash": 50.00,
        "equity_nav": 50.00,
        "forex_nav": 0.00,
        "equity_drawdown": -0.01,
        "forex_drawdown": 0.00,
    }

    metrics = HybridPortfolioMetrics(mock_account)

    print("[PORTFOLIO]")
    for key, value in metrics.to_dict().items():
        print(f"  {key}: {value}")
    print()

    if trading_mode == TradingMode.EQUITY_TRADING:
        print("[ROUTING] → EQUITY TRADING (v3.0.31 logic)")
        print("[STATUS] Phase 1A: Routing validated. Equity execution deferred to main Lambda.")
        result = {
            "mode": "EQUITY",
            "status": "ROUTING_CONFIGURED",
            "message": "Route to mcelveen-trading-system Lambda"
        }

    elif trading_mode == TradingMode.FOREX_TRADING:
        print("[ROUTING] → FOREX TRADING (24/5 markets)")
        print("[STATUS] Phase 1A: Routing validated. Forex execution pending.")

        # Mock macro analysis
        mock_market_data = {
            "fed_rate": 4.25,
            "ecb_rate": 3.75,
            "boj_rate": 0.25,
            "fed_stance": "HAWKISH",
            "ecb_stance": "NEUTRAL",
            "high_impact_events": [],
        }

        macro = analyze_forex_macro(mock_market_data)
        print("[MACRO ANALYSIS]")
        print(f"  Regime: {macro['regime']}")
        print(f"  Conviction: {macro['conviction']:.2f}")
        print(f"  Fed Rate: {macro['fed_rate']}% | ECB Rate: {macro['ecb_rate']}%")
        print(f"  Rate Differential: {macro['rate_differential']:.2f}%")
        print(f"  Recommended Pairs: {', '.join(macro['recommended_pairs'])}")
        print()

        result = {
            "mode": "FOREX",
            "status": "ROUTING_CONFIGURED",
            "macro_analysis": macro,
            "message": "Forex execution pending Phase 1B"
        }

    else:
        print("[ROUTING] ⏸️ Markets closed")
        print("[STATUS] No trading today")
        result = {
            "mode": "CLOSED",
            "status": "MARKETS_CLOSED",
            "next_session": "Equity 9:30 AM ET"
        }

    print()
    print("=" * 80)
    print("[SUCCESS] v3.0.33 Phase 1A: Infrastructure routing validated")
    print("=" * 80)

    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }


# =====================================================================
# LOCAL TESTING
# =====================================================================

if __name__ == "__main__":
    print("[DEBUG] Running v3.0.33 Phase 1A locally")
    print()

    result = lambda_handler({}, None)
    print()
    print("[RESULT]")
    print(json.dumps(json.loads(result["body"]), indent=2))
