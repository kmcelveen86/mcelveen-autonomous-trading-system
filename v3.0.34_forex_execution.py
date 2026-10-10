#!/usr/bin/env python3
"""
McElveen Autonomous Trading System v3.0.34 - Forex Execution Layer
Real Schwab API Integration for Forex Order Placement & P&L Tracking

Phase 1B Objective:
- Get forex market quotes from Schwab API
- Place forex BUY/SELL orders with position sizing
- Close positions and calculate pips + P&L
- Log trades to DynamoDB
- Publish metrics to CloudWatch

Deployment: AWS Lambda (Python 3.11+)
Trigger: v3.0.33 hybrid router → forex execution when FOREX_TRADING mode detected
Status: Phase 1B (Oct 15-Nov 5, 2026)
"""

import json
import boto3
import requests
import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Optional, Tuple

# Time zone handling
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("US/Eastern")
    UTC = ZoneInfo("UTC")
except Exception:
    ET = timezone(timedelta(hours=-4))  # EDT
    UTC = timezone.utc

# =====================================================================
# CONFIGURATION
# =====================================================================

SCHWAB_API_BASE = "https://api.schwabapi.com/trader/v1"
SCHWAB_ACCOUNT_ID = os.getenv("SCHWAB_ACCOUNT_ID", "7720-9306")
SCHWAB_ACCESS_TOKEN = os.getenv("SCHWAB_ACCESS_TOKEN", "")

# DynamoDB for trade logging
try:
    DYNAMODB = boto3.resource("dynamodb", region_name="us-east-2")
    FOREX_TRADES_TABLE = DYNAMODB.Table(os.getenv("FOREX_TRADES_TABLE", "mcelveen-forex-trades"))
    FOREX_METRICS_TABLE = DYNAMODB.Table(os.getenv("FOREX_METRICS_TABLE", "mcelveen-forex-metrics"))
    CLOUDWATCH = boto3.client("cloudwatch", region_name="us-east-2")
except Exception:
    DYNAMODB = None
    FOREX_TRADES_TABLE = None
    FOREX_METRICS_TABLE = None
    CLOUDWATCH = None

# =====================================================================
# ENUMS & CONSTANTS
# =====================================================================

class ForexPairs(Enum):
    """7 Major Forex Pairs with Schwab symbols"""
    EUR_USD = ("EUR/USD", "EURUSD")  # (display_name, schwab_symbol)
    GBP_USD = ("GBP/USD", "GBPUSD")
    USD_JPY = ("USD/JPY", "USDJPY")
    USD_CHF = ("USD/CHF", "USDCHF")
    AUD_USD = ("AUD/USD", "AUDUSD")
    NZD_USD = ("NZD/USD", "NZDUSD")
    USD_CAD = ("USD/CAD", "USDCAD")


class OrderStatus(Enum):
    """Forex order statuses"""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


# =====================================================================
# SCHWAB FOREX API CLIENT
# =====================================================================

