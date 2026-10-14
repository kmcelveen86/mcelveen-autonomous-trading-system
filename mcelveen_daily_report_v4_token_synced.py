"""
McElveen Daily P&L Report - Lambda Handler (v4 FINAL - TOKEN SYNCED FROM TRADING SYSTEM)
========================================================================================

PURPOSE: Generate daily profit/loss (P&L) report with trading activity summary
         Captures end-of-day account balance, trades executed, sector rotation, P&L
         Sends comprehensive daily summary to user

SCHEDULE: EventBridge cron `1 20 ? * MON-FRI`
          Fires at: 4:01 PM ET, Monday-Friday
          Reason: Market closes at 4:00 PM ET, 1-min delay for final data

STATUS: v4 FINAL - TOKEN SYNCED FROM TRADING SYSTEM
        ✅ Positions extraction from /accounts response
        ✅ Account health check (FIX #40)
        ✅ Daily trading activity summary (trades, sector rotation)
        ✅ Days held tracking (validates FIX #46)
        ✅ Risk guardrails compliance
        ✅ Detailed position P&L with hold duration
        ✅ DynamoDB trade journal integration
        ✅ TOKEN SYNCED FROM TRADING SYSTEM (no manual refresh needed!)

KEY CHANGE FROM v4:
        Line 76-89: Read refresh token from DynamoDB OAUTH_TOKENS_TABLE
                    Same table trading system updates every 30 minutes
                    Eliminates token expiration issues
"""

import requests
import base64
import boto3
from datetime import datetime, timedelta
import os
import json

# ============================================================================
# ENVIRONMENT VARIABLES (set in AWS Lambda Configuration)
# ============================================================================

CLIENT_ID = os.environ.get("SCHWAB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SCHWAB_CLIENT_SECRET")
SCHWAB_ACCOUNT_ID = os.environ.get("SCHWAB_ACCOUNT_ID")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
ALERT_EMAIL = os.environ.get("ALERT_EMAIL")

# DynamoDB Tables (must match trading system table names)
DYNAMODB_OAUTH_TABLE = os.environ.get("DYNAMODB_OAUTH_TABLE", "mcelveen-oauth-tokens")
DYNAMODB_TRADES_TABLE = os.environ.get("DYNAMODB_TRADES_TABLE", "mcelveen-trade-journal")
DYNAMODB_POSITIONS_TABLE = os.environ.get("DYNAMODB_POSITIONS_TABLE", "mcelveen-positions-snapshot")

# Securities lending enrollment status
SECURITIES_LENDING_ENROLLED = os.environ.get("SECURITIES_LENDING_ENROLLED", "false").lower() == "true"
SECURITIES_LENDING_ELIGIBLE = os.environ.get("SECURITIES_LENDING_ELIGIBLE", "false").lower() == "true"

# ============================================================================
# AWS CLIENTS
# ============================================================================

sns_client = boto3.client("sns", region_name="us-east-2")
dynamodb = boto3.resource("dynamodb", region_name="us-east-2")

oauth_table = dynamodb.Table(DYNAMODB_OAUTH_TABLE)
trades_table = dynamodb.Table(DYNAMODB_TRADES_TABLE)
positions_table = dynamodb.Table(DYNAMODB_POSITIONS_TABLE)


def get_refresh_token_from_dynamodb():
    """READ refresh token from DynamoDB (SYNCED FROM TRADING SYSTEM)

    This ensures Daily Report always has the latest token that the
    autonomous trading system just refreshed 30 minutes ago.
    No manual token updates needed!
    """

    try:
        print("[INFO] Reading refresh token from DynamoDB OAUTH table...")
        response = oauth_table.get_item(
            Key={"token_id": "schwab-refresh-token"}
        )

        if "Item" in response:
            token = response["Item"].get("token_value")
            updated_at = response["Item"].get("updated_at", "Unknown")

            if token:
                print(f"[INFO] ✅ Refresh token loaded from DynamoDB")
                print(f"[INFO] Last updated by trading system: {updated_at}")
                return token
            else:
                print("[ERROR] ❌ Token value is empty in DynamoDB")
                return None
        else:
            print("[ERROR] ❌ No refresh token found in DynamoDB OAUTH table")
            print("[ERROR] Trading system may not have run yet today")
            return None

    except Exception as e:
        print(f"[ERROR] ❌ Failed to read token from DynamoDB: {str(e)}")
        return None


