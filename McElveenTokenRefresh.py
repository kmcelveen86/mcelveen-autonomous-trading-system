#!/usr/bin/env python3
"""
McElveen Autonomous Trading System - Token Refresh Lambda
Refreshes Schwab OAuth refresh token on a daily schedule (2 AM EDT).
Uses form data authentication (not Basic Auth) per Schwab API requirements.

FIX v3.0.32: Uses corrected form data approach instead of Basic Auth.
- Stores new refresh token to DynamoDB for automatic rotation
- Persists across Lambda restarts with 7-day TTL

Deployment:
- AWS Lambda function
- Runtime: Python 3.11+
- Trigger: CloudWatch Events (daily at 2 AM EDT / 6 AM UTC)
- Timeout: 30 seconds
- Memory: 128 MB
"""

import os
import sys
import json
import boto3
import requests
from datetime import datetime, timedelta

# ============================================================================
# Configuration
# ============================================================================

SCHWAB_CLIENT_ID = os.getenv('SCHWAB_CLIENT_ID', '')
SCHWAB_CLIENT_SECRET = os.getenv('SCHWAB_CLIENT_SECRET', '')
SCHWAB_TOKEN_URL = 'https://api.schwabapi.com/v1/oauth/token'

# DynamoDB for token persistence
DYNAMODB = boto3.resource('dynamodb', region_name='us-east-2')
OAUTH_TOKENS_TABLE = os.getenv('OAUTH_TOKENS_TABLE', 'mceleven-oauth-tokens')

# SNS for alerts
SNS = boto3.client('sns', region_name='us-east-2')
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN', 'arn:aws:sns:us-east-2:650589744593:McElveenAlerts')
ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'kvmcelveen@outlook.com')

# Lambda for main trading system updates (optional)
LAMBDA = boto3.client('lambda', region_name='us-east-2')
MAIN_LAMBDA_NAME = os.getenv('MAIN_LAMBDA_NAME', 'mcelveen-trading-system')


# ============================================================================
# Token Management Functions
# ============================================================================

def get_refresh_token_from_dynamodb():
    """
    Retrieve current refresh token from DynamoDB.
    Falls back to environment variable if not found.
    """
    try:
        table = DYNAMODB.Table(OAUTH_TOKENS_TABLE)
        response = table.get_item(Key={'token_id': 'schwab-refresh-token'})

        if 'Item' in response:
            stored_token = response['Item'].get('token_value')
            print(f"[OAUTH] ✅ Retrieved refresh token from DynamoDB")
            return stored_token
    except Exception as e:
        print(f"[WARN] Failed to retrieve token from DynamoDB: {e}")

    # Fallback to environment variable
    print(f"[OAUTH] Using refresh token from environment variable")
    return os.getenv('SCHWAB_REFRESH_TOKEN', '')


def store_refresh_token_to_dynamodb(refresh_token):
    """
    Store new refresh token to DynamoDB for next rotation.
    Includes TTL for automatic cleanup after 8 days.
    """
    try:
        table = DYNAMODB.Table(OAUTH_TOKENS_TABLE)
        table.put_item(Item={
            'token_id': 'schwab-refresh-token',
            'token_value': refresh_token,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'ttl': int((datetime.utcnow() + timedelta(days=8)).timestamp())
        })
        print(f"[OAUTH] ✅ New refresh token stored in DynamoDB")
        return True
    except Exception as e:
        print(f"[WARN] Failed to store token in DynamoDB: {e}")
        return False


def refresh_schwab_token(current_refresh_token):
    """
    Exchange refresh token for new access token using form data authentication.

    FIX v3.0.32: Uses form data (credentials in request body) instead of Basic Auth.
    This matches Schwab's OAuth token endpoint requirements.

    Args:
        current_refresh_token: Valid Schwab refresh token

    Returns:
        dict: Token response with access_token, refresh_token, expires_in
        None: If exchange fails
    """
    print("[OAUTH] 🔄 Exchanging refresh token for new access token...")

    try:
        # Form data approach (correct method)
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': current_refresh_token,
            'client_id': SCHWAB_CLIENT_ID,
            'client_secret': SCHWAB_CLIENT_SECRET
        }

        response = requests.post(SCHWAB_TOKEN_URL, headers=headers, data=data, timeout=10)

        if response.status_code == 200:
            tokens = response.json()
            print(f"[OAUTH] ✅ Token exchanged successfully")
            return tokens
        else:
            print(f"[ERROR] Token exchange failed: HTTP {response.status_code}")
            print(f"[ERROR] Response: {response.text}")
            return None

    except Exception as e:
        print(f"[ERROR] Token exchange exception: {e}")
        return None


