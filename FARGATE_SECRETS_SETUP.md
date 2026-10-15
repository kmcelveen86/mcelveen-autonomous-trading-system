# AWS Secrets Manager Setup - McElveen Trading System

**⚠️ REQUIRED BEFORE DEPLOYMENT**

The Fargate deployment uses AWS Secrets Manager to securely store sensitive credentials. You must create these secrets before deploying.

---

## 📋 Required Secrets

### 1. Schwab Credentials

```powershell
# Account ID
aws secretsmanager create-secret `
  --name mcelveen/schwab/account-id `
  --secret-string "7720-9306" `
  --region us-east-1

# Client ID
aws secretsmanager create-secret `
  --name mcelveen/schwab/client-id `
  --secret-string "YOUR_SCHWAB_CLIENT_ID" `
  --region us-east-1

# Client Secret
aws secretsmanager create-secret `
  --name mcelveen/schwab/client-secret `
  --secret-string "YOUR_SCHWAB_CLIENT_SECRET" `
  --region us-east-1

# Refresh Token (from DynamoDB)
aws secretsmanager create-secret `
  --name mcelveen/schwab/refresh-token `
  --secret-string "YOUR_REFRESH_TOKEN" `
  --region us-east-1
```

### 2. Claude API Key

```powershell
aws secretsmanager create-secret `
  --name mcelveen/claude/api-key `
  --secret-string "sk-ant-YOUR_CLAUDE_API_KEY" `
  --region us-east-1
```

### 3. SNS Topic ARN

```powershell
# First, create SNS topic if it doesn't exist
aws sns create-topic --name mcelveen-trading-alerts --region us-east-1

# Get the topic ARN
$topicArn = aws sns list-topics --region us-east-1 --query 'Topics[?contains(TopicArn, `mcelveen-trading-alerts`)].TopicArn' --output text

# Store it in Secrets Manager
aws secretsmanager create-secret `
  --name mcelveen/sns/topic-arn `
  --secret-string $topicArn `
  --region us-east-1
```

### 4. Alert Email

```powershell
aws secretsmanager create-secret `
  --name mcelveen/alerts/email `
  --secret-string "your-email@example.com" `
  --region us-east-1
```

---

## ✅ Verification

```powershell
# List all secrets
aws secretsmanager list-secrets --region us-east-1 | grep mcelveen

# Verify specific secret (MASKED - shows only name and metadata)
aws secretsmanager describe-secret --secret-id mcelveen/schwab/client-id --region us-east-1

# Get secret value (ONLY for testing - don't log this!)
aws secretsmanager get-secret-value --secret-id mcelveen/schwab/client-id --region us-east-1 --query 'SecretString' --output text
```

---

## 🔒 IAM Permissions Required

The task execution role needs permission to read these secrets:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:mcelveen/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": [
        "arn:aws:kms:us-east-1:ACCOUNT_ID:key/*"
      ]
    }
  ]
}
```

This is automatically added by CloudFormation.

---

## 🔄 Updating Secrets

```powershell
# Update an existing secret
aws secretsmanager update-secret `
  --secret-id mcelveen/schwab/refresh-token `
  --secret-string "NEW_REFRESH_TOKEN" `
  --region us-east-1
```

---

## 📝 DynamoDB Tables Required

In addition to secrets, ensure these DynamoDB tables exist:

```powershell
# Check existing tables
aws dynamodb list-tables --region us-east-1 | grep mcelveen

# Required tables:
# - mcelveen-oauth-tokens (for token storage)
# - mcelveen-trades-table (for trade logging)
# - mcelveen-execution-log (for execution history)
# - mcelveen-portfolio-metrics (for metrics)
# - mcelveen-positions-snapshot (for position data)
```

---

## ⚡ Quick Setup Script

```powershell
# Save as: setup-secrets.ps1

$secrets = @{
    "mcelveen/schwab/account-id" = "7720-9306"
    "mcelveen/schwab/client-id" = $env:SCHWAB_CLIENT_ID
    "mcelveen/schwab/client-secret" = $env:SCHWAB_CLIENT_SECRET
    "mcelveen/schwab/refresh-token" = $env:SCHWAB_REFRESH_TOKEN
    "mcelveen/claude/api-key" = $env:CLAUDE_API_KEY
    "mcelveen/alerts/email" = "your-email@example.com"
}

foreach ($secretName in $secrets.Keys) {
    $secretValue = $secrets[$secretName]
    Write-Host "Creating secret: $secretName"
    
    aws secretsmanager create-secret `
        --name $secretName `
        --secret-string $secretValue `
        --region us-east-1 2>$null
}

Write-Host "✓ All secrets created!"
```

Run with:
```powershell
$env:SCHWAB_CLIENT_ID = "your-id"
$env:SCHWAB_CLIENT_SECRET = "your-secret"
$env:SCHWAB_REFRESH_TOKEN = "your-token"
$env:CLAUDE_API_KEY = "your-api-key"
.\setup-secrets.ps1
```

---

## 🔐 Security Best Practices

1. **Never commit secrets** to Git
2. **Use Secrets Manager** for all credentials (not environment variables)
3. **Rotate tokens regularly** (especially Schwab refresh token)
4. **Enable encryption** with AWS KMS
5. **Audit secret access** with CloudTrail
6. **Use IAM policies** to restrict secret access

---

## 📌 Before You Deploy

- [ ] All 4 secret groups created in Secrets Manager
- [ ] DynamoDB tables exist
- [ ] SNS topic created for alerts
- [ ] CloudFormation IAM permissions verified
- [ ] Schwab credentials are valid
- [ ] Claude API key is valid

**Once secrets are set up, deploy with:**
```powershell
.\scripts\deploy-to-fargate.ps1
```

---

**Last Updated:** October 14, 2026
