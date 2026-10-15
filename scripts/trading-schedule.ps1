# McElveen Trading System - EventBridge Schedule Management (PowerShell)
# Enable/disable trading rules for market hours

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("enable", "disable")]
    [string]$Action,

    [string]$AwsRegion = "us-east-1",
    [string]$Environment = "production"
)

$ErrorActionPreference = "Stop"

$ruleHours = @(9, 10, 11, 12, 13, 14, 15, 16)
$clusterName = "mcelveen-$Environment"

Write-Host "Trading System Schedule Manager - PowerShell" -ForegroundColor Green
Write-Host "Action: $Action" -ForegroundColor Green
Write-Host "Region: $AwsRegion" -ForegroundColor Green
Write-Host ""

switch ($Action) {
    "enable" {
        Write-Host "Enabling trading system rules..." -ForegroundColor Green
        foreach ($hour in $ruleHours) {
            $ruleName = "mcelveen-trading-system-$hour"
            Write-Host "  Enabling: $ruleName" -ForegroundColor Cyan
            aws events put-rule --name $ruleName --state ENABLED --region $AwsRegion
        }
        Write-Host "✓ Trading system enabled" -ForegroundColor Green
    }
    "disable" {
        Write-Host "Disabling trading system rules..." -ForegroundColor Yellow
        foreach ($hour in $ruleHours) {
            $ruleName = "mcelveen-trading-system-$hour"
            Write-Host "  Disabling: $ruleName" -ForegroundColor Cyan
            aws events put-rule --name $ruleName --state DISABLED --region $AwsRegion
        }
        Write-Host "✓ Trading system disabled" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Verify status:" -ForegroundColor Green
Write-Host "  aws events describe-rule --name mcelveen-trading-system-9 --region $AwsRegion" -ForegroundColor Cyan