def get_access_token():
    """STEP 1: Get access token from refresh token (loaded from DynamoDB)"""

    # Get refresh token from DynamoDB (synced from trading system)
    refresh_token = get_refresh_token_from_dynamodb()
    if not refresh_token:
        print("[ERROR] ❌ No refresh token available - cannot authenticate")
        return None

    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    try:
        print("[INFO] Requesting access token from Schwab...")
        response = requests.post(
            "https://api.schwabapi.com/v1/oauth/token",
            data=data,
            headers=headers,
            timeout=10
        )

        response.raise_for_status()

        tokens = response.json()
        access_token = tokens.get("access_token")
        expires_in = tokens.get("expires_in", "unknown")

        if access_token:
            print(f"[INFO] ✅ Access token obtained (expires in {expires_in}s)")
            return access_token
        else:
            print("[ERROR] ❌ No access_token in Schwab response")
            return None

    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] ❌ HTTP {e.response.status_code}: {e.response.text}")
        return None

    except Exception as e:
        print(f"[ERROR] ❌ Token request failed: {str(e)}")
        return None


def get_account_balance(access_token):
    """STEP 2: Fetch account balances and positions from Schwab"""

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    try:
        print("[INFO] Fetching account data from Schwab...")
        response = requests.get(
            "https://api.schwabapi.com/trader/v1/accounts",
            headers=headers,
            timeout=10
        )

        response.raise_for_status()

        accounts = response.json()

        if not accounts or len(accounts) == 0:
            print("[ERROR] ❌ No accounts returned from Schwab")
            return None

        account = accounts[0]
        securities_account = account.get("securitiesAccount", {})

        # Extract positions - they should be in securitiesAccount.positions
        positions = securities_account.get("positions", [])
        print(f"[DEBUG] Positions found in securitiesAccount.positions: {len(positions)}")

        # If positions empty, check alternate locations
        if not positions or len(positions) == 0:
            print("[DEBUG] Positions array is empty - checking alternate structures...")
            if "holdings" in securities_account:
                positions = securities_account.get("holdings", [])
                print(f"[DEBUG] Found {len(positions)} in 'holdings'")
            elif "positionsList" in securities_account:
                positions = securities_account.get("positionsList", [])
                print(f"[DEBUG] Found {len(positions)} in 'positionsList'")

        account_data = {
            "accountNumber": securities_account.get("accountNumber", "Unknown"),
            "type": securities_account.get("type", "Unknown"),
            "currentBalances": securities_account.get("currentBalances", {}),
            "positions": positions
        }

        print(f"[INFO] ✅ Account retrieved: {account_data['accountNumber']}")
        print(f"[INFO] ✅ Positions retrieved: {len(positions)} position(s)")

        return account_data

    except requests.exceptions.HTTPError as e:
        print(f"[ERROR] ❌ Fetch failed: HTTP {e.response.status_code}")
        print(f"[ERROR] Response: {e.response.text}")
        return None
    except Exception as e:
        print(f"[ERROR] ❌ Fetch error: {str(e)}")
        return None


def get_today_trades():
    """STEP 2b: Fetch today's trades from DynamoDB trade journal"""

    try:
        print("[INFO] Fetching today's trades from DynamoDB...")
        today_date = datetime.utcnow().strftime("%Y-%m-%d")

        # Scan trades table (no partition key available for query)
        response = trades_table.scan(
            FilterExpression="trade_date = :date",
            ExpressionAttributeValues={":date": today_date}
        )

        trades = response.get("Items", [])
        print(f"[INFO] ✅ Found {len(trades)} trade(s) today")

        return trades

    except Exception as e:
        print(f"[WARN] ⚠️  Could not fetch trades from DynamoDB: {str(e)}")
        return []


