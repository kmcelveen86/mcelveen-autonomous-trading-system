"""
System Configuration (no secrets here - all passed via Lambda env vars)
"""

import os
import json

# AWS
AWS_REGION = os.getenv('AWS_REGION', 'us-east-2')
DYNAMODB_TABLE = 'mcelveen-trading-ledger'
CLOUDWATCH_NAMESPACE = 'McElveenTrading'

# Portfolio Targets
try:
    PORTFOLIO_ALLOCATION_TARGETS = json.loads(
        os.getenv('PORTFOLIO_TARGET_ALLOCATION',
                   '{"US_EQUITIES": 0.60, "INTERNATIONAL": 0.20, "BONDS": 0.15, "CASH": 0.05}')
    )
except json.JSONDecodeError:
    PORTFOLIO_ALLOCATION_TARGETS = {
        'US_EQUITIES': 0.60,
        'INTERNATIONAL': 0.20,
        'BONDS': 0.15,
        'CASH': 0.05
    }

# Risk Guardrails
CONCENTRATION_LIMIT = float(os.getenv('CONCENTRATION_LIMIT', 0.15))  # Max 15% in any single position
DAILY_TRADE_FREQUENCY_CAP = int(os.getenv('DAILY_TRADE_FREQUENCY_CAP', 3))  # Max 3 trades per day
VIX_THRESHOLD_AGGRESSIVE = float(os.getenv('VIX_THRESHOLD_AGGRESSIVE', 15))  # Go aggressive when VIX < 15
VIX_THRESHOLD_DEFENSIVE = float(os.getenv('VIX_THRESHOLD_DEFENSIVE', 25))   # Go defensive when VIX > 25

# Position Sizing
MIN_SHARE_QUANTITY = 1
MAX_SHARE_QUANTITY = 10000

# API Timeouts
SCHWAB_TIMEOUT = 30  # seconds
ANTHROPIC_TIMEOUT = 60  # seconds
