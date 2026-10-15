param(
    [string]$AwsRegion = "us-east-1",
    [string]$Environment = "production",
    [switch]$SkipCloudFormation
)

$ErrorActionPreference = "Stop"

Write-Host "[INFO] Starting McElveen Fargate Deployment..." -ForegroundColor Green

$AwsAccountId = if ($env:AWS_ACCOUNT_ID) { $env:AWS_ACCOUNT_ID } else {
    (aws sts get-caller-identity --query Account --output text)
}
$EcrRegistry = "$AwsAccountId.dkr.ecr.$AwsRegion.amazonaws.com"

Write-Host "[INFO] Using AWS Account ID: $AwsAccountId" -ForegroundColor Green
Write-Host "[INFO] Using Region: $AwsRegion" -ForegroundColor Green

Write-Host "[INFO] Checking prerequisites..." -ForegroundColor Green

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] AWS CLI not found. Please install it first." -ForegroundColor Red
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Docker not found. Please install it first." -ForegroundColor Red
    exit 1
}

function Build-Image {
    param([string]$Service, [string]$Dockerfile)
    Write-Host "[INFO] Building image for $Service..." -ForegroundColor Green
    $imageUri = "$EcrRegistry/mcelveen-${Service}:latest"
    $dateTag = Get-Date -Format "yyyyMMdd-HHmmss"
    $imageUriDated = "$EcrRegistry/mcelveen-${Service}:$dateTag"
    docker build -f $Dockerfile -t $imageUri -t $imageUriDated .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to build image for $Service" -ForegroundColor Red
        exit 1
    }
    Write-Host "[INFO] Pushing $Service image to ECR..." -ForegroundColor Green
    docker push $imageUri
    docker push $imageUriDated
    Write-Host "[INFO] OK $Service image pushed: $imageUri" -ForegroundColor Green
}

Write-Host "[INFO] Creating ECR repositories..." -ForegroundColor Green

$repos = @("trading-system", "daily-report", "token-refresh")
foreach ($repo in $repos) {
    $repoName = "mcelveen-$repo"
    $repoExists = aws ecr describe-repositories --repository-names $repoName --region $AwsRegion -ErrorAction SilentlyContinue 2>$null
    if ($repoExists) {
        Write-Host "[INFO] Repository $repo already exists" -ForegroundColor Green
    } else {
        Write-Host "[INFO] Creating repository $repo..." -ForegroundColor Green
        aws ecr create-repository --repository-name $repoName --region $AwsRegion --image-scanning-configuration scanOnPush=true --encryption-configuration encryptionType=AES | Out-Null
    }
}

Write-Host "[INFO] Logging in to ECR..." -ForegroundColor Green
$ecrToken = aws ecr get-login-password --region $AwsRegion
$ecrToken | docker login --username AWS --password-stdin $EcrRegistry

Write-Host "[INFO] Building and pushing Docker images..." -ForegroundColor Green

Build-Image "trading-system" "docker/Dockerfile.trading-system"
Build-Image "daily-report" "docker/Dockerfile.daily-report"
Build-Image "token-refresh" "docker/Dockerfile.token-refresh"

if (-not $SkipCloudFormation) {
    Write-Host "[INFO] Deploying CloudFormation stack..." -ForegroundColor Green
    $VpcId = $env:VPC_ID
    $SubnetIds = $env:SUBNET_IDS
    if (-not $VpcId -or -not $SubnetIds) {
        Write-Host "[ERROR] VPC_ID and SUBNET_IDS environment variables must be set" -ForegroundColor Red
        exit 1
    }
    $stackName = "mcelveen-ecs-$Environment"
    aws cloudformation deploy --template-file ecs/cloudformation-ecs-fargate.yaml --stack-name $stackName --parameter-overrides Environment="$Environment" VpcId="$VpcId" "PrivateSubnetIds=$SubnetIds" TradingSystemImage="$EcrRegistry/mcelveen-trading-system:latest" DailyReportImage="$EcrRegistry/mcelveen-daily-report:latest" TokenRefreshImage="$EcrRegistry/mcelveen-token-refresh:latest" --capabilities CAPABILITY_NAMED_IAM --region $AwsRegion --no-fail-on-empty-changeset
    Write-Host "[INFO] OK CloudFormation stack deployed" -ForegroundColor Green
} else {
    Write-Host "[WARN] Skipping CloudFormation deployment (SkipCloudFormation flag set)" -ForegroundColor Yellow
}

Write-Host "[INFO] OK Deployment completed successfully!" -ForegroundColor Green