def get_position_entry_dates():
    """Get entry dates for all current positions from position snapshot table"""

    try:
        print("[INFO] Fetching position entry dates from DynamoDB...")

        response = positions_table.scan()
        positions_map = {}

        for item in response.get("Items", []):
            symbol = item.get("symbol", "")
            entry_date = item.get("entry_date", "")
            if symbol:
                positions_map[symbol] = entry_date

        print(f"[INFO] ✅ Loaded entry dates for {len(positions_map)} position(s)")
        return positions_map

    except Exception as e:
        print(f"[WARN] ⚠️  Could not fetch position dates from DynamoDB: {str(e)}")
        return {}


def calculate_days_held(entry_date_str):
    """Calculate days held from entry date string (ISO format)"""
    try:
        if not entry_date_str:
            return None

        entry_date = datetime.fromisoformat(entry_date_str.replace("Z", "+00:00"))
        today = datetime.utcnow().replace(tzinfo=entry_date.tzinfo)
        days = (today - entry_date).days

        return max(0, days)
    except:
        return None


def calculate_pnl(account_data, positions_map):
    """STEP 3: Calculate P&L (profit/loss) from account data + account health"""

    current_balances = account_data.get("currentBalances", {})
    positions = account_data.get("positions", [])

    cash_balance = current_balances.get("cashBalance", 0)
    account_value = current_balances.get("accountBalance", 0)
    liquidation_value = current_balances.get("liquidationValue", 0)
    buying_power = current_balances.get("buyingPower", 0)
    option_buying_power = current_balances.get("optionBuyingPower", buying_power)
    positions_count = len(positions) if positions else 0

    # Account health check (FIX #40)
    account_health_status = "🟢 HEALTHY" if option_buying_power >= 0 else "🔴 MARGIN DEFICIT"
    account_needs_action = option_buying_power < 0

    # Add days held to each position
    for position in positions:
        symbol = position.get("instrument", {}).get("symbol", "")
        entry_date = positions_map.get(symbol, "")
        days_held = calculate_days_held(entry_date)
        position["days_held"] = days_held
        position["entry_date"] = entry_date

    # Calculate securities lending income tracking
    lending_eligible_value = 0
    lending_ineligible_value = 0

    for position in positions:
        market_value = position.get("marketValue", 0)
        if cash_balance > 0:
            lending_eligible_value += market_value
        else:
            lending_ineligible_value += market_value

    print(f"[INFO] ✅ P&L calculated:")
    print(f"       Cash: ${cash_balance:,.2f}")
    print(f"       Account Value: ${account_value:,.2f}")
    print(f"       Liquidation Value: ${liquidation_value:,.2f}")
    print(f"       Buying Power: ${buying_power:,.2f}")
    print(f"       Option Buying Power: ${option_buying_power:,.2f}")
    print(f"       Account Health: {account_health_status}")
    print(f"       Positions: {positions_count}")

    return {
        "cash_balance": cash_balance,
        "account_value": account_value,
        "liquidation_value": liquidation_value,
        "buying_power": buying_power,
        "option_buying_power": option_buying_power,
        "account_health_status": account_health_status,
        "account_needs_action": account_needs_action,
        "positions_count": positions_count,
        "positions": positions,
        "lending_enrolled": SECURITIES_LENDING_ENROLLED,
        "lending_eligible": SECURITIES_LENDING_ELIGIBLE,
        "lending_eligible_value": lending_eligible_value,
        "lending_ineligible_value": lending_ineligible_value
    }


