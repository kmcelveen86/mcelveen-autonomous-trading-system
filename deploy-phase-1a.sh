#!/bin/bash

# McElveen Autonomous Trading System - Phase 1A Deployment
# Automated AWS Infrastructure Setup
# Usage: ./deploy-phase-1a.sh <aws-profile>

set -e

AWS_PROFILE=${1:-default}
AWS_REGION="us-east-2"
ACCOUNT_ID="650589744593"

echo "=========================================="
echo "Phase 1A: AWS Infrastructure Deployment"
echo "=========================================="
echo "Profile: $AWS_PROFILE"
echo "Region: $AWS_REGION"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ===== STEP 1: Create DynamoDB Tables =====
echo -e "${BLUE}[STEP 1] Creating DynamoDB Tables...${NC}"

echo "Creating mcelveen-forex-trades table..."
aws dynamodb create-table \
  --table-name mcelveen-forex-trades \
  --attribute-definitions \
    AttributeName=Date,AttributeType=S \
    AttributeName=Timestamp,AttributeType=S \
  --key-schema \
    AttributeName=Date,KeyType=HASH \
    AttributeName=Timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || echo "  (Table may already exist)"

echo "Creating mcelveen-forex-metrics table..."
aws dynamodb create-table \
  --table-name mcelveen-forex-metrics \
  --attribute-definitions \
    AttributeName=Date,AttributeType=S \
    AttributeName=MetricType,AttributeType=S \
  --key-schema \
    AttributeName=Date,KeyType=HASH \
    AttributeName=MetricType,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || echo "  (Table may already exist)"

echo -e "${GREEN}✓ DynamoDB tables ready${NC}\n"

# ===== STEP 2: Create/Update IAM Role =====
echo -e "${BLUE}[STEP 2] Setting up IAM Role...${NC}"

ROLE_NAME="Lambda-EventBridge-Role"

# Check if role exists
if aws iam get-role --role-name $ROLE_NAME --profile $AWS_PROFILE 2>/dev/null; then
  echo "  Role $ROLE_NAME already exists"
else
  echo "Creating IAM role $ROLE_NAME..."

  # Trust policy
  cat > /tmp/trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": ["lambda.amazonaws.com", "events.amazonaws.com"]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

  aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document file:///tmp/trust-policy.json \
    --profile $AWS_PROFILE

  rm /tmp/trust-policy.json
fi

# Attach permissions policy
echo "Attaching permissions policy..."

cat > /tmp/permissions-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:$AWS_REGION:$ACCOUNT_ID:table/mcelveen-forex-trades",
        "arn:aws:dynamodb:$AWS_REGION:$ACCOUNT_ID:table/mcelveen-forex-metrics"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:$AWS_REGION:$ACCOUNT_ID:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:$AWS_REGION:$ACCOUNT_ID:function:mcelveen-*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name mcelveen-lambda-policy \
  --policy-document file:///tmp/permissions-policy.json \
  --profile $AWS_PROFILE

rm /tmp/permissions-policy.json

echo -e "${GREEN}✓ IAM role configured${NC}\n"

# ===== STEP 3: Deploy v3.0.33 Lambda =====
echo -e "${BLUE}[STEP 3] Deploying v3.0.33 Hybrid Router Lambda...${NC}"

FUNCTION_NAME="mcelveen-hybrid-trading-v3.0.33"
HANDLER="v3.0.33_hybrid_forex_system.lambda_handler"
RUNTIME="python3.11"
TIMEOUT="60"
MEMORY="512"

# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text --profile $AWS_PROFILE)

# Create zip file
echo "Packaging v3.0.33..."
zip -j /tmp/v3.0.33.zip v3.0.33_hybrid_forex_system.py > /dev/null 2>&1

# Check if function exists
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --profile $AWS_PROFILE 2>/dev/null; then
  echo "Updating $FUNCTION_NAME..."
  aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb:///tmp/v3.0.33.zip \
    --region $AWS_REGION \
    --profile $AWS_PROFILE > /dev/null

  # Update config
  aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --timeout $TIMEOUT \
    --memory-size $MEMORY \
    --environment "Variables={SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,SCHWAB_REFRESH_TOKEN=,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE > /dev/null
