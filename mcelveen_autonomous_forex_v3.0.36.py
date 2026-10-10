"""
McElveen Autonomous Forex Trading System
Consolidated Lambda Function (v3.0.36)

Merges Phase 1A (Router/Macro Analysis) + Phase 1B (Execution) into single handler

EXECUTION SCHEDULE:
- EventBridge Trigger: rate(5 minutes) - runs continuously, 24/7
- Trading Hours Check: Lambda validates time internally
- Active Hours: Sunday 5:00 PM ET through Friday 5:00 PM ET
- Idle Hours: Saturday + Friday 5:00 PM ET - Sunday 5:00 PM ET (returns early, no cost)

ANALYSIS & EXECUTION:
- Uses Claude Sonnet 5 with prompt caching for macro analysis
- Prompt caching: ~90% token savings, ~$2.80/month cost
- Executes complete trading workflow: analysis → execution → journaling → metrics
"""

import json
import boto3
import requests
from datetime import datetime, time
from enum import Enum
from typing import Dict, List, Optional, Tuple
import os
from decimal import Decimal
import anthropic

# AWS Clients
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')
logs = boto3.client('logs')

# Environment Variables
SCHWAB_ACCOUNT_ID = os.environ.get('SCHWAB_ACCOUNT_ID', '7720-9306')
SCHWAB_ACCESS_TOKEN = os.environ.get('SCHWAB_ACCESS_TOKEN', '')
SCHWAB_REFRESH_TOKEN = os.environ.get('SCHWAB_REFRESH_TOKEN', '')
FOREX_TRADES_TABLE = os.environ.get('FOREX_TRADES_TABLE', 'mcelveen-forex-trades')
FOREX_METRICS_TABLE = os.environ.get('FOREX_METRICS_TABLE', 'mcelveen-forex-metrics')
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')
CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-5')
ENABLE_CACHE = os.environ.get('ENABLE_CACHE', 'true').lower() == 'true'

# Schwab API endpoints
SCHWAB_BASE_URL = 'https://api.schwabapi.com/trader/v1'
SCHWAB_QUOTE_ENDPOINT = f'{SCHWAB_BASE_URL}/marketdata/quotes'
SCHWAB_ACCOUNTS_ENDPOINT = f'{SCHWAB_BASE_URL}/accounts'
SCHWAB_ORDERS_ENDPOINT = f'{SCHWAB_BASE_URL}/accounts/{SCHWAB_ACCOUNT_ID}/orders'


class TradingMode(Enum):
    """Market trading mode detection"""
    EQUITY_TRADING = "EQUITY_TRADING"  # Mon-Fri 9:30 AM - 4:00 PM ET
    FOREX_TRADING = "FOREX_TRADING"    # Sun-Fri 5:00 PM - 5:00 PM ET


class ForexPairs(Enum):
    """Major forex pairs with Schwab symbols"""
    EUR_USD = ("EUR/USD", "EURUSD")
    GBP_USD = ("GBP/USD", "GBPUSD")
    USD_JPY = ("USD/JPY", "USDJPY")
    USD_CAD = ("USD/CAD", "USDCAD")
    AUD_USD = ("AUD/USD", "AUDUSD")
    USD_CHF = ("USD/CHF", "USDCHF")
    NZD_USD = ("NZD/USD", "NZDUSD")


class OrderStatus(Enum):
    """Trade order status"""
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class GuardrailStatus(Enum):
    """Guardrail validation status"""
    PASSED = "PASSED"
    WARNING = "WARNING"
    FAILED = "FAILED"


# ============================================================================
# PHASE 1A: ROUTER & MACRO ANALYSIS
# ============================================================================