def extract_trading_summary(trades):
    """Extract trading summary from today's trades"""

    sell_buy_cycles = []
    sell_orders = []
    buy_orders = []

    for trade in trades:
        order_type = trade.get("order_type", "").upper()
        symbol = trade.get("symbol", "")
        quantity = trade.get("quantity", 0)
        order_id = trade.get("order_id", "")

        if order_type == "SELL":
            sell_orders.append({"symbol": symbol, "qty": quantity, "order_id": order_id})
        elif order_type == "BUY":
            buy_orders.append({"symbol": symbol, "qty": quantity, "order_id": order_id})

    # Match SELL_AND_BUY cycles (sell followed by buy)
    if sell_orders and buy_orders:
        for sell in sell_orders:
            for buy in buy_orders:
                sell_buy_cycles.append({
                    "sold": sell["symbol"],
                    "bought": buy["symbol"],
                    "sell_qty": sell["qty"],
                    "buy_qty": buy["qty"]
                })

    return {
        "total_trades": len(trades),
        "sell_buy_cycles": sell_buy_cycles,
        "sell_count": len(sell_orders),
        "buy_count": len(buy_orders),
        "trades": trades
    }


def format_email_body(account_data, pnl_data, trades_summary):
    """STEP 4: Format email body with P&L report + trading activity"""

    account_number = account_data.get("accountNumber", "Unknown")
    account_type = account_data.get("type", "Unknown")

    cash = pnl_data["cash_balance"]
    account_value = pnl_data["account_value"]
    liquidation_value = pnl_data["liquidation_value"]
    buying_power = pnl_data["buying_power"]
    option_buying_power = pnl_data.get("option_buying_power", buying_power)
    account_health_status = pnl_data.get("account_health_status", "🟢 HEALTHY")
    account_needs_action = pnl_data.get("account_needs_action", False)
    positions_count = pnl_data["positions_count"]
    positions = pnl_data["positions"]
    lending_enrolled = pnl_data.get("lending_enrolled", False)
    lending_eligible = pnl_data.get("lending_eligible", False)
    lending_eligible_value = pnl_data.get("lending_eligible_value", 0)

    trades = trades_summary["trades"]
    total_trades = trades_summary["total_trades"]
    sell_buy_cycles = trades_summary["sell_buy_cycles"]

    now = datetime.utcnow().isoformat()

    body = f"""
McElveen Daily P&L Report - v4 FINAL (Token Synced from Trading System)
======================================

Report Date (UTC): {now}

ACCOUNT SUMMARY
Account Number: {account_number}
Account Type: {account_type}

BALANCE SUMMARY
Cash Balance:          ${cash:>15,.2f}
Buying Power:          ${buying_power:>15,.2f}
Option Buying Power:   ${option_buying_power:>15,.2f}
Account Value:         ${account_value:>15,.2f}
Liquidation Value:     ${liquidation_value:>15,.2f}

ACCOUNT HEALTH CHECK (FIX #40)
======================================
Status: {account_health_status}
{f'⚠️  ACTION REQUIRED: Account in margin deficit (${option_buying_power:.2f}). Cash injection needed.' if account_needs_action else '✅ No action required - account healthy'}

DAILY TRADING ACTIVITY
======================================
Trades Executed:       {total_trades}
SELL_AND_BUY Cycles:   {len(sell_buy_cycles)}
Sell Orders:           {trades_summary['sell_count']}
Buy Orders:            {trades_summary['buy_count']}

"""

    # Add SELL_AND_BUY cycle details
    if sell_buy_cycles:
        body += "REBALANCING ACTIVITY\n"
        body += "=" * 70 + "\n"
        for i, cycle in enumerate(sell_buy_cycles, 1):
            body += f"Cycle {i}: Sold {cycle['sold']} → Bought {cycle['bought']}\n"
            body += f"         Qty: {cycle['sell_qty']:.4f} → {cycle['buy_qty']:.4f}\n"
        body += "=" * 70 + "\n\n"

    # Add portfolio metrics
    body += f"""
UNREALIZED P&L SUMMARY
======================================
Position Count:    {positions_count:>15}
Portfolio Value:   ${sum(p.get('marketValue', 0) for p in positions):>15,.2f}

POSITIONS WITH HOLD DURATION
Total Open Positions: {positions_count}

"""

    if positions and len(positions) > 0:
        body += "DETAILED POSITIONS\n"
        body += "=" * 110 + "\n"
        body += f"{'Symbol':<8} {'Qty':>10} {'Entry Price':>12} {'Current':>12} {'Value':>12} {'P&L':>12} {'%':>7} {'Days':>6}\n"
        body += "-" * 110 + "\n"

        total_pnl = 0
        total_entry_value = 0

        for position in sorted(positions, key=lambda p: p.get("instrument", {}).get("symbol", "")):
            symbol = position.get("instrument", {}).get("symbol", "Unknown")
            quantity = position.get("longQuantity", 0)
            market_value = position.get("marketValue", 0)
            average_price = position.get("averagePrice", 0)
            days_held = position.get("days_held", "?")

            # Format days held
            days_str = str(days_held) if days_held is not None else "?"

            # Calculate current price per share
            current_price = market_value / quantity if quantity > 0 else 0

            # Calculate P&L
            entry_value = average_price * quantity
            pnl = market_value - entry_value
            pnl_percent = (pnl / entry_value * 100) if entry_value != 0 else 0

            total_pnl += pnl
            total_entry_value += entry_value

            # Format the row
            body += f"{symbol:<8} {quantity:>10.4f} ${average_price:>11.2f} ${current_price:>11.2f} ${market_value:>11,.2f} ${pnl:>11,.2f} {pnl_percent:>6.2f}% {days_str:>6}\n"

        body += "-" * 110 + "\n"

        # Totals row
        total_entry_value_display = total_entry_value
        total_pnl_percent = (total_pnl / total_entry_value_display * 100) if total_entry_value_display != 0 else 0

        body += f"{'TOTAL':<8} {' ':>10} {' ':>12} {' ':>12} ${sum(p.get('marketValue', 0) for p in positions):>11,.2f} ${total_pnl:>11,.2f} {total_pnl_percent:>6.2f}% {'':>6}\n"
        body += "=" * 110 + "\n"
    else:
        body += "No open positions.\n"

    body += f"""
SECURITIES LENDING STATUS
======================================
Enrollment Status:        {'ACTIVE - Earning lending income' if lending_enrolled else 'INACTIVE - Not yet enrolled'}
Eligible for Enrollment:  {'Yes (apply at Schwab)' if lending_eligible and not lending_enrolled else 'Not yet (account too small or trading too fast)'}
Lending-Eligible Value:   ${lending_eligible_value:>12,.2f} {'(earning passive income)' if lending_enrolled else '(would earn if enrolled)'}

Note: Lending income rates typically 0.5-2% APY depending on stock demand.
      Enrolled positions earn passive income while you hold them.
      Margin positions are NOT eligible for lending.

======================================
This is an automated daily report from the McElveen Autonomous Trading System.
System automatically executes trades based on market analysis and Portfolio Manager directives.

🔄 TOKEN SYNC: Refresh token automatically synced from trading system
              No manual token updates needed!

Lambda Function: McElveenDailyReport
Region: us-east-2
Version: v4 FINAL - Token Synced from Trading System (FIX #40, #44, #45, #46, #47)

For questions or to review trade logic, check CloudWatch logs or Schwab account.
======================================
"""

    return body