def update_main_lambda_env_variable(new_refresh_token):
    """
    Update the main trading Lambda function with new refresh token.
    Optional since DynamoDB now handles persistence.

    Args:
        new_refresh_token: Fresh refresh token from Schwab

    Returns:
        bool: True if update successful
    """
    try:
        # Get current function config
        response = LAMBDA.get_function_configuration(FunctionName=MAIN_LAMBDA_NAME)
        current_env = response.get('Environment', {}).get('Variables', {})

        # Update refresh token
        current_env['SCHWAB_REFRESH_TOKEN'] = new_refresh_token

        # Apply update
        LAMBDA.update_function_configuration(
            FunctionName=MAIN_LAMBDA_NAME,
            Environment={'Variables': current_env}
        )

        print(f"[LAMBDA] ✅ Updated {MAIN_LAMBDA_NAME} with new refresh token")
        return True

    except Exception as e:
        print(f"[WARN] Failed to update main Lambda: {e}")
        return False


def send_alert_email(subject, body):
    """Send SNS email alert."""
    try:
        SNS.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=body
        )
        print(f"[ALERT] ✅ Email sent: {subject}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send alert: {e}")
        return False


# ============================================================================
# Main Lambda Handler
# ============================================================================

def lambda_handler(event, context):
    """
    Main handler for daily token refresh.
    Runs on CloudWatch schedule: 6 AM UTC (2 AM EDT).
    """

    print("=" * 80)
    print("McElveen Autonomous Trading System - Token Refresh v3.0.32")
    print("=" * 80)
    print(f"[TIME] {datetime.utcnow().isoformat()}Z")
    print()

    # Validate credentials
    if not SCHWAB_CLIENT_ID or not SCHWAB_CLIENT_SECRET:
        msg = "[ERROR] Missing Schwab credentials in environment variables"
        print(msg)
        send_alert_email("McElveen Token Refresh - FAILED", msg)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Missing credentials'})
        }

    # Step 1: Get current refresh token
    print("[STEP 1] Retrieving current refresh token...")
    current_refresh_token = get_refresh_token_from_dynamodb()

    if not current_refresh_token:
        msg = "[ERROR] No refresh token available"
        print(msg)
        send_alert_email("McElveen Token Refresh - FAILED", msg)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'No refresh token'})
        }

    print(f"[OAUTH] Current token (last 20 chars): ...{current_refresh_token[-20:]}")
    print()

    # Step 2: Exchange for new tokens
    print("[STEP 2] Exchanging refresh token for new access token...")
    token_response = refresh_schwab_token(current_refresh_token)

    if not token_response or 'access_token' not in token_response:
        msg = "[ERROR] Token refresh failed - could not obtain new access token"
        print(msg)
        send_alert_email("McElveen Token Refresh - FAILED", msg)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Token exchange failed'})
        }

    access_token = token_response.get('access_token', '')
    new_refresh_token = token_response.get('refresh_token', '')
    expires_in = token_response.get('expires_in', 1800)

    print(f"[OAUTH] Access token expires in: {expires_in} seconds")
    print(f"[OAUTH] New refresh token (last 20 chars): ...{new_refresh_token[-20:]}")
    print()

    # Step 3: Store new refresh token to DynamoDB
    print("[STEP 3] Storing new refresh token to DynamoDB...")
    if new_refresh_token:
        store_refresh_token_to_dynamodb(new_refresh_token)
    print()

    # Step 4: Optionally update main Lambda (for backward compatibility)
    print("[STEP 4] Updating main Lambda environment variable...")
    update_main_lambda_env_variable(new_refresh_token)
    print()

    # Step 5: Send success alert
    print("[STEP 5] Sending alert email...")
    success_msg = f"""
McElveen Autonomous Trading System - Token Refresh Success ✅

Timestamp: {datetime.utcnow().isoformat()}Z
Status: Token refreshed successfully
Access Token Expiration: {expires_in} seconds
Refresh Token Validity: 7 days

Next Refresh: Tomorrow at 2:00 AM EDT

System Status: OPERATIONAL
"""
    send_alert_email("McElveen Token Refresh - SUCCESS ✅", success_msg)
    print()

    print("=" * 80)
    print("[SUCCESS] ✅ Daily token refresh completed successfully")
    print("=" * 80)

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Token refresh successful',
            'access_token_expires_in': expires_in,
            'refresh_token_expires_in': '7 days'
        })
    }


# ============================================================================
# Local Testing
# ============================================================================

if __name__ == '__main__':
    """
    Local testing - for development only.
    In production, this runs via CloudWatch Events on AWS Lambda.
    """
    print("[DEBUG] Running in local test mode")
    print()

    # Simulate Lambda event
    event = {}
    context = None

    # Call handler
    result = lambda_handler(event, context)
    print()
    print("[DEBUG] Result:", json.dumps(result, indent=2))
