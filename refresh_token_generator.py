#!/usr/bin/env python3
"""
McElveen Autonomous Trading System - Schwab OAuth Token Generator
Automates the OAuth authorization code flow to obtain a fresh refresh_token
without manual copy-paste delays that cause code expiration.

Usage:
    python3 refresh_token_generator.py
"""

import os
import sys
import json
import time
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from datetime import datetime
import requests

# ============================================================================
# Configuration
# ============================================================================

SCHWAB_CLIENT_ID = os.getenv('SCHWAB_CLIENT_ID', '')
SCHWAB_CLIENT_SECRET = os.getenv('SCHWAB_CLIENT_SECRET', '')
SCHWAB_AUTH_URL = 'https://api.schwabapi.com/v1/oauth/authorize'
SCHWAB_TOKEN_URL = 'https://api.schwabapi.com/v1/oauth/token'
REDIRECT_URI = 'http://localhost:8080/callback'
CALLBACK_PORT = 8080

# Global state
authorization_code = None
server_ready = False


# ============================================================================
# OAuth Callback Handler
# ============================================================================

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the authorization code from Schwab redirect."""

    def do_GET(self):
        global authorization_code

        # Parse the callback URL
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Extract authorization code or error
        if 'code' in query_params:
            authorization_code = query_params['code'][0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            html = '''
                <html>
                <head><title>Authorization Successful</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>[OK] Authorization Successful</h1>
                    <p>You can close this window and return to the terminal.</p>
                    <p style="color: green; font-weight: bold;">Authorization code captured!</p>
                </body>
                </html>
            '''
            self.wfile.write(html.encode('utf-8'))
        else:
            error = query_params.get('error', ['Unknown error'])[0]
            error_desc = query_params.get('error_description', [''])[0]
            self.send_response(400)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            html = f'''
                <html>
                <head><title>Authorization Failed</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h1>[ERROR] Authorization Failed</h1>
                    <p><strong>Error:</strong> {error}</p>
                    <p><strong>Description:</strong> {error_desc}</p>
                </body>
                </html>
            '''
            self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        """Suppress verbose logging."""
        pass


# ============================================================================
# Main OAuth Flow
# ============================================================================

def start_callback_server():
    """Start HTTP server to listen for OAuth callback."""
    global server_ready
    try:
        server = HTTPServer(('localhost', CALLBACK_PORT), OAuthCallbackHandler)
        server_ready = True
        print(f"[OAUTH] ✅ Callback server listening on {REDIRECT_URI}")

        # Run server in background, but stop after we get the code
        while authorization_code is None:
            server.handle_request()
            if authorization_code:
                break

        server.server_close()
    except Exception as e:
        print(f"[ERROR] Failed to start callback server: {e}")
        sys.exit(1)


def get_authorization_url():
    """Generate the Schwab OAuth authorization URL."""
    params = {
        'client_id': SCHWAB_CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': 'PlaceTrades AccountAccess MoveMoney'
    }
    return f"{SCHWAB_AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code):
    """Exchange authorization code for access and refresh tokens."""
    print("[OAUTH] 🔄 Exchanging authorization code for tokens...")

    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': SCHWAB_CLIENT_ID,
        'client_secret': SCHWAB_CLIENT_SECRET
    }

    try:
        response = requests.post(SCHWAB_TOKEN_URL, data=payload, timeout=10)
        response.raise_for_status()
        tokens = response.json()
        return tokens
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Token exchange failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"[ERROR] Response: {e.response.text}")
        sys.exit(1)


def main():
    """Main OAuth flow orchestration."""
    global authorization_code

    print("=" * 80)
    print("McElveen Autonomous Trading System - OAuth Token Generator")
    print("=" * 80)
    print()

    # Validate credentials
    if not SCHWAB_CLIENT_ID or not SCHWAB_CLIENT_SECRET:
        print("[ERROR] ❌ Missing credentials!")
        print("Set these environment variables:")
        print("  export SCHWAB_CLIENT_ID='...'")
        print("  export SCHWAB_CLIENT_SECRET='...'")
        sys.exit(1)

    print(f"[CONFIG] Client ID: {SCHWAB_CLIENT_ID[:20]}...")
    print(f"[CONFIG] Redirect URI: {REDIRECT_URI}")
    print()

    # Start callback server in background
    print("[SETUP] Starting OAuth callback server...")
    server_thread = Thread(target=start_callback_server, daemon=True)
    server_thread.start()
    time.sleep(1)  # Give server time to start

    if not server_ready:
        print("[ERROR] Failed to start callback server")
        sys.exit(1)

    # Generate OAuth URL and open browser
    auth_url = get_authorization_url()
    print("[OAUTH] 🌐 Opening browser to Schwab authorization page...")
    print(f"[OAUTH] Authorization URL: {auth_url}")
    print()
    print("⏳ Waiting for authorization...")
    print("   1. A browser will open to Schwab OAuth")
    print("   2. Login with your Schwab credentials")
    print("   3. Accept the permissions")
    print("   4. We'll automatically capture the authorization code")
    print()

    # Open browser
    webbrowser.open(auth_url)

    # Wait for authorization code
    timeout = 300  # 5 minutes
    start_time = time.time()
    while authorization_code is None:
        if time.time() - start_time > timeout:
            print("[ERROR] ❌ Timeout waiting for authorization (5 minutes)")
            sys.exit(1)
        time.sleep(0.5)

    print()
    print(f"[OAUTH] ✅ Authorization code captured!")
    print()

    # Exchange code for tokens
    tokens = exchange_code_for_tokens(authorization_code)

    if 'error' in tokens:
        print(f"[ERROR] Token exchange error: {tokens['error']}")
        if 'error_description' in tokens:
            print(f"[ERROR] {tokens['error_description']}")
        sys.exit(1)

    # Extract tokens
    access_token = tokens.get('access_token', '')
    refresh_token = tokens.get('refresh_token', '')
    expires_in = tokens.get('expires_in', 0)

    print("[OAUTH] ✅ Successfully obtained tokens!")
    print()
    print("=" * 80)
    print("📋 COPY THIS REFRESH TOKEN TO LAMBDA")
    print("=" * 80)
    print()
    print(f"Refresh Token:\n{refresh_token}\n")
    print("=" * 80)
    print()
    print(f"[INFO] Access token expires in: {expires_in} seconds")
    print(f"[INFO] Refresh token valid for: 7 days")
    print()
    print("Next steps:")
    print("  1. Copy the refresh token above")
    print("  2. Go to AWS Lambda Console → mcelveen-trading-system → Configuration")
    print("  3. Environment variables → Edit → SCHWAB_REFRESH_TOKEN")
    print("  4. Paste the token and Save")
    print("  5. Wait 1-2 minutes for Lambda to reload")
    print("  6. Run Lambda manually to verify v3.0.32 deployment")
    print()

    # Save token to a file for reference
    output_file = '/tmp/schwab_refresh_token.txt'
    with open(output_file, 'w') as f:
        f.write(refresh_token)
    print(f"[INFO] Token also saved to: {output_file}")


if __name__ == '__main__':
    main()