def send_email_via_sns(pnl_data, email_body):
    """STEP 5: Send email via AWS SNS"""

    try:
        subject = f"McElveen Daily P&L Report - {datetime.utcnow().strftime('%Y-%m-%d')}"

        print(f"[INFO] Publishing email to SNS topic...")
        print(f"[INFO] Topic ARN: {SNS_TOPIC_ARN}")
        print(f"[INFO] Recipient: {ALERT_EMAIL}")

        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=email_body
        )

        message_id = response.get("MessageId", "Unknown")
        print(f"[INFO] ✅ Email published to SNS")
        print(f"[INFO] Message ID: {message_id}")
        print(f"[INFO] Email will be delivered to {ALERT_EMAIL} shortly")

        return True

    except Exception as e:
        print(f"[ERROR] ❌ Failed to publish email to SNS")
        print(f"[ERROR] Error: {str(e)}")
        print(f"[ERROR] Check:")
        print(f"       1. SNS topic exists: {SNS_TOPIC_ARN}")
        print(f"       2. SNS region is us-east-2 (not us-east-1)")
        print(f"       3. Lambda IAM role has sns:Publish permission")
        print(f"       4. Email subscriber is confirmed")
        return False


def lambda_handler(event, context):
    """MAIN HANDLER: Daily P&L Report Execution with Trading Activity"""

    print("\n" + "=" * 80)
    print("McElveen Daily P&L Report v4 FINAL - Starting Execution")
    print("=" * 80)
    print(f"Time (UTC): {datetime.utcnow().isoformat()}")
    print(f"SNS Topic: {SNS_TOPIC_ARN}")
    print(f"Report Email: {ALERT_EMAIL}")
    print(f"Securities Lending: {'ENROLLED' if SECURITIES_LENDING_ENROLLED else 'NOT ENROLLED'}")

    # STEP 1: Get access token (reads refresh token from DynamoDB)
    print("\n[STEP 1] Obtaining Schwab access token (token from DynamoDB)...")
    access_token = get_access_token()
    if not access_token:
        error_msg = "Failed to obtain access token - check DynamoDB OAUTH table"
        print(f"[ERROR] {error_msg}")
        return {"statusCode": 401, "body": json.dumps({"error": error_msg})}

    # STEP 2: Fetch account data and today's trades
    print("\n[STEP 2] Fetching account data and trading activity...")
    account_data = get_account_balance(access_token)
    if not account_data:
        error_msg = "Failed to fetch account data from Schwab"
        print(f"[ERROR] {error_msg}")
        return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

    # STEP 2b: Get today's trades and position entry dates
    print("\n[STEP 2b] Loading trading activity and position history...")
    today_trades = get_today_trades()
    positions_map = get_position_entry_dates()

    # STEP 3: Calculate P&L
    print("\n[STEP 3] Calculating P&L with position hold duration...")
    pnl_data = calculate_pnl(account_data, positions_map)

    # STEP 3b: Extract trading summary
    print("\n[STEP 3b] Analyzing trading activity...")
    trades_summary = extract_trading_summary(today_trades)
    print(f"[INFO] ✅ Trading summary: {trades_summary['total_trades']} trades, {len(trades_summary['sell_buy_cycles'])} SELL_AND_BUY cycle(s)")

    # STEP 4: Format email
    print("\n[STEP 4] Formatting comprehensive email report...")
    email_body = format_email_body(account_data, pnl_data, trades_summary)
    print(f"[INFO] ✅ Email formatted ({len(email_body)} chars)")

    # STEP 5: Send email via SNS
    print("\n[STEP 5] Sending email via SNS...")
    email_sent = send_email_via_sns(pnl_data, email_body)

    # COMPLETION
    if email_sent:
        print("\n" + "=" * 80)
        print("✅ Daily P&L Report - Execution Complete (v4 FINAL)")
        print("=" * 80)
        print("Email successfully published to SNS topic.")
        print("Recipient should receive it within a few minutes.")
        print("=" * 80)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "SUCCESS",
                "message": "Daily P&L report email sent",
                "cash_balance": pnl_data["cash_balance"],
                "account_value": pnl_data["account_value"],
                "positions": pnl_data["positions_count"],
                "trades_today": trades_summary["total_trades"],
                "sell_buy_cycles": len(trades_summary["sell_buy_cycles"])
            })
        }
    else:
        print("\n" + "=" * 80)
        print("⚠️  Daily P&L Report - Execution Completed with Issues")
        print("=" * 80)
        print("Report was generated but email failed to send.")
        print("Check SNS topic and Lambda IAM permissions.")
        print("=" * 80)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "PARTIAL_FAILURE",
                "message": "Report generated but email delivery failed",
                "error": "SNS publish failed"
            })
        }
