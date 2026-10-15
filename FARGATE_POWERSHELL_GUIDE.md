# Fargate Deployment - PowerShell Quick Guide

**Update:** All scripts are now PowerShell-first for AWS infrastructure automation.

---

## 🚀 Quick Deploy (PowerShell)

### 1. Set Environment Variables
```powershell
$env:AWS_REGION = "us-east-1"
$env:AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$env:VPC_ID = "vpc-xxxxxxxx"
$env:SUBNET_IDS = "subnet-xxx,subnet-yyy"
$env:ENVIRONMENT = "production"

# Verify
echo "Account: $env:AWS_ACCOUNT_ID, VPC: $env:VPC_ID"
```

### 2. Deploy Everything
```powershell
cd C:\Path\To\mcelveen-repo
.\scripts\deploy-to-fargate.ps1
```

### 3. Monitor
```powershell
# View logs in real-time
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1

# List running tasks
aws ecs list-tasks --cluster mcelveen-production --region us-east-1

# Describe cluster
aws ecs describe-clusters --clusters mcelveen-production --region us-east-1
```

---

## 📋 Common PowerShell Commands

### Deploy with Skip CloudFormation
```powershell
.\scripts\deploy-to-fargate.ps1 -SkipCloudFormation
```

### Enable Trading Rules (Before Market Open)
```powershell
.\scripts\trading-schedule.ps1 -Action enable
```

### Disable Trading Rules (After Market Close)
```powershell
.\scripts\trading-schedule.ps1 -Action disable
```

### View CloudWatch Logs
```powershell
# All logs (latest 50 lines)
aws logs tail /ecs/mcelveen-trading-system --region us-east-1

# Follow in real-time
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1

# Last 100 lines
aws logs tail /ecs/mcelveen-trading-system --max-items 100 --region us-east-1

# Daily Report logs
aws logs tail /ecs/mcelveen-daily-report --follow --region us-east-1

# Token Refresh logs
aws logs tail /ecs/mcelveen-token-refresh --follow --region us-east-1
```

### Check ECS Resources
```powershell
# List clusters
aws ecs list-clusters --region us-east-1

# List services in cluster
aws ecs list-services --cluster mcelveen-production --region us-east-1

# Describe services
aws ecs describe-services `
  --cluster mcelveen-production `
  --services mcelveen-token-refresh-service `
  --region us-east-1

# List running tasks
aws ecs list-tasks `
  --cluster mcelveen-production `
  --region us-east-1

# Describe a specific task
aws ecs describe-tasks `
  --cluster mcelveen-production `
  --tasks <task-arn> `
  --region us-east-1
```

### Check EventBridge Rules
```powershell
# List all EventBridge rules
aws events list-rules --region us-east-1 | Select-String "mcelveen"

# Check specific rule status
aws events describe-rule --name mcelveen-trading-system-9 --region us-east-1

# List all trading system rules
$hours = 9, 10, 11, 12, 13, 14, 15, 16
foreach ($hour in $hours) {
    $rule = "mcelveen-trading-system-$hour"
    $status = aws events describe-rule --name $rule --region us-east-1 --query 'State' --output text
    Write-Host "Rule: $rule - State: $status"
}

# List targets for a rule
aws events list-targets-by-rule `
  --rule mcelveen-trading-system-9 `
  --region us-east-1
```

### Manually Run a Trading Task
```powershell
# Get cluster info
$cluster = "mcelveen-production"
$taskDef = "mcelveen-trading-system:1"
$subnetId = aws ec2 describe-subnets `
  --filters "Name=vpc-id,Values=$env:VPC_ID" `
  --query 'Subnets[0].SubnetId' `
  --output text
$securityGroup = aws ec2 describe-security-groups `
  --filters "Name=tag:Name,Values=mcelveen-ecs-sg*" `
  --query 'SecurityGroups[0].GroupId' `
  --output text

# Run task
aws ecs run-task `
  --cluster $cluster `
  --task-definition $taskDef `
  --launch-type FARGATE `
  --network-configuration "awsvpcConfiguration={subnets=[$subnetId],securityGroups=[$securityGroup],assignPublicIp=DISABLED}" `
  --region us-east-1