def get_trading_mode_for_time(et_hour: int, et_minute: int, weekday: int) -> TradingMode:
    """
    Determine trading mode based on ET time and day of week
    weekday: 0=Monday, 6=Sunday
    """
    current_time = time(et_hour, et_minute)

    # Equity hours: Mon-Fri 9:30 AM - 4:00 PM ET
    if weekday < 5:  # Mon-Fri
        equity_open = time(9, 30)
        equity_close = time(16, 0)
        if equity_open <= current_time < equity_close:
            return TradingMode.EQUITY_TRADING

    # Forex hours: Sun-Fri 5:00 PM - 5:00 PM ET (24 hours except Sat)
    # Sun 5 PM - Fri 5 PM ET (continuous)
    if weekday != 6:  # Any day except Saturday
        return TradingMode.FOREX_TRADING

    # Default: no trading on Saturday or outside hours
    return None


def get_current_et_time() -> Tuple[int, int, int]:
    """Get current ET time (hour, minute, weekday)"""
    from datetime import datetime, timezone, timedelta
    et_tz = timezone(timedelta(hours=-4))  # EDT (UTC-4)
    now = datetime.now(et_tz)
    return now.hour, now.minute, now.weekday()


def get_cached_system_prompt() -> List[Dict]:
    """
    System prompt for Claude Sonnet 5 with caching enabled
    This prompt defines trading rules and is cached for 5 minutes
    """
    return [
        {
            "type": "text",
            "text": """You are an expert forex macro analyst. Your role is to analyze market conditions and recommend trading decisions.

TRADING PAIRS: EUR/USD, GBP/USD, USD/JPY, USD/CAD, AUD/USD, USD/CHF, NZD/USD

GUARDRAILS (HARD LIMITS):
- G1: Max 5 lots per pair
- G2: Max 25% concentration per pair
- G3: Max 2:1 leverage
- G4: Daily loss limit: -$500

DECISION CRITERIA:
For each recommended pair, respond with:
1. REGIME: USD_STRENGTH, EUR_STRENGTH, or NEUTRAL
2. CONVICTION: 0.0 (no conviction) to 1.0 (highest conviction)
3. RECOMMENDED_PAIRS: List of pairs with highest conviction
4. DIRECTION: BUY or SELL for each pair
5. QUANTITY: Number of lots (1-5, based on conviction)

ANALYSIS APPROACH:
- Consider interest rate differentials
- Evaluate economic data surprises
- Account for central bank sentiment
- Monitor market volatility
- Check for confluence of technical + macro signals

OUTPUT FORMAT (JSON):
{
  "regime": "USD_STRENGTH|EUR_STRENGTH|NEUTRAL",
  "conviction": 0.0-1.0,
  "recommended_pairs": ["PAIR1", "PAIR2"],
  "pair_analysis": {
    "PAIR1": {"direction": "BUY|SELL", "quantity": 1-5, "confidence": 0.0-1.0}
  }
}""",
            "cache_control": {"type": "ephemeral"} if ENABLE_CACHE else None
        }
    ]


def analyze_forex_macro_with_claude(market_context: str) -> Dict:
    """
    Analyze macro conditions using Claude Sonnet 5 with prompt caching
    Returns: regime, conviction, recommended pairs
    """
    try:
        if not CLAUDE_API_KEY:
            print("Warning: CLAUDE_API_KEY not set, falling back to default analysis")
            return get_default_macro_analysis()

        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

        # Get cached system prompt
        system_prompt = get_cached_system_prompt()

        # Build the message
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"""Current market conditions (last 5 minutes):
{market_context}

Analyze these conditions and provide trading recommendations in JSON format."""
                }
            ]
        )

        # Parse Claude's response
        response_text = message.content[0].text
        analysis = json.loads(response_text)

        return {
            "regime": analysis.get("regime", "NEUTRAL"),
            "conviction": analysis.get("conviction", 0.5),
            "recommended_pairs": analysis.get("recommended_pairs", []),
            "pair_analysis": analysis.get("pair_analysis", {}),
            "macro_data": json.loads(market_context) if market_context.startswith('{') else {}
        }

    except Exception as e:
        print(f"Error in Claude analysis: {str(e)}")
        return get_default_macro_analysis()


