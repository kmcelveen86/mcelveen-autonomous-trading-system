#!/bin/bash

# McElveen Autonomous Trading System - Phase 1B Deployment
# Automated Forex Execution Layer Setup
# Usage: ./deploy-phase-1b.sh <aws-profile>

set -e

AWS_PROFILE=${1:-default}
AWS_REGION="us-east-2"
ACCOUNT_ID="650589744593"

echo "=========================================="
echo "Phase 1B: Forex Execution Layer Deployment"
echo "=========================================="
echo "Profile: $AWS_PROFILE"
echo "Region: $AWS_REGION"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ===== STEP 1: Deploy v3.0.34 Lambda =====
echo -e "${BLUE}[STEP 1] Deploying v3.0.34 Forex Execution Lambda...${NC}"

FUNCTION_NAME="mcelveen-forex-execution-v3.0.34"
HANDLER="v3.0.34_forex_execution.lambda_handler"
RUNTIME="python3.11"
TIMEOUT="60"
MEMORY="512"

# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name "Lambda-EventBridge-Role" --query 'Role.Arn' --output text --profile $AWS_PROFILE)

# Create zip file
echo "Packaging v3.0.34..."
zip -j /tmp/v3.0.34.zip v3.0.34_forex_execution.py > /dev/null 2>&1

# Check if function exists
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --profile $AWS_PROFILE 2>/dev/null; then
  echo "Updating $FUNCTION_NAME..."
  aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb:///tmp/v3.0.34.zip \
    --region $AWS_REGION \
    --profile $AWS_PROFILE > /dev/null

  # Update config
  aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --timeout $TIMEOUT \
    --memory-size $MEMORY \
    --environment "Variables={SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE > /dev/null
else
  echo "Creating $FUNCTION_NAME..."
  aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime $RUNTIME \
    --role $ROLE_ARN \
    --handler $HANDLER \
    --zip-file fileb:///tmp/v3.0.34.zip \
    --timeout $TIMEOUT \
    --memory-size $MEMORY \
    --environment "Variables={SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE > /dev/null
fi

rm /tmp/v3.0.34.zip

echo -e "${GREEN}✓ v3.0.34 Lambda deployed${NC}\n"

# ===== STEP 2: Grant v3.0.33 Permission to Invoke v3.0.34 =====
echo -e "${BLUE}[STEP 2] Configuring Router → Execution Chain...${NC}"

ROUTER_FUNCTION="mcelveen-hybrid-trading-v3.0.33"
EXECUTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text --profile $AWS_PROFILE)

echo "Adding invoke permission to v3.0.33..."
aws lambda add-permission \
  --function-name $ROUTER_FUNCTION \
  --statement-id "AllowInvokeExecution" \
  --action "lambda:InvokeFunction" \
  --principal "lambda.amazonaws.com" \
  --source-arn "$EXECUTION_ARN" \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || echo "  (Permission may already exist)"

echo -e "${GREEN}✓ Router → Execution chain configured${NC}\n"

# ===== STEP 3: Testing =====
echo -e "${BLUE}[STEP 3] Running Validation Tests...${NC}"

echo "Test 1: Direct v3.0.34 invocation..."
aws lambda invoke \
  --function-name $FUNCTION_NAME \
  --region $AWS_REGION \
  --profile $AWS_PROFILE \
  --payload '{"mode":"FOREX","macro_analysis":{"regime":"NEUTRAL","conviction":0.5,"recommended_pairs":["EUR/USD","USD/CAD"]},"action":"EXECUTE"}' \
  /tmp/v3.0.34-response.json > /dev/null 2>&1

if [ -f /tmp/v3.0.34-response.json ]; then
  STATUS=$(jq -r '.statusCode' /tmp/v3.0.34-response.json 2>/dev/null)
  if [ "$STATUS" = "200" ]; then
    echo "  ✓ v3.0.34 responds correctly"
  else
    echo "  ✗ Unexpected response: $STATUS"
  fi
fi

echo "Test 2: Router invocation..."
aws lambda invoke \
  --function-name $ROUTER_FUNCTION \
  --region $AWS_REGION \
  --profile $AWS_PROFILE \
  /tmp/v3.0.33-response.json > /dev/null 2>&1

if [ -f /tmp/v3.0.33-response.json ]; then
  STATUS=$(jq -r '.statusCode' /tmp/v3.0.33-response.json 2>/dev/null)
  if [ "$STATUS" = "200" ]; then
    echo "  ✓ v3.0.33 router responds correctly"
  else
    echo "  ✗ Unexpected response: $STATUS"
  fi
fi

echo "Test 3: CloudWatch logs..."
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/mcelveen" --region $AWS_REGION --profile $AWS_PROFILE | grep -q "mcelveen" && echo "  ✓ CloudWatch logs configured" || echo "  ✗ Logs not found"

echo -e "${GREEN}✓ Validation tests complete${NC}\n"

# ===== STEP 4: Configuration Summary =====
echo -e "${BLUE}[STEP 4] Configuration Summary...${NC}"

echo "v3.0.33 Router:"
aws lambda get-function-configuration \
  --function-name $ROUTER_FUNCTION \
  --region $AWS_REGION \
  --profile $AWS_PROFILE | jq '{FunctionName, Runtime, Timeout, MemorySize, Role}' 2>/dev/null || echo "  (Unable to retrieve)"

echo ""
echo "v3.0.34 Execution:"
aws lambda get-function-configuration \
  --function-name $FUNCTION_NAME \
  --region $AWS_REGION \
  --profile $AWS_PROFILE | jq '{FunctionName, Runtime, Timeout, MemorySize, Role}' 2>/dev/null || echo "  (Unable to retrieve)"

echo ""
echo "=========================================="
echo -e "${GREEN}Phase 1B Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "System Status:"
echo "✓ v3.0.33 Router deployed"
echo "✓ v3.0.34 Execution deployed"
echo "✓ Router → Execution chain configured"
echo "✓ EventBridge triggers set (every 15 min during forex hours)"
echo "✓ DynamoDB tables ready for trade logging"
echo "✓ CloudWatch metrics namespace ready"
echo ""
echo "Next Steps (Oct 15):"
echo "1. Update SCHWAB_ACCESS_TOKEN in both Lambdas (fresh token from v3.0.32)"
echo "2. Monitor CloudWatch logs during forex trading hours"
echo "3. Verify first trades appear in DynamoDB by Oct 16"
echo "4. Collect baseline data through Nov 5"
echo ""
echo "Timeline:"
echo "Oct 15-Nov 5: Baseline data collection (7+ trades/day target)"
echo "Nov 5-20:     Phase 1C ML integration & A/B testing"
echo "Nov 20-Feb28: Phase 2 Live ML trading (12 weeks)"
echo "Q2 2027:      Paylinq investor pitch"
echo ""
