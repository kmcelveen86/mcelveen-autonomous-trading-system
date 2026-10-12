#!/bin/bash

# McElveen Autonomous Trading System - v3.0.37 Deployment
# Deploys the fixed lambda_function.py to mcelveen-autonomous-forex

set -e

AWS_PROFILE=${1:-default}
AWS_REGION="us-east-2"
FUNCTION_NAME="mcelveen-autonomous-forex"

echo "=========================================="
echo "v3.0.37 Deployment: Schwab API Fix"
echo "=========================================="
echo "Function: $FUNCTION_NAME"
echo "Region: $AWS_REGION"
echo "Profile: $AWS_PROFILE"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Step 1: Package the code
echo -e "${BLUE}[STEP 1] Packaging lambda_function.py...${NC}"
cd /home/claude/mcelveen-autonomous-trading-system
zip -j /tmp/v3.0.37.zip lambda_function.py > /dev/null 2>&1
echo -e "${GREEN}✓ Code packaged${NC}\n"

# Step 2: Get current function config
echo -e "${BLUE}[STEP 2] Checking Lambda function...${NC}"
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --profile $AWS_PROFILE > /dev/null 2>&1; then
  echo -e "${GREEN}✓ Found: $FUNCTION_NAME${NC}"
else
  echo -e "${RED}✗ Function not found: $FUNCTION_NAME${NC}"
  exit 1
fi
echo ""

# Step 3: Update function code
echo -e "${BLUE}[STEP 3] Updating function code...${NC}"
aws lambda update-function-code \
  --function-name $FUNCTION_NAME \
  --zip-file fileb:///tmp/v3.0.37.zip \
  --region $AWS_REGION \
  --profile $AWS_PROFILE > /dev/null 2>&1

echo -e "${GREEN}✓ Code updated${NC}\n"

# Step 4: Verify deployment
echo -e "${BLUE}[STEP 4] Verifying deployment...${NC}"
sleep 3  # Wait for Lambda to finish updating

LAST_MODIFIED=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --profile $AWS_PROFILE --query 'Configuration.LastModified' --output text 2>/dev/null)
echo -e "${GREEN}✓ Last Modified: $LAST_MODIFIED${NC}\n"

# Step 5: Test the function
echo -e "${BLUE}[STEP 5] Running test execution...${NC}"
aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --region $AWS_REGION \
  --profile $AWS_PROFILE \
  --payload '{}' \
  /tmp/v3.0.37-response.json > /dev/null 2>&1

if [ -f /tmp/v3.0.37-response.json ]; then
  echo -e "${GREEN}✓ Test execution completed${NC}"
  echo "Response:"
  cat /tmp/v3.0.37-response.json | jq . 2>/dev/null || cat /tmp/v3.0.37-response.json
else
  echo -e "${YELLOW}⚠ Response file not found${NC}"
fi
echo ""

# Cleanup
rm -f /tmp/v3.0.37.zip /tmp/v3.0.37-response.json

echo "=========================================="
echo -e "${GREEN}v3.0.37 Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Deployed Fixes:"
echo "✅ FIX #1: Correct Schwab market data endpoint"
echo "   - Changed from: /trader/v1/marketdata/quotes"
echo "   - Changed to: /marketdata/v1/quotes"
echo ""
echo "✅ FIX #2: Defensive Portfolio Manager"
echo "   - Added check for empty holdings_scores"
echo "   - Prevents min() arg is an empty sequence error"
echo ""
echo "Next Steps:"
echo "1. Monitor CloudWatch logs for next execution:"
echo "   aws logs tail /aws/lambda/$FUNCTION_NAME --follow --region $AWS_REGION --profile $AWS_PROFILE"
echo ""
echo "2. Check for clean execution (zero errors):"
echo "   - All Schwab API calls return HTTP 200"
echo "   - Market data endpoint returns valid quotes"
echo "   - Portfolio Manager completes without crashes"
echo ""
echo "3. Once confirmed clean, proceed with forex integration:"
echo "   ./deploy-phase-1b.sh $AWS_PROFILE"
echo ""