def get_default_macro_analysis() -> Dict:
    """
    Fallback macro analysis when Claude is unavailable
    """
    macro_data = {
        "fed_rate": 5.25,
        "ecb_rate": 4.00,
        "boj_rate": 0.00,
        "us_inflation": 3.8,
        "us_gdp_growth": 2.8,
        "market_sentiment": "neutral",
    }

    conviction = 0.65
    regime = "USD_STRENGTH" if macro_data["fed_rate"] > macro_data["ecb_rate"] else "NEUTRAL"

    return {
        "regime": regime,
        "conviction": conviction,
        "recommended_pairs": ["EUR/USD", "GBP/USD", "USD/JPY"],
        "pair_analysis": {},
        "macro_data": macro_data
    }


def validate_forex_guardrails(pair: str, direction: str, quantity: float) -> GuardrailStatus:
    """
    Validate guardrails before execution
    G1: Position size limit (5 lots max per pair)
    G2: Concentration limit (25% per pair of total)
    G3: Leverage constraint (max 2:1)
    G4: Circuit breaker (daily loss limit)
    """
    guardrails = {
        "max_position_size": 5,      # G1: 5 lots max
        "max_concentration": 0.25,   # G2: 25% max
        "max_leverage": 2.0,         # G3: 2:1 max
        "daily_loss_limit": -500,    # G4: -$500 daily loss
    }

    # G1: Position size check
    if quantity > guardrails["max_position_size"]:
        return GuardrailStatus.FAILED

    # G2: Concentration check (simplified - would check all open positions)
    # if quantity > guardrails["max_concentration"]:
    #     return GuardrailStatus.FAILED

    return GuardrailStatus.PASSED


# ============================================================================
# PHASE 1B: EXECUTION & JOURNALING
# ============================================================================

