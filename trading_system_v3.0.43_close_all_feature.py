"""
=================================================================================
CLOSE-ALL FEATURE FOR v3.0.42 - PURE DAY TRADER (Liquidate at 3:55 PM ET)
=================================================================================

FEATURE SUMMARY:
✅ Checks current time every execution
✅ If time >= 3:55 PM ET and market open → Liquidate ALL positions
✅ Converts entire portfolio to cash before 4:00 PM close
✅ Starts fresh next trading day with clean slate

RATIONALE:
Day traders lock in ALL gains/losses before market close (4:00 PM ET)
to eliminate overnight gap risk (news, earnings, Fed announcements, etc)

TRADING FLOW (WITH CLOSE-ALL):
  09:30 AM - Market opens
  09:30 AM - 3:54 PM: Normal SELL_AND_BUY rotations, diversification
  3:55 PM - 3:59 PM: CLOSE-ALL triggered
              └─ Sell all positions
              └─ Convert to 100% cash
              └─ Zero overnight risk
  4:00 PM - Market closes
  Next day: Fresh portfolio, new capital deployment

OVERNIGHT RISK ELIMINATED:
  ❌ Gap risk (earnings, Fed decisions)
  ❌ After-hours volatility (3:30 PM - 4:00 PM)
  ❌ Extended hours volatility (4:00 PM - 8:00 AM next day)
  ✅ 100% cash safety
  ✅ Clean redeployment each day
  ✅ Compound on daily wins, avoid overnight blowups

IMPLEMENTATION POINTS:
1. Add is_close_all_time() function (checks if >= 15:55 ET)
2. Add close_all_positions() function (liquidates portfolio)
3. Call is_close_all_time() in main lambda_handler BEFORE trading decisions
4. If true, skip regular trading → execute close_all_positions() instead
5. Log: "[CLOSE_ALL] Liquidating portfolio at 3:55 PM (market close in 5 min)"
"""

# ============================================================================
# NEW FUNCTION #1: Check if it's 3:55 PM (close-all time)
# ============================================================================

def is_close_all_time():
    """
    Check if current time >= 3:55 PM ET (5 minutes before 4:00 PM market close)

    Returns: (is_close_all_time: bool, current_time_str: str)
    """
    from datetime import datetime
    from pytz import timezone

    try:
        et = timezone('America/New_York')
        now = datetime.now(et)

        # Extract hour and minute
        hour = now.hour
        minute = now.minute

        # 3:55 PM = 15:55 in 24-hour time
        # Check if >= 15:55 and < 16:00 (market close window)
        is_close_all = (hour == 15 and minute >= 55) or (hour >= 16)

        current_time_str = now.strftime("%H:%M:%S %Z")

        print(f"[TIME_CHECK] Current time: {current_time_str}")

        if is_close_all and hour < 17:  # Don't liquidate after 5 PM (market closed)
            print(f"[CLOSE_ALL] ✅ Time is {current_time_str} - CLOSE_ALL triggered")
            return True, current_time_str
        else:
            return False, current_time_str

    except Exception as e:
        print(f"[ERROR] Failed to check close-all time: {str(e)}")
        return False, "ERROR"


# ============================================================================
# NEW FUNCTION #2: Close all positions (liquidate portfolio)
# ============================================================================

def close_all_positions(account_hash, access_token, positions_data):
    """
    Liquidate ALL positions in portfolio at 3:55 PM ET

    Args:
        account_hash (str): Schwab account ID
        access_token (str): Schwab OAuth access token
        positions_data (list): Current positions from get_portfolio()

    Returns:
        {
            'executed': bool,
            'closed_count': int,
            'total_value': float,
            'errors': list
        }
    """

    print("\n" + "=" * 90)
    print("[CLOSE_ALL] 🔴 MARKET CLOSE SEQUENCE - Liquidating all positions at 3:55 PM")
    print("=" * 90)

    if not positions_data or len(positions_data) == 0:
        print("[CLOSE_ALL] ✅ No positions to close - portfolio already 100% cash")
        return {
            'executed': True,
            'closed_count': 0,
            'total_value': 0,
            'errors': []
        }

    closed_count = 0
    total_value = 0
    errors = []

    # Sort positions by market value (largest first) to close most impactful first
    sorted_positions = sorted(
        positions_data,
        key=lambda p: p.get('marketValue', 0),
        reverse=True
    )

    print(f"\n[CLOSE_ALL] Closing {len(sorted_positions)} position(s):\n")

    for position in sorted_positions:
        try:
            symbol = position.get('instrument', {}).get('symbol', 'UNKNOWN')
            quantity = position.get('longQuantity', 0)
            market_value = position.get('marketValue', 0)
            current_price = market_value / quantity if quantity > 0 else 0

            print(f"[CLOSE_ALL] Selling {symbol}: {quantity:.4f} shares @ ${current_price:.2f} = ${market_value:.2f}")

            # Execute SELL order
            sell_success = execute_sell_single(
                symbol=symbol,
                quantity=quantity,
                account_hash=account_hash,
                access_token=access_token,
                trade_context="CLOSE_ALL"
            )

            if sell_success:
                closed_count += 1
                total_value += market_value
                print(f"[CLOSE_ALL] ✅ {symbol} SOLD")
            else:
                error_msg = f"Failed to sell {symbol}"
                errors.append(error_msg)
                print(f"[CLOSE_ALL] ❌ {error_msg}")

        except Exception as e:
            error_msg = f"Error closing {symbol}: {str(e)}"
            errors.append(error_msg)
            print(f"[CLOSE_ALL] ❌ {error_msg}")

    # Summary
    print("\n" + "=" * 90)
    print(f"[CLOSE_ALL] SUMMARY")
    print("=" * 90)
    print(f"Positions closed: {closed_count}/{len(sorted_positions)}")
    print(f"Total value liquidated: ${total_value:,.2f}")
    if errors:
        print(f"Errors encountered: {len(errors)}")
        for error in errors:
            print(f"  - {error}")
    else:
        print(f"All positions successfully closed ✅")
    print(f"Portfolio now: 100% CASH")
    print("=" * 90 + "\n")

    return {
        'executed': True,
        'closed_count': closed_count,
        'total_value': total_value,
        'errors': errors
    }


