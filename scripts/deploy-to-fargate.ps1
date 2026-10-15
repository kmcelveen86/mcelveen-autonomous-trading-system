# McElveen Fargate Deployment Script - PowerShell Version
# Builds Docker images and deploys to ECS on Fargate

param(
    [string]$AwsRegion = "us-east-1",
    [string]$Environment = "production",
    [switch]$SkipCloudFormation
)

$ErrorActionPreference = "Stop"

# Configuration
$AwsAccountId = if ($env:AWS_ACCOUNT_ID) { $env:AWS_ACCOUNT_ID } else {
    (aws sts get-caller-identity --query Account --output text)
}
$EcrRegistry = "$AwsAccountId.dkr.ecr.$AwsRegion.amazonaws.com"

# Colors
$InfoColor = 'Green'
$WarnColor = 'Yellow'
$ErrorColor = 'Red'

# Functions
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor $InfoColor
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor $WarnColor
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor $ErrorColor
}

function Test-Prerequisites {
    Write-Info "Checking prerequisites..."

    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        Write-Error-Custom "AWS CLI not found. Please install it first."
        exit 1
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error-Custom "Docker not found. Please install it first."
        exit 1
    }

    Write-Info "Using AWS Account ID: $AwsAccountId"
    Write-Info "Using Region: $AwsRegion"
}

function New-EcrRepositories {
    Write-Info "Creating ECR repositories..."

    $repos = @("trading-system", "daily-report", "token-refresh")

    foreach ($repo in $repos) {
        $repoName = "mcelveen-$repo"

        try {
            $existing = aws ecr describe-repositories `
                --repository-names $repoName `
                --region $AwsRegion 2>$null

            Write-Info "Repository $repo already exists"
        }
        catch {
            Write-Info "Creating repository $repo..."
            aws ecr create-repository `
                --repository-name $repoName `
                --region $AwsRegion `
                --image-scanning-configuration scanOnPush=true `
                --encryption-configuration encryptionType=AES | Out-Null
        }
    }
}

function Invoke-EcrLogin {
    Write-Info "Logging in to ECR..."

    $ecrToken = aws ecr get-login-password --region $AwsRegion
    $ecrToken | docker login --username AWS --password-stdin $EcrRegistry
}

function Build-And-Push-Image {
    param(
        [string]$Service,
        [string]$Dockerfile,
        [string]$Context
    )

    Write-Info "Building image for $Service..."

    $imageUri = "$EcrRegistry/mcelveen-${Service}:latest"
    $dateTag = Get-Date -Format "yyyyMMdd-HHmmss"
    $imageUriDated = "$EcrRegistry/mcelveen-${Service}:$dateTag"

    docker build -f $Dockerfile -t $imageUri -t $imageUriDated $Context

    if ($LASTEXITCODE -ne 0) {
        Write-Error-Custom "Failed to build image for $Service"
        exit 1
    }

    Write-Info "Pushing $Service image to ECR..."
    docker push $imageUri
    docker push $imageUriDated

    Write-Info "✓ $Service image pushed: $imageUri"
}

function Deploy-Images {
    Write-Info "Building and pushing Docker images..."

    Invoke-EcrLogin

    Build-And-Push-Image "trading-system" "docker/Dockerfile.trading-system" "."
    Build-And-Push-Image "daily-report" "docker/Dockerfile.daily-report" "."
    Build-And-Push-Image "token-refresh" "docker/Dockerfile.token-refresh" "."
}