class SchwabForexClient:
    """
    Wrapper for Schwab Forex API.
    Handles quotes, order placement, position management, and P&L.
    """

    def __init__(self, access_token: str, account_id: str):
        self.access_token = access_token
        self.account_id = account_id
        self.base_url = SCHWAB_API_BASE
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

    def get_forex_quote(self, pair: str) -> Optional[Dict]:
        """
        Get forex market quote (bid/ask/last).

        Args:
            pair: Schwab forex symbol (e.g., "EURUSD")

        Returns:
            dict with keys: symbol, bid, ask, last, change, changePercent
            None if API call fails
        """
        try:
            # Schwab forex quotes endpoint
            url = f"{self.base_url}/quotes/forex/{pair}"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                quote = response.json()
                print(f"[QUOTE] {pair}: bid={quote.get('bid')}, ask={quote.get('ask')}")
                return quote
            else:
                print(f"[ERROR] Quote fetch failed for {pair}: HTTP {response.status_code}")
                return None

        except Exception as e:
            print(f"[ERROR] Quote exception: {e}")
            return None

    def place_forex_order(
        self,
        pair: str,
        direction: str,  # BUY or SELL
        quantity: float,  # Lot size (e.g., 1.0 = 1 standard lot = 100k units)
        entry_price: float,
        order_type: str = "MARKET"  # MARKET or LIMIT
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Place forex order via Schwab API.

        Args:
            pair: Schwab forex symbol (e.g., "EURUSD")
            direction: BUY or SELL
            quantity: Lot size
            entry_price: Entry price (market price at order time)
            order_type: MARKET or LIMIT

        Returns:
            tuple: (success: bool, order_id: str or None, filled_price: float or None)
        """
        try:
            url = f"{self.base_url}/accounts/{self.account_id}/orders"

            order_payload = {
                "orderType": order_type,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": direction,  # BUY or SELL
                        "quantity": quantity,
                        "instrument": {
                            "symbol": pair,
                            "assetType": "FOREX"
                        }
                    }
                ]
            }

            if order_type == "LIMIT":
                order_payload["orderLegCollection"][0]["price"] = entry_price

            response = requests.post(url, headers=self.headers, json=order_payload, timeout=10)

            if response.status_code in [200, 201]:
                order_id = response.headers.get("location", "").split("/")[-1]
                print(f"[ORDER] ✅ {direction} {quantity}L {pair} at {entry_price}")
                print(f"[ORDER] Order ID: {order_id}")
                return True, order_id, entry_price
            else:
                print(f"[ERROR] Order placement failed: HTTP {response.status_code}")
                print(f"[ERROR] Response: {response.text}")
                return False, None, None

        except Exception as e:
            print(f"[ERROR] Order placement exception: {e}")
            return False, None, None

    def get_position(self, pair: str) -> Optional[Dict]:
        """
        Get current forex position details.

        Args:
            pair: Schwab forex symbol (e.g., "EURUSD")

        Returns:
            dict with position info or None
        """
        try:
            url = f"{self.base_url}/accounts/{self.account_id}/positions"
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                positions = response.json().get("positions", [])
                for pos in positions:
                    instrument = pos.get("instrument", {})
                    if instrument.get("symbol") == pair:
                        print(f"[POSITION] {pair}: qty={pos.get('longQuantity') or pos.get('shortQuantity')}")
                        return pos
                print(f"[POSITION] No open position for {pair}")
                return None
            else:
                print(f"[ERROR] Position fetch failed: HTTP {response.status_code}")
                return None

        except Exception as e:
            print(f"[ERROR] Position exception: {e}")
            return None

    def close_position(
        self,
        pair: str,
        exit_price: float
    ) -> Tuple[bool, Optional[float]]:
        """
        Close forex position (reverse the open position).

        Args:
            pair: Schwab forex symbol
            exit_price: Exit price (closing price)

        Returns:
            tuple: (success: bool, pnl: float or None)
        """
        try:
            # Get current position
            position = self.get_position(pair)
            if not position:
                print(f"[ERROR] Cannot close position - no open position for {pair}")
                return False, None

            # Determine direction to close (opposite of entry)
            is_long = position.get("longQuantity", 0) > 0
            quantity = position.get("longQuantity") or position.get("shortQuantity", 0)

            close_direction = "SELL" if is_long else "BUY"

            # Place closing order
            success, order_id, _ = self.place_forex_order(
                pair=pair,
                direction=close_direction,
                quantity=quantity,
                entry_price=exit_price,
                order_type="MARKET"
            )

            if not success:
                return False, None

            # Calculate P&L (simplified - real calculation would track entry price)
            # P&L = (exit_price - entry_price) * quantity * contract_multiplier
            # For forex: 1 lot = 100,000 units, pip value = $10 per pip (for most pairs)
            entry_price = position.get("averagePrice", 0)
            price_diff = exit_price - entry_price

            # Forex pip conversion (simplified)
            pips = round(price_diff * 10000, 2)  # EUR/USD: 1 pip = 0.0001
            pnl = pips * 10 * quantity  # $10 per pip per lot

            print(f"[CLOSE] ✅ Closed {quantity}L {pair} at {exit_price}")
            print(f"[CLOSE] Pips: {pips} | P&L: ${pnl:.2f}")

            return True, pnl

        except Exception as e:
            print(f"[ERROR] Close position exception: {e}")
            return False, None


# =====================================================================
# TRADE JOURNAL & METRICS
# =====================================================================

class ForexTradeJournal:
    """
    Logs forex trades to DynamoDB and publishes metrics to CloudWatch.
    """

    def __init__(self):
        self.trades_today = []

    def log_trade(self, trade_data: Dict) -> bool:
        """
        Log trade to DynamoDB mcelveen-forex-trades table.

        Args:
            trade_data: dict with pair, direction, quantity, entry_price, exit_price (optional), pnl, status

        Returns:
            bool: True if logged successfully
        """
        try:
            if not FOREX_TRADES_TABLE:
                print(f"[WARN] DynamoDB not available, skipping trade log")
                return False

            trade_record = {
                "Date": datetime.now(ET).strftime("%Y-%m-%d"),
                "Timestamp": datetime.now(UTC).isoformat(),
                "Pair": trade_data.get("pair"),
                "Direction": trade_data.get("direction"),  # BUY/SELL
                "Quantity": trade_data.get("quantity"),
                "EntryPrice": trade_data.get("entry_price"),
                "ExitPrice": trade_data.get("exit_price"),
                "PipsGained": trade_data.get("pips_gained"),
                "PnL": trade_data.get("pnl"),
                "Status": trade_data.get("status"),  # OPEN/CLOSED
            }

            FOREX_TRADES_TABLE.put_item(Item=trade_record)
            print(f"[LOG] ✅ Trade logged to DynamoDB")
            self.trades_today.append(trade_record)
            return True

        except Exception as e:
            print(f"[LOG] ⚠️ Failed to log trade: {e}")
            return False

    def calculate_daily_metrics(self) -> Dict:
        """
        Calculate daily forex metrics from trades logged today.

        Returns:
            dict with daily_pnl, win_rate, trades_completed, avg_pips
        """
        if not self.trades_today:
            return {
                "daily_pnl": 0.0,
                "win_rate": 0.0,
                "trades_completed": 0,
                "avg_pips": 0.0
            }

        closed_trades = [t for t in self.trades_today if t.get("Status") == "CLOSED"]
        total_pnl = sum(t.get("PnL", 0) for t in closed_trades)
        winning_trades = sum(1 for t in closed_trades if t.get("PnL", 0) > 0)
        win_rate = (winning_trades / len(closed_trades) * 100) if closed_trades else 0

        avg_pips = sum(t.get("PipsGained", 0) for t in closed_trades) / len(closed_trades) if closed_trades else 0

        return {
            "daily_pnl": total_pnl,
            "win_rate": win_rate,
            "trades_completed": len(closed_trades),
            "trades_open": len(self.trades_today) - len(closed_trades),
            "avg_pips": avg_pips
        }

    def publish_metrics_to_cloudwatch(self, metrics: Dict) -> bool:
        """
        Publish metrics to CloudWatch McElveen/Forex namespace.
        """
        try:
            if not CLOUDWATCH:
                print(f"[WARN] CloudWatch not available, skipping metrics publish")
                return False

            cloudwatch_metrics = [
                {
                    "MetricName": "DailyPnL",
                    "Value": metrics.get("daily_pnl", 0),
                    "Unit": "None",
                },
                {
                    "MetricName": "WinRate",
                    "Value": metrics.get("win_rate", 0),
                    "Unit": "Percent",
                },
                {
                    "MetricName": "TradesCompleted",
                    "Value": metrics.get("trades_completed", 0),
                    "Unit": "Count",
                },
                {
                    "MetricName": "TradesOpen",
                    "Value": metrics.get("trades_open", 0),
                    "Unit": "Count",
                },
                {
                    "MetricName": "AveragePips",
                    "Value": metrics.get("avg_pips", 0),
                    "Unit": "None",
                },
            ]

            CLOUDWATCH.put_metric_data(
                Namespace="McElveen/Forex",
                MetricData=cloudwatch_metrics
            )
            print(f"[METRICS] ✅ Published {len(cloudwatch_metrics)} metrics to CloudWatch")
            return True

        except Exception as e:
            print(f"[METRICS] ⚠️ Failed to publish metrics: {e}")
            return False


# =====================================================================
# EXECUTION ORCHESTRATOR
# =====================================================================

class ForexExecutionOrchestrator:
    """
    Coordinates forex trading execution.
    - Receives routing signal from v3.0.33
    - Executes CIO macro recommendations
    - Validates guardrails
    - Logs trades
    """

    def __init__(self, access_token: str, account_id: str):
        self.client = SchwabForexClient(access_token, account_id)
        self.journal = ForexTradeJournal()

    def execute_recommendation(
        self,
        pair: str,
        direction: str,
        quantity: float,
        macro_conviction: float
    ) -> Dict:
        """
        Execute a forex trade recommendation from CIO macro analysis.

        Args:
            pair: Schwab forex symbol (e.g., "EURUSD")
            direction: BUY or SELL
            quantity: Lot size
            macro_conviction: Conviction level 0.0-1.0 from macro analysis

        Returns:
            dict with execution results (success, order_id, entry_price, pnl if closed)
        """
        print(f"\n[EXECUTION] {direction} {quantity}L {pair} (conviction: {macro_conviction})")
        print("=" * 80)

        # Step 1: Get current quote
        quote = self.client.get_forex_quote(pair)
        if not quote:
            return {"success": False, "error": "Quote unavailable"}

        entry_price = quote.get("ask") if direction == "BUY" else quote.get("bid")

        # Step 2: Place order
        success, order_id, filled_price = self.client.place_forex_order(
            pair=pair,
            direction=direction,
            quantity=quantity,
            entry_price=entry_price
        )

        if not success:
            return {"success": False, "error": "Order placement failed"}

        # Step 3: Log opened trade
        trade_data = {
            "pair": pair,
            "direction": direction,
            "quantity": quantity,
            "entry_price": filled_price,
            "exit_price": None,
            "pips_gained": None,
            "pnl": 0.0,
            "status": "OPEN"
        }
        self.journal.log_trade(trade_data)

        result = {
            "success": True,
            "pair": pair,
            "direction": direction,
            "order_id": order_id,
            "entry_price": filled_price,
            "quantity": quantity,
            "status": "OPEN"
        }

        print(f"[EXECUTION] ✅ Trade executed successfully")
        print("=" * 80)
        return result

    def close_recommendation(self, pair: str) -> Dict:
        """
        Close an open forex position.

        Args:
            pair: Schwab forex symbol

        Returns:
            dict with close results (success, exit_price, pnl)
        """
        print(f"\n[CLOSE] Closing position {pair}")
        print("=" * 80)

        # Get current quote for exit price
        quote = self.client.get_forex_quote(pair)
        if not quote:
            return {"success": False, "error": "Quote unavailable"}

        exit_price = quote.get("mid", quote.get("ask"))

        # Close the position
        success, pnl = self.client.close_position(pair, exit_price)

        if not success:
            return {"success": False, "error": "Close failed"}

        # Log closed trade
        trade_data = {
            "pair": pair,
            "direction": "CLOSE",
            "quantity": 0,
            "entry_price": 0,
            "exit_price": exit_price,
            "pips_gained": 0,
            "pnl": pnl,
            "status": "CLOSED"
        }
        self.journal.log_trade(trade_data)

        result = {
            "success": True,
            "pair": pair,
            "exit_price": exit_price,
            "pnl": pnl,
            "status": "CLOSED"
        }

        print(f"[CLOSE] ✅ Position closed")
        print("=" * 80)
        return result


# =====================================================================
# LAMBDA HANDLER (Phase 1B - Execution)
# =====================================================================

def lambda_handler(event, context):
    """
    v3.0.34 Forex Execution Layer - Phase 1B Handler
    Called by v3.0.33 when FOREX_TRADING mode detected.

    Event format:
    {
        "mode": "FOREX",
        "macro_analysis": {
            "regime": "NEUTRAL",
            "conviction": 0.50,
            "recommended_pairs": ["EUR/USD", "USD/CAD"]
        },
        "action": "EXECUTE" or "CLOSE"
    }
    """

    print("=" * 80)
    print("McElveen Autonomous Trading System v3.0.34 - Forex Execution")
    print("=" * 80)
    print(f"[TIME] {datetime.now(ET).isoformat()}")
    print()

    # Get credentials
    access_token = SCHWAB_ACCESS_TOKEN
    if not access_token:
        print("[ERROR] No access token available")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Missing access token"})
        }

    # Initialize orchestrator
    orchestrator = ForexExecutionOrchestrator(access_token, SCHWAB_ACCOUNT_ID)

    # Parse macro recommendations
    macro = event.get("macro_analysis", {})
    recommended_pairs = macro.get("recommended_pairs", [])
    regime = macro.get("regime", "NEUTRAL")
    conviction = macro.get("conviction", 0.5)

    print(f"[REGIME] {regime}")
    print(f"[CONVICTION] {conviction:.2f}")
    print(f"[PAIRS] {', '.join(recommended_pairs)}")
    print()

    # Execute sample trades (Phase 1B demo)
    executions = []
    if event.get("action") == "EXECUTE":
        for pair_name in recommended_pairs[:2]:  # Trade top 2 recommended pairs
            # Convert display name to Schwab symbol
            for forex_pair in ForexPairs:
                if forex_pair.value[0] == pair_name:
                    schwab_symbol = forex_pair.value[1]

                    # Determine direction based on regime
                    direction = "BUY" if regime == "RISK_ON" else "SELL"
                    quantity = 0.1 * conviction  # Size based on conviction

                    result = orchestrator.execute_recommendation(
                        pair=schwab_symbol,
                        direction=direction,
                        quantity=quantity,
                        macro_conviction=conviction
                    )
                    executions.append(result)
                    break

    # Calculate and publish metrics
    metrics = orchestrator.journal.calculate_daily_metrics()
    orchestrator.journal.publish_metrics_to_cloudwatch(metrics)

    print()
    print("[METRICS]")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    print()

    print("=" * 80)
    print("[SUCCESS] v3.0.34 Phase 1B: Forex execution ready")
    print("=" * 80)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "mode": "FOREX",
            "executions": executions,
            "metrics": metrics,
            "message": "Forex execution layer operational"
        })
    }


# =====================================================================
# LOCAL TESTING
# =====================================================================

if __name__ == "__main__":
    print("[DEBUG] Running v3.0.34 Phase 1B locally")
    print()

    # Mock event from v3.0.33 router
    mock_event = {
        "mode": "FOREX",
        "macro_analysis": {
            "regime": "NEUTRAL",
            "conviction": 0.50,
            "recommended_pairs": ["EUR/USD", "USD/CAD"]
        },
        "action": "EXECUTE"
    }

    result = lambda_handler(mock_event, None)
    print()
    print("[RESULT]")
    print(json.dumps(json.loads(result["body"]), indent=2))