else
  echo "Creating $FUNCTION_NAME..."
  aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime $RUNTIME \
    --role $ROLE_ARN \
    --handler $HANDLER \
    --zip-file fileb:///tmp/v3.0.33.zip \
    --timeout $TIMEOUT \
    --memory-size $MEMORY \
    --environment "Variables={SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_ACCESS_TOKEN=,SCHWAB_REFRESH_TOKEN=,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}" \
    --region $AWS_REGION \
    --profile $AWS_PROFILE > /dev/null
fi

rm /tmp/v3.0.33.zip

echo -e "${GREEN}✓ v3.0.33 Lambda deployed${NC}\n"

# ===== STEP 4: Create EventBridge Rules =====
echo -e "${BLUE}[STEP 4] Setting up EventBridge Rules...${NC}"

ROUTER_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text --profile $AWS_PROFILE)

# Rule 1: Every 15 minutes during forex hours
RULE_1="mcelveen-forex-trading-15min"
echo "Creating rule: $RULE_1..."

aws events put-rule \
  --name $RULE_1 \
  --schedule-expression "rate(15 minutes)" \
  --state ENABLED \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || true

# Add Lambda target
aws events put-targets \
  --rule $RULE_1 \
  --targets "Id"="1","Arn"="$ROUTER_ARN","RoleArn"="$ROLE_ARN" \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || true

# Allow EventBridge to invoke Lambda
aws lambda add-permission \
  --function-name $FUNCTION_NAME \
  --statement-id "AllowEventBridgeInvoke" \
  --action "lambda:InvokeFunction" \
  --principal "events.amazonaws.com" \
  --source-arn "arn:aws:events:$AWS_REGION:$ACCOUNT_ID:rule/$RULE_1" \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || true

# Rule 2: Daily at 4:01 PM ET for reports
RULE_2="mcelveen-forex-report-4pm"
echo "Creating rule: $RULE_2..."

aws events put-rule \
  --name $RULE_2 \
  --schedule-expression "cron(1 16 ? * MON-FRI *)" \
  --state ENABLED \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || true

aws events put-targets \
  --rule $RULE_2 \
  --targets "Id"="1","Arn"="$ROUTER_ARN","RoleArn"="$ROLE_ARN" \
  --region $AWS_REGION \
  --profile $AWS_PROFILE 2>/dev/null || true

echo -e "${GREEN}✓ EventBridge rules configured${NC}\n"

# ===== STEP 5: Validation =====
echo -e "${BLUE}[STEP 5] Validating Deployment...${NC}"

echo "Checking DynamoDB tables..."
aws dynamodb list-tables --region $AWS_REGION --profile $AWS_PROFILE | grep -q "mcelveen-forex-trades" && echo "  ✓ mcelveen-forex-trades" || echo "  ✗ mcelveen-forex-trades NOT FOUND"
aws dynamodb list-tables --region $AWS_REGION --profile $AWS_PROFILE | grep -q "mcelveen-forex-metrics" && echo "  ✓ mcelveen-forex-metrics" || echo "  ✗ mcelveen-forex-metrics NOT FOUND"

echo "Checking Lambda function..."
aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --profile $AWS_PROFILE > /dev/null && echo "  ✓ $FUNCTION_NAME deployed" || echo "  ✗ $FUNCTION_NAME NOT FOUND"

echo "Checking EventBridge rules..."
aws events list-rules --name-prefix "mcelveen-forex" --region $AWS_REGION --profile $AWS_PROFILE | grep -q "mcelveen-forex-trading-15min" && echo "  ✓ mcelveen-forex-trading-15min" || echo "  ✗ Rule NOT FOUND"

echo ""
echo "=========================================="
echo -e "${GREEN}Phase 1A Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Set SCHWAB_REFRESH_TOKEN in Lambda environment:"
echo "   aws lambda update-function-configuration --function-name $FUNCTION_NAME --environment Variables='{SCHWAB_ACCOUNT_ID=7720-9306,SCHWAB_REFRESH_TOKEN=<your-token>,FOREX_TRADES_TABLE=mcelveen-forex-trades,FOREX_METRICS_TABLE=mcelveen-forex-metrics}' --region $AWS_REGION --profile $AWS_PROFILE"
echo ""
echo "2. Test the router:"
echo "   aws lambda invoke --function-name $FUNCTION_NAME --region $AWS_REGION --profile $AWS_PROFILE /tmp/response.json && cat /tmp/response.json | jq ."
echo ""
echo "3. Proceed to Phase 1B deployment:"
echo "   ./deploy-phase-1b.sh $AWS_PROFILE"
echo ""