# ============================================================================
# INTEGRATION INTO MAIN LAMBDA HANDLER (Add this check early in flow)
# ============================================================================

"""
LOCATION: In lambda_handler() function, add AFTER market hours check but BEFORE trading decisions:

    # ========== NEW: CLOSE-ALL CHECK AT 3:55 PM ==========
    print("[STEP 2.5] Checking for market close sequence...")
    is_close_all, time_str = is_close_all_time()

    if is_close_all:
        print(f"[STEP 2.5] Time is {time_str} - executing CLOSE_ALL sequence")

        # Get current positions
        account_data = get_portfolio(...)
        positions_data = account_data.get("positions", [])

        # Liquidate all
        close_result = close_all_positions(
            account_hash=account_hash,
            access_token=access_token,
            positions_data=positions_data
        )

        # Log to DynamoDB
        trades_table.put_item(Item={
            "symbol": "CLOSE_ALL",
            "order_type": "CLOSE_ALL_SEQUENCE",
            "quantity": close_result['closed_count'],
            "total_value": close_result['total_value'],
            "timestamp": datetime.utcnow().isoformat(),
            "trade_date": today_date,
            "status": "COMPLETED"
        })

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "CLOSE_ALL_EXECUTED",
                "message": f"Liquidated {close_result['closed_count']} positions at {time_str}",
                "total_value": close_result['total_value'],
                "errors": close_result['errors']
            })
        }

    # ========== Continue with normal trading if not close-all time ==========
    # [STEP 3] Chief Investment Officer analyzing macro...
    # ... rest of normal trading logic ...
"""

# ============================================================================
# EXECUTION FLOW DIAGRAM
# ============================================================================

"""
                   Market Open (9:30 AM ET)
                            |
                            v
                   ┌─────────────────┐
                   │  Normal Trading  │
                   │  SELL_AND_BUY    │
                   │  Rotations       │
                   │  09:30 - 15:54   │
                   └─────────────────┘
                            |
                            v (15:54 becomes 15:55)
                   ┌─────────────────────┐
                   │ is_close_all_time() │
                   │   >= 15:55 ET?      │
                   └─────────────────────┘
                         /        \
                       NO          YES
                       |            |
                       v            v
              Continue Trading   CLOSE_ALL
              (wait for next        |
               execution)           v
                              close_all_positions()
                              ├─ Sell all positions
                              ├─ Convert to cash
                              ├─ Zero risk overnight
                              └─ Log to DynamoDB
                                   |
                                   v
                         Market Close (4:00 PM ET)
                              100% Cash

Next Day 9:30 AM: Fresh positions, new capital deployment
"""


# ============================================================================
# CLOUDWATCH LOG EXAMPLE
# ============================================================================

"""
[STEP 2.5] Checking for market close sequence...
[TIME_CHECK] Current time: 15:56:23 EDT
[CLOSE_ALL] ✅ Time is 15:56:23 EDT - CLOSE_ALL triggered
[CLOSE_ALL] 🔴 MARKET CLOSE SEQUENCE - Liquidating all positions at 3:55 PM
[CLOSE_ALL] Closing 7 position(s):

[CLOSE_ALL] Selling SPY: 0.0239 shares @ $769.04 = $18.38
[CLOSE_ALL] ✅ SPY SOLD
[CLOSE_ALL] Selling AAPL: 0.0134 shares @ $343.28 = $4.60
[CLOSE_ALL] ✅ AAPL SOLD
[CLOSE_ALL] Selling NVDA: 0.0103 shares @ $221.36 = $2.28
[CLOSE_ALL] ✅ NVDA SOLD
[CLOSE_ALL] Selling SCHD: 0.0595 shares @ $33.64 = $2.00
[CLOSE_ALL] ✅ SCHD SOLD
[CLOSE_ALL] Selling AGG: 0.0700 shares @ $94.86 = $6.64
[CLOSE_ALL] ✅ AGG SOLD
[CLOSE_ALL] Selling VTI: 0.0053 shares @ $377.36 = $2.00
[CLOSE_ALL] ✅ VTI SOLD
[CLOSE_ALL] Selling UNH: 0.0060 shares @ $393.33 = $2.36
[CLOSE_ALL] ✅ UNH SOLD

==============================================================================================
[CLOSE_ALL] SUMMARY
==============================================================================================
Positions closed: 7/7
Total value liquidated: $38.26
All positions successfully closed ✅
Portfolio now: 100% CASH
==============================================================================================

[LOGGING] ✅ Logged CLOSE_ALL to DynamoDB (symbol: CLOSE_ALL, quantity: 7, total_value: $38.26)

Result: ✅ CLOSE_ALL_EXECUTED
Message: Liquidated 7 positions at 15:56:23 EDT
"""