# Monitor logs
aws logs tail /ecs/mcelveen-trading-system --follow --region us-east-1
```

### Stop a Running Task
```powershell
# Get running task ARN
$taskArn = aws ecs list-tasks `
  --cluster mcelveen-production `
  --region us-east-1 `
  --query 'taskArns[0]' `
  --output text

# Stop task
if ($taskArn) {
    aws ecs stop-task `
      --cluster mcelveen-production `
      --task $taskArn `
      --region us-east-1
    Write-Host "Task stopped: $taskArn"
} else {
    Write-Host "No running tasks found"
}
```

### Update Token Refresh Service (Scale)
```powershell
# Change desired count to 2 instances
aws ecs update-service `
  --cluster mcelveen-production `
  --service mcelveen-token-refresh-service `
  --desired-count 2 `
  --region us-east-1

# Verify
aws ecs describe-services `
  --cluster mcelveen-production `
  --services mcelveen-token-refresh-service `
  --region us-east-1 `
  --query 'services[0].[desiredCount,runningCount,status]' `
  --output text
```

### Local Testing with Docker
```powershell
# Navigate to docker directory
cd docker

# Start services
docker-compose -f docker-compose.yml up -d

# Wait for startup
Start-Sleep -Seconds 30

# Test health checks
$checks = @(
    @{ name = "Trading System"; port = 8001 },
    @{ name = "Daily Report"; port = 8002 },
    @{ name = "Token Refresh"; port = 8003 }
)

foreach ($check in $checks) {
    $response = Invoke-WebRequest -Uri "http://localhost:$($check.port)/health" -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ $($check.name) is healthy" -ForegroundColor Green
    } else {
        Write-Host "✗ $($check.name) failed" -ForegroundColor Red
    }
}

# View logs
docker-compose -f docker-compose.yml logs -f

# Stop services
docker-compose -f docker-compose.yml down
```

---

## 🔍 Troubleshooting PowerShell

### Check If AWS CLI is Accessible
```powershell
Get-Command aws
aws --version
```

### Check Docker
```powershell
Get-Command docker
docker --version
```

### Set Execution Policy (if needed)
```powershell
# Allow script execution (current user, current session)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Or for the script only
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-to-fargate.ps1
```

### Clear CloudFormation Stack (Rollback)
```powershell
# Delete the stack
aws cloudformation delete-stack `
  --stack-name mcelveen-ecs-production `
  --region us-east-1

# Wait for deletion
aws cloudformation wait stack-delete-complete `
  --stack-name mcelveen-ecs-production `
  --region us-east-1

Write-Host "Stack deleted successfully"
```

### Delete ECR Images
```powershell
# Delete repositories
$repos = @("mcelveen-trading-system", "mcelveen-daily-report", "mcelveen-token-refresh")
foreach ($repo in $repos) {
    Write-Host "Deleting $repo..."
    aws ecr delete-repository `
      --repository-name $repo `
      --force `
      --region us-east-1
}
```

---

## 📊 PowerShell Monitoring Scripts

### Create a Monitoring Dashboard Function
```powershell
function Get-McElveenStatus {
    param(
        [string]$Region = "us-east-1",
        [string]$Environment = "production"
    )
    
    $cluster = "mcelveen-$Environment"
    
    Write-Host "=== McElveen Trading System Status ===" -ForegroundColor Cyan
    Write-Host ""
    
    # Cluster status
    Write-Host "Cluster: $cluster" -ForegroundColor Green
    $clusterStatus = aws ecs describe-clusters `
        --clusters $cluster `
        --region $Region `
        --query 'clusters[0].status' `
        --output text
    Write-Host "  Status: $clusterStatus"
    
    # Services
    Write-Host ""
    Write-Host "Services:" -ForegroundColor Green
    $services = aws ecs list-services `
        --cluster $cluster `
        --region $Region `
        --query 'serviceArns[]' `
        --output text
    
    foreach ($serviceArn in $services -split '\s+') {
        if ($serviceArn) {
            $serviceName = $serviceArn -split '/' | Select-Object -Last 1
            $details = aws ecs describe-services `
                --cluster $cluster `
                --services $serviceName `
                --region $Region `
                --query 'services[0]' `
                --output json | ConvertFrom-Json
            
            Write-Host "  $serviceName" -ForegroundColor Cyan
            Write-Host "    Desired: $($details.desiredCount), Running: $($details.runningCount), Status: $($details.status)"
        }
    }
    
    # Running tasks
    Write-Host ""
    Write-Host "Running Tasks:" -ForegroundColor Green
    $tasks = aws ecs list-tasks `
        --cluster $cluster `
        --region $Region `
        --query 'taskArns' `
        --output text
    
    if ($tasks) {
        $taskCount = ($tasks -split '\s+' | Where-Object { $_ }).Count
        Write-Host "  Count: $taskCount"
    } else {
        Write-Host "  No running tasks"
    }
    
    Write-Host ""
}

