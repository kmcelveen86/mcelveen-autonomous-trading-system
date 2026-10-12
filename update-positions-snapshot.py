#!/usr/bin/env python3
"""
Update POSITIONS_SNAPSHOT_TABLE with current holdings from Schwab
Usage: python3 update-positions-snapshot.py
Requirements: AWS credentials configured (aws configure)
"""

import boto3
import json
import sys
from datetime import datetime

# Your current holdings from Schwab screenshot (2026-10-12 11:02 EDT)
current_holdings = {
    'AGS': {
        'symbol': 'AGS',
        'quantity': 0.07,
        'cost_basis': 6.62,
        'current_price': 94.59,
        'market_value': 6.62,
        'sector': 'FINANCE',
        'asset_class': 'STOCK'
    },
    'MRK': {
        'symbol': 'MRK',
        'quantity': 0.02,
        'cost_basis': 2.90,
        'current_price': 145.60,
        'market_value': 2.90,
        'sector': 'HEALTHCARE',
        'asset_class': 'STOCK'
    },
    'MSTR': {
        'symbol': 'MSTR',
        'quantity': 0.0096,
        'cost_basis': 5.19,
        'current_price': 535.07,
        'market_value': 5.19,
        'sector': 'TECHNOLOGY',
        'asset_class': 'STOCK'
    },
    'SPY': {
        'symbol': 'SPY',
        'quantity': 0.0137,
        'cost_basis': 10.66,
        'current_price': 778.57,
        'market_value': 10.66,
        'sector': 'BROAD',
        'asset_class': 'BROAD_ETF'
    },
    'VEA': {
        'symbol': 'VEA',
        'quantity': 0.02,
        'cost_basis': 1.40,
        'current_price': 70.35,
        'market_value': 1.40,
        'sector': 'BROAD',
        'asset_class': 'BROAD_ETF'
    },
    'VIG': {
        'symbol': 'VIG',
        'quantity': 0.0085,
        'cost_basis': 2.04,
        'current_price': 239.05,
        'market_value': 2.04,
        'sector': 'DIVIDEND',
        'asset_class': 'DIVIDEND_ETF'
    },
    'VTI': {
        'symbol': 'VTI',
        'quantity': 0.0053,
        'cost_basis': 2.02,
        'current_price': 381.54,
        'market_value': 2.02,
        'sector': 'BROAD',
        'asset_class': 'BROAD_ETF'
    },
    'WMT': {
        'symbol': 'WMT',
        'quantity': 0.0411,
        'cost_basis': 4.61,
        'current_price': 111.35,
        'market_value': 4.61,
        'sector': 'CONSUMER',
        'asset_class': 'STOCK'
    },
    'XLE': {
        'symbol': 'XLE',
        'quantity': 0.02,
        'cost_basis': 1.31,
        'current_price': 65.68,
        'market_value': 1.31,
        'sector': 'ENERGY',
        'asset_class': 'SECTOR_ETF'
    },
    'XOM': {
        'symbol': 'XOM',
        'quantity': 0.019,
        'cost_basis': 3.26,
        'current_price': 171.01,
        'market_value': 3.26,
        'sector': 'ENERGY',
        'asset_class': 'STOCK'
    }
}

def update_positions_snapshot():
    """Update DynamoDB with current holdings snapshot."""
    try:
        # Connect to DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
        table = dynamodb.Table('mcelveen-positions-snapshot')

        # Create snapshot item
        timestamp = datetime.utcnow().isoformat()
        snapshot_item = {
            'SnapshotTime': timestamp,
            'HoldingsCount': len(current_holdings),
            'Holdings': json.dumps(current_holdings),
            'CreatedAt': timestamp,
            'Source': 'Manual update from Schwab screenshot 2026-10-12'
        }

        # Write to DynamoDB
        table.put_item(Item=snapshot_item)

        # Print summary
        print("=" * 80)
        print("✅ POSITIONS_SNAPSHOT_TABLE UPDATED SUCCESSFULLY")
        print("=" * 80)
        print(f"Timestamp: {timestamp}")
        print(f"Holdings count: {len(current_holdings)}")
        print(f"Total market value: ${sum(h['market_value'] for h in current_holdings.values()):.2f}")
        print(f"\nHoldings:")
        for sym, h in sorted(current_holdings.items()):
            print(f"  {sym:6s} {h['quantity']:8.4f} @ ${h['current_price']:8.2f} = ${h['market_value']:8.2f}")

        print("\n" + "=" * 80)
        print("Next execution will use this fresh snapshot instead of stale trade journal")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"❌ Error updating snapshot: {e}")
        print(f"\nPlease configure AWS credentials:")
        print("  aws configure")
        print(f"\nOr set environment variables:")
        print("  export AWS_ACCESS_KEY_ID=your_key")
        print("  export AWS_SECRET_ACCESS_KEY=your_secret")
        print("  export AWS_DEFAULT_REGION=us-east-2")
        return False

if __name__ == '__main__':
    success = update_positions_snapshot()
    sys.exit(0 if success else 1)
