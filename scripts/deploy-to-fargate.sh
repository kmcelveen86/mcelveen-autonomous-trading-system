#!/bin/bash

set -e

# McElveen Fargate Deployment Script
# Builds Docker images and deploys to ECS on Fargate

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID}"
ENVIRONMENT="${ENVIRONMENT:-production}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Please install it first."
        exit 1
    fi

    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install it first."
        exit 1
    fi

    if [ -z "$AWS_ACCOUNT_ID" ]; then
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        log_info "Using AWS Account ID: $AWS_ACCOUNT_ID"
    fi

    if [ -z "$VPC_ID" ] || [ -z "$SUBNET_IDS" ]; then
        log_warn "VPC_ID or SUBNET_IDS not set. These will be needed for CloudFormation deployment."
    fi
}

create_ecr_repositories() {
    log_info "Creating ECR repositories..."

    for repo in trading-system daily-report token-refresh; do
        repo_uri="${ECR_REGISTRY}/mcelveen-${repo}"

        if aws ecr describe-repositories --repository-names "mcelveen-${repo}" --region "$AWS_REGION" &>/dev/null; then
            log_info "Repository $repo already exists"
        else
            log_info "Creating repository $repo..."
            aws ecr create-repository \
                --repository-name "mcelveen-${repo}" \
                --region "$AWS_REGION" \
                --image-scanning-configuration scanOnPush=true \
                --encryption-configuration encryptionType=AES
        fi
    done
}

login_to_ecr() {
    log_info "Logging in to ECR..."

    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$ECR_REGISTRY"
}

build_and_push_image() {
    local service=$1
    local dockerfile=$2
    local context=$3

    log_info "Building image for $service..."

    local image_uri="${ECR_REGISTRY}/mcelveen-${service}:latest"
    local image_uri_dated="${ECR_REGISTRY}/mcelveen-${service}:$(date +%Y%m%d-%H%M%S)"

    # Build image
    docker build \
        -f "$dockerfile" \
        -t "$image_uri" \
        -t "$image_uri_dated" \
        "$context"

    log_info "Pushing $service image to ECR..."
    docker push "$image_uri"
    docker push "$image_uri_dated"

    log_info "✓ $service image pushed: $image_uri"
}

deploy_images() {
    log_info "Building and pushing Docker images..."

    login_to_ecr

    # Build trading system
    build_and_push_image "trading-system" \
        "docker/Dockerfile.trading-system" \
        "."

    # Build daily report
    build_and_push_image "daily-report" \
        "docker/Dockerfile.daily-report" \
        "."

    # Build token refresh
    build_and_push_image "token-refresh" \
        "docker/Dockerfile.token-refresh" \
        "."
}

deploy_cloudformation() {
    log_info "Deploying CloudFormation stack..."

    if [ -z "$VPC_ID" ] || [ -z "$SUBNET_IDS" ]; then
        log_error "VPC_ID and SUBNET_IDS must be set for CloudFormation deployment"
        log_warn "Set them: export VPC_ID=vpc-xxx && export SUBNET_IDS=subnet-xxx,subnet-yyy"
        return 1
    fi

    local stack_name="mcelveen-ecs-${ENVIRONMENT}"

    # Convert subnet IDs from comma-separated to JSON array
    local subnet_json=""
    IFS=',' read -ra SUBNET_ARRAY <<< "$SUBNET_IDS"
    for subnet in "${SUBNET_ARRAY[@]}"; do
        subnet_json="${subnet_json}\"${subnet//[[:space:]]/}\","
    done
    subnet_json="[${subnet_json%,}]"

    log_info "Creating/Updating CloudFormation stack: $stack_name"

    aws cloudformation deploy \
        --template-file ecs/cloudformation-ecs-fargate.yaml \
        --stack-name "$stack_name" \
        --parameter-overrides \
            Environment="$ENVIRONMENT" \
            VpcId="$VPC_ID" \
            "PrivateSubnetIds=$SUBNET_IDS" \
            TradingSystemImage="${ECR_REGISTRY}/mcelveen-trading-system:latest" \
            DailyReportImage="${ECR_REGISTRY}/mcelveen-daily-report:latest" \
            TokenRefreshImage="${ECR_REGISTRY}/mcelveen-token-refresh:latest" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION" \
        --no-fail-on-empty-changeset

    log_info "✓ CloudFormation stack deployed"
}

verify_deployment() {
    log_info "Verifying deployment..."

    local cluster_name="mcelveen-${ENVIRONMENT}"

    # Check if cluster exists
    if aws ecs describe-clusters --clusters "$cluster_name" --region "$AWS_REGION" &>/dev/null; then
        log_info "✓ ECS Cluster exists: $cluster_name"

        # List services
        aws ecs list-services --cluster "$cluster_name" --region "$AWS_REGION" \
            --query 'serviceArns[]' --output text | tr '\t' '\n' | while read -r service; do
            if [ -n "$service" ]; then
                log_info "  Service: $(basename $service)"
            fi
        done
    else
        log_error "Cluster not found: $cluster_name"
        return 1
    fi
}

print_summary() {
    log_info "=========================================="
    log_info "Deployment Summary"
    log_info "=========================================="
    log_info "Environment: $ENVIRONMENT"
    log_info "Region: $AWS_REGION"
    log_info "Account ID: $AWS_ACCOUNT_ID"
    log_info "ECR Registry: $ECR_REGISTRY"
    log_info ""
    log_info "Docker Images:"
    log_info "  - Trading System: ${ECR_REGISTRY}/mcelveen-trading-system:latest"
    log_info "  - Daily Report: ${ECR_REGISTRY}/mcelveen-daily-report:latest"
    log_info "  - Token Refresh: ${ECR_REGISTRY}/mcelveen-token-refresh:latest"
    log_info ""
    log_info "ECS Cluster: mcelveen-${ENVIRONMENT}"
    log_info ""
    log_info "Next Steps:"
    log_info "1. Verify tasks are running: aws ecs list-tasks --cluster mcelveen-${ENVIRONMENT}"
    log_info "2. View logs: aws logs tail /ecs/mcelveen-trading-system --follow"
    log_info "=========================================="
}

main() {
    log_info "Starting McElveen Fargate Deployment..."

    check_prerequisites
    create_ecr_repositories
    deploy_images

    if [ "${SKIP_CLOUDFORMATION:-false}" != "true" ]; then
        deploy_cloudformation
        verify_deployment
    else
        log_warn "Skipping CloudFormation deployment (SKIP_CLOUDFORMATION=true)"
        log_info "To deploy CloudFormation, run: SKIP_CLOUDFORMATION=false $0"
    fi

    print_summary
    log_info "✓ Deployment completed successfully!"
}

# Run main function
main "$@"