# Usage: Get-McElveenStatus
```

### Real-time Log Monitoring
```powershell
function Watch-McElveenLogs {
    param(
        [ValidateSet("trading-system", "daily-report", "token-refresh")]
        [string]$Service = "trading-system",
        
        [string]$Region = "us-east-1"
    )
    
    $logGroup = "/ecs/mcelveen-$Service"
    Write-Host "Tailing logs for $Service..." -ForegroundColor Green
    Write-Host "(Ctrl+C to stop)" -ForegroundColor Yellow
    Write-Host ""
    
    aws logs tail $logGroup --follow --region $Region
}

# Usage: Watch-McElveenLogs -Service trading-system
```

---

## 🎯 Pre-Market Checklist (PowerShell)

```powershell
# Save as: check-trading-readiness.ps1
Write-Host "=== Pre-Market Readiness Check ===" -ForegroundColor Green
Write-Host ""

# 1. Verify cluster is running
Write-Host "1. Checking cluster..." -ForegroundColor Cyan
$cluster = aws ecs describe-clusters `
  --clusters mcelveen-production `
  --region us-east-1 `
  --query 'clusters[0].status' `
  --output text

if ($cluster -eq "ACTIVE") {
    Write-Host "   ✓ Cluster is active" -ForegroundColor Green
} else {
    Write-Host "   ✗ Cluster is not active: $cluster" -ForegroundColor Red
}

# 2. Verify token refresh is running
Write-Host "2. Checking token refresh service..." -ForegroundColor Cyan
$tokenService = aws ecs describe-services `
  --cluster mcelveen-production `
  --services mcelveen-token-refresh-service `
  --region us-east-1 `
  --query 'services[0]' `
  --output json | ConvertFrom-Json

if ($tokenService.runningCount -ge 1) {
    Write-Host "   ✓ Token refresh service is running" -ForegroundColor Green
} else {
    Write-Host "   ✗ Token refresh service has no running tasks" -ForegroundColor Red
}

# 3. Verify EventBridge rules are enabled
Write-Host "3. Checking EventBridge rules..." -ForegroundColor Cyan
$ruleStatus = aws events describe-rule `
  --name mcelveen-trading-system-9 `
  --region us-east-1 `
  --query 'State' `
  --output text

if ($ruleStatus -eq "ENABLED") {
    Write-Host "   ✓ Trading system rules are enabled" -ForegroundColor Green
} else {
    Write-Host "   ✗ Trading system rules are disabled" -ForegroundColor Red
}

Write-Host ""
Write-Host "✓ Pre-market check complete!" -ForegroundColor Green
```

---

## 📚 Files Reference

| File | Purpose |
|------|---------|
| `scripts/deploy-to-fargate.ps1` | Main deployment script (PowerShell) |
| `scripts/trading-schedule.ps1` | Enable/disable trading rules |
| `FARGATE_POWERSHELL_GUIDE.md` | This guide |

---

**Last Updated:** October 14, 2026  
**Preferred Shell:** PowerShell ✓