function Deploy-CloudFormation {
    Write-Info "Deploying CloudFormation stack..."

    $VpcId = $env:VPC_ID
    $SubnetIds = $env:SUBNET_IDS

    if (-not $VpcId -or -not $SubnetIds) {
        Write-Error-Custom "VPC_ID and SUBNET_IDS environment variables must be set"
        Write-Warn "Set them: `$env:VPC_ID='vpc-xxx'; `$env:SUBNET_IDS='subnet-xxx,subnet-yyy'"
        return $false
    }

    $stackName = "mcelveen-ecs-$Environment"

    Write-Info "Creating/Updating CloudFormation stack: $stackName"

    aws cloudformation deploy `
        --template-file ecs/cloudformation-ecs-fargate.yaml `
        --stack-name $stackName `
        --parameter-overrides `
            Environment="$Environment" `
            VpcId="$VpcId" `
            "PrivateSubnetIds=$SubnetIds" `
            TradingSystemImage="$EcrRegistry/mcelveen-trading-system:latest" `
            DailyReportImage="$EcrRegistry/mcelveen-daily-report:latest" `
            TokenRefreshImage="$EcrRegistry/mcelveen-token-refresh:latest" `
        --capabilities CAPABILITY_NAMED_IAM `
        --region $AwsRegion `
        --no-fail-on-empty-changeset

    Write-Info "✓ CloudFormation stack deployed"
    return $true
}

function Verify-Deployment {
    Write-Info "Verifying deployment..."

    $clusterName = "mcelveen-$Environment"

    try {
        aws ecs describe-clusters --clusters $clusterName --region $AwsRegion | Out-Null
        Write-Info "✓ ECS Cluster exists: $clusterName"

        $services = aws ecs list-services `
            --cluster $clusterName `
            --region $AwsRegion `
            --query 'serviceArns[]' `
            --output text

        if ($services) {
            foreach ($service in $services -split '\s+') {
                if ($service) {
                    $serviceName = $service -split '/' | Select-Object -Last 1
                    Write-Info "  Service: $serviceName"
                }
            }
        }
    }
    catch {
        Write-Error-Custom "Cluster not found: $clusterName"
        return $false
    }

    return $true
}



function Print-Summary {
    $separator = "=" * 50
    Write-Host ""
    Write-Host $separator -ForegroundColor $InfoColor
    Write-Host "Deployment Summary" -ForegroundColor $InfoColor
    Write-Host $separator -ForegroundColor $InfoColor
    Write-Host "Environment: $Environment" -ForegroundColor $InfoColor
    Write-Host "Region: $AwsRegion" -ForegroundColor $InfoColor
    Write-Host "Account ID: $AwsAccountId" -ForegroundColor $InfoColor
    Write-Host "ECR Registry: $EcrRegistry" -ForegroundColor $InfoColor
    Write-Host ""
    Write-Host "Docker Images:" -ForegroundColor $InfoColor
    Write-Host "  - Trading System: $EcrRegistry/mcelveen-trading-system:latest" -ForegroundColor $InfoColor
    Write-Host "  - Daily Report: $EcrRegistry/mcelveen-daily-report:latest" -ForegroundColor $InfoColor
    Write-Host "  - Token Refresh: $EcrRegistry/mcelveen-token-refresh:latest" -ForegroundColor $InfoColor
    Write-Host ""
    Write-Host "ECS Cluster: mcelveen-$Environment" -ForegroundColor $InfoColor
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor $InfoColor
    Write-Host "1. Verify tasks: aws ecs list-tasks --cluster mcelveen-$Environment --region $AwsRegion" -ForegroundColor $InfoColor
    Write-Host "2. View logs: aws logs tail /ecs/mcelveen-trading-system --follow --region $AwsRegion" -ForegroundColor $InfoColor
    Write-Host $separator -ForegroundColor $InfoColor
    Write-Host ""
}

function Main {
    Write-Info "Starting McElveen Fargate Deployment..."

    Test-Prerequisites
    New-EcrRepositories
    Deploy-Images

    if (-not $SkipCloudFormation) {
        $cfSuccess = Deploy-CloudFormation
        if ($cfSuccess) {
            Verify-Deployment
        }
    }
    else {
        Write-Warn "Skipping CloudFormation deployment (SkipCloudFormation flag set)"
        Write-Info "To deploy CloudFormation, run: .\deploy-to-fargate.ps1"
    }

    Print-Summary
    Write-Info "✓ Deployment completed successfully!"
}

Main