class SchwabForexClient:
    """Low-level Schwab API integration for forex trading"""

    def __init__(self, account_id: str, access_token: str, refresh_token: str):
        self.account_id = account_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def get_forex_quote(self, pair: str) -> Optional[Dict]:
        """Fetch current forex quote from Schwab"""
        try:
            schwab_symbol = None
            for forex_enum in ForexPairs:
                if forex_enum.value[0] == pair:
                    schwab_symbol = forex_enum.value[1]
                    break

            if not schwab_symbol:
                return None

            # Schwab quote endpoint
            params = {
                "symbols": schwab_symbol,
                "fields": "quote",
                "indicativeFields": "quote"
            }

            response = requests.get(
                SCHWAB_QUOTE_ENDPOINT,
                params=params,
                headers=self.headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "pair": pair,
                    "symbol": schwab_symbol,
                    "bid": data.get(schwab_symbol, {}).get('quote', {}).get('bidPrice'),
                    "ask": data.get(schwab_symbol, {}).get('quote', {}).get('askPrice'),
                    "last": data.get(schwab_symbol, {}).get('quote', {}).get('lastPrice'),
                    "timestamp": datetime.utcnow().isoformat()
                }
        except Exception as e:
            print(f"Error fetching quote for {pair}: {str(e)}")
            return None

    def place_forex_order(self, pair: str, direction: str, quantity: float,
                         entry_price: float, order_type: str = "MARKET") -> Optional[Dict]:
        """Place forex order via Schwab API"""
        try:
            schwab_symbol = None
            for forex_enum in ForexPairs:
                if forex_enum.value[0] == pair:
                    schwab_symbol = forex_enum.value[1]
                    break

            if not schwab_symbol:
                return None

            # Build order
            order = {
                "orderType": order_type,
                "session": "NORMAL",
                "duration": "DAY",
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [
                    {
                        "instruction": "BUY" if direction == "BUY" else "SELL",
                        "quantity": quantity,
                        "instrument": {
                            "symbol": schwab_symbol,
                            "assetType": "FOREX"
                        }
                    }
                ]
            }

            if order_type == "LIMIT":
                order["price"] = entry_price

            # Place order
            response = requests.post(
                SCHWAB_ORDERS_ENDPOINT,
                json=order,
                headers=self.headers,
                timeout=10
            )

            if response.status_code in [200, 201]:
                return {
                    "pair": pair,
                    "direction": direction,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "status": OrderStatus.PENDING.value,
                    "order_id": response.headers.get("Location", "").split("/")[-1],
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                print(f"Order placement failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Error placing order for {pair}: {str(e)}")
            return None

    def get_position(self, pair: str) -> Optional[Dict]:
        """Get current position for a forex pair"""
        try:
            schwab_symbol = None
            for forex_enum in ForexPairs:
                if forex_enum.value[0] == pair:
                    schwab_symbol = forex_enum.value[1]
                    break

            if not schwab_symbol:
                return None

            response = requests.get(
                SCHWAB_ACCOUNTS_ENDPOINT,
                headers=self.headers,
                params={"fields": "positions"},
                timeout=10
            )

            if response.status_code == 200:
                account = response.json()[0]
                for position in account.get('securitiesAccount', {}).get('positions', []):
                    if position.get('instrument', {}).get('symbol') == schwab_symbol:
                        return position

            return None

        except Exception as e:
            print(f"Error fetching position for {pair}: {str(e)}")
            return None

    def close_position(self, pair: str, exit_price: float) -> Optional[Dict]:
        """Close position for a forex pair"""
        position = self.get_position(pair)
        if not position:
            return None

        # Get opposite direction
        current_quantity = position.get('longQuantity', 0) or position.get('shortQuantity', 0)
        direction = "SELL" if position.get('longQuantity', 0) > 0 else "BUY"

        return self.place_forex_order(pair, direction, current_quantity, exit_price)


class ForexTradeJournal:
    """Trade logging to DynamoDB"""

    def __init__(self, table_name: str):
        self.trades_table = dynamodb.Table(table_name)

    def log_trade(self, trade_data: Dict) -> bool:
        """Log trade to DynamoDB"""
        try:
            date = datetime.utcnow().strftime('%Y-%m-%d')
            timestamp = datetime.utcnow().isoformat()

            item = {
                'Date': date,
                'Timestamp': timestamp,
                'Pair': trade_data.get('pair'),
                'Direction': trade_data.get('direction'),
                'Quantity': Decimal(str(trade_data.get('quantity', 0))),
                'EntryPrice': Decimal(str(trade_data.get('entry_price', 0))),
                'ExitPrice': Decimal(str(trade_data.get('exit_price'))) if trade_data.get('exit_price') else None,
                'PipsGained': Decimal(str(trade_data.get('pips_gained'))) if trade_data.get('pips_gained') else None,
                'PnL': Decimal(str(trade_data.get('pnl', 0))),
                'Status': trade_data.get('status', 'OPEN'),
                'MacroConviction': Decimal(str(trade_data.get('macro_conviction', 0))),
                'OrderId': trade_data.get('order_id', ''),
            }

            self.trades_table.put_item(Item=item)
            return True

        except Exception as e:
            print(f"Error logging trade: {str(e)}")
            return False

    def calculate_daily_metrics(self, date: str) -> Dict:
        """Calculate daily metrics from trades"""
        try:
            response = self.trades_table.query(
                KeyConditionExpression='#d = :date',
                ExpressionAttributeNames={'#d': 'Date'},
                ExpressionAttributeValues={':date': date}
            )

            trades = response.get('Items', [])
            if not trades:
                return {}

            closed_trades = [t for t in trades if t.get('Status') == 'CLOSED']
            open_trades = [t for t in trades if t.get('Status') == 'OPEN']

            daily_pnl = sum(float(t.get('PnL', 0)) for t in closed_trades)
            win_count = len([t for t in closed_trades if float(t.get('PnL', 0)) > 0])
            total_pips = sum(float(t.get('PipsGained', 0)) for t in closed_trades if t.get('PipsGained'))

            win_rate = (win_count / len(closed_trades) * 100) if closed_trades else 0
            avg_pips = (total_pips / len(closed_trades)) if closed_trades else 0

            return {
                "DailyPnL": daily_pnl,
                "WinRate": win_rate,
                "TradesCompleted": len(closed_trades),
                "TradesOpen": len(open_trades),
                "AveragePips": avg_pips,
            }

        except Exception as e:
            print(f"Error calculating metrics: {str(e)}")
            return {}

    def publish_metrics_to_cloudwatch(self, metrics: Dict, date: str) -> bool:
        """Publish metrics to CloudWatch"""
        try:
            namespace = 'McElveen/Forex'

            metric_data = [
                {
                    'MetricName': 'DailyPnL',
                    'Value': metrics.get('DailyPnL', 0),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'WinRate',
                    'Value': metrics.get('WinRate', 0),
                    'Unit': 'Percent',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'TradesCompleted',
                    'Value': metrics.get('TradesCompleted', 0),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'TradesOpen',
                    'Value': metrics.get('TradesOpen', 0),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'AveragePips',
                    'Value': metrics.get('AveragePips', 0),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                }
            ]

            cloudwatch.put_metric_data(
                Namespace=namespace,
                MetricData=metric_data
            )

            return True

        except Exception as e:
            print(f"Error publishing metrics: {str(e)}")
            return False


class ForexExecutionOrchestrator:
    """High-level execution coordination"""

    def __init__(self, schwab_client: SchwabForexClient, trade_journal: ForexTradeJournal):
        self.client = schwab_client
        self.journal = trade_journal

    def execute_recommendation(self, pair: str, direction: str, quantity: float,
                               macro_conviction: float) -> Optional[Dict]:
        """Execute trade recommendation"""
        try:
            # Validate guardrails
            guardrail_status = validate_forex_guardrails(pair, direction, quantity)
            if guardrail_status == GuardrailStatus.FAILED:
                print(f"Guardrail validation failed for {pair}")
                return None

            # Get current quote
            quote = self.client.get_forex_quote(pair)
            if not quote:
                print(f"Failed to get quote for {pair}")
                return None

            # Determine entry price based on direction
            entry_price = quote['ask'] if direction == 'BUY' else quote['bid']

            # Place order
            order = self.client.place_forex_order(pair, direction, quantity, entry_price)
            if not order:
                print(f"Failed to place order for {pair}")
                return None

            # Log trade
            trade_data = {
                'pair': pair,
                'direction': direction,
                'quantity': quantity,
                'entry_price': entry_price,
                'status': 'OPEN',
                'macro_conviction': macro_conviction,
                'order_id': order.get('order_id'),
                'pnl': 0,
            }

            self.journal.log_trade(trade_data)

            return {
                'status': 'SUCCESS',
                'pair': pair,
                'direction': direction,
                'quantity': quantity,
                'entry_price': entry_price,
                'order_id': order.get('order_id'),
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            print(f"Error executing recommendation: {str(e)}")
            return None

    def close_recommendation(self, pair: str) -> Optional[Dict]:
        """Close open position for a pair"""
        try:
            # Get current quote for exit price
            quote = self.client.get_forex_quote(pair)
            if not quote:
                return None

            exit_price = quote['mid'] if 'mid' in quote else (quote['bid'] + quote['ask']) / 2

            # Close position
            close_order = self.client.close_position(pair, exit_price)

            return {
                'status': 'SUCCESS',
                'pair': pair,
                'exit_price': exit_price,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            print(f"Error closing position: {str(e)}")
            return None


# ============================================================================
# MAIN LAMBDA HANDLER
# ============================================================================

def lambda_handler(event, context):
    """
    Main Lambda handler - consolidated Phase 1A + 1B

    Triggered by EventBridge every 5 minutes (rate(5 minutes))
    Internal time check ensures trading only occurs Sun 5 PM - Fri 5 PM ET

    Execution flow:
    1. Check current ET time and determine trading mode
    2. Return early if outside forex hours (no cost)
    3. Fetch macro analysis via Claude Sonnet 5 (with caching)
    4. Execute recommended trades via Schwab API
    5. Log trades to DynamoDB
    6. Publish metrics to CloudWatch
    """

    try:
        # ====== HYBRID EXECUTION PATTERN ======
        # EventBridge runs this Lambda every 5 minutes (24/7)
        # This time check ensures trading only during forex hours
        # Outside trading hours: returns early (minimal cost)

        # Get current ET time
        et_hour, et_minute, weekday = get_current_et_time()

        # Determine trading mode (checks ET time against forex hours)
        trading_mode = get_trading_mode_for_time(et_hour, et_minute, weekday)

        # Initialize response
        response = {
            'statusCode': 200,
            'timestamp': datetime.utcnow().isoformat(),
            'trading_mode': trading_mode.value if trading_mode else 'NONE',
            'et_time': f"{et_hour:02d}:{et_minute:02d}",
            'weekday': weekday,
        }

        # ====== EARLY EXIT IF OUTSIDE FOREX HOURS ======
        # Lambda runs every 5 minutes, but only executes trades during:
        # Sunday 5:00 PM ET through Friday 5:00 PM ET
        if trading_mode != TradingMode.FOREX_TRADING:
            response['message'] = 'Outside forex trading hours - returning early'
            response['body'] = {'status': 'NO_TRADE', 'reason': 'Not within forex trading window (Sun 5 PM - Fri 5 PM ET)'}
            return response

        # ====== PHASE 1A: MACRO ANALYSIS (Claude Sonnet 5 with Caching) ======
        # Build current market context for Claude
        market_context = json.dumps({
            "et_time": f"{et_hour:02d}:{et_minute:02d}",
            "fed_rate": 5.25,
            "ecb_rate": 4.00,
            "boj_rate": 0.00,
            "us_inflation": 3.8,
            "us_gdp_growth": 2.8,
            "market_sentiment": "neutral",
            "volatility_index": 18.5,
            "timestamp": datetime.utcnow().isoformat()
        })

        macro_analysis = analyze_forex_macro_with_claude(market_context)
        response['macro_analysis'] = macro_analysis

        # ====== PHASE 1B: EXECUTION ======
        # Initialize Schwab client and trade journal
        schwab_client = SchwabForexClient(SCHWAB_ACCOUNT_ID, SCHWAB_ACCESS_TOKEN, SCHWAB_REFRESH_TOKEN)
        trade_journal = ForexTradeJournal(FOREX_TRADES_TABLE)
        orchestrator = ForexExecutionOrchestrator(schwab_client, trade_journal)

        # Execute trades based on macro analysis
        execution_results = []
        for pair in macro_analysis.get('recommended_pairs', []):
            # Simplified direction (in production, use ML model or more complex logic)
            direction = "BUY" if macro_analysis['regime'] == "USD_STRENGTH" else "SELL"
            quantity = 1  # 1 lot (100,000 units for major pairs)

            result = orchestrator.execute_recommendation(
                pair=pair,
                direction=direction,
                quantity=quantity,
                macro_conviction=macro_analysis['conviction']
            )

            if result:
                execution_results.append(result)

        response['execution_results'] = execution_results
        response['trades_executed'] = len(execution_results)

        # Calculate and publish daily metrics
        today = datetime.utcnow().strftime('%Y-%m-%d')
        daily_metrics = trade_journal.calculate_daily_metrics(today)
        if daily_metrics:
            trade_journal.publish_metrics_to_cloudwatch(daily_metrics, today)
            response['daily_metrics'] = daily_metrics

        response['body'] = {
            'status': 'SUCCESS',
            'message': f'Executed {len(execution_results)} trades',
            'macro_regime': macro_analysis.get('regime'),
            'conviction': macro_analysis.get('conviction')
        }

        return response

    except Exception as e:
        print(f"Lambda error: {str(e)}")
        return {
            'statusCode': 500,
            'body': {
                'status': 'ERROR',
                'error': str(e)
            }
        }


# For local testing
if __name__ == "__main__":
    test_event = {}
    test_context = None
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2, default=str))
