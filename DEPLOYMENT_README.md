# McElveen Autonomous Trading System - Deployment Documentation

**Status:** Ready for Production Deployment on October 15, 2026  
**Target:** Live forex trading system with baseline data collection through November 5, 2026  
**Architecture:** AWS Lambda + DynamoDB + EventBridge + Schwab API

---

## 📋 Documentation Overview

This folder contains everything needed to deploy the McElveen Autonomous Trading System to your personal AWS account. Start here and follow in order:

### 1. **DEPLOYMENT_PREFLIGHT.md** (Start Here)
- ✅ Complete prerequisites checklist (Oct 9-14)
- ✅ Verify AWS CLI, Schwab credentials, IAM permissions
- ✅ Validate AWS account ID (650589744593)
- ✅ Obtain fresh Schwab refresh token
- **Action:** Work through entire checklist by Oct 14 EOD

### 2. **DEPLOYMENT_QUICK_REFERENCE.md** (Oct 15 Only)
- ⚡ Quick checklist for deployment day (Oct 15)
- ⚡ Timeline: 9 AM Phase 1A → 1 PM Phase 1B → 3 PM Tests
- ⚡ Exact commands to run with no explanation
- **Action:** Print or keep handy during deployment

### 3. **DEPLOYMENT_GUIDE.md** (Detailed Reference)
- 📖 Comprehensive step-by-step deployment guide
- 📖 Phase 1A infrastructure setup details
- 📖 Phase 1B execution layer setup details
- 📖 Post-deployment configuration instructions
- 📖 Complete troubleshooting guide
- **Action:** Refer during deployment if issues arise

### 4. **PHASE_1B_DEPLOYMENT_GUIDE.md** (Technical Deep-Dive)
- 🔧 Detailed Phase 1B architecture
- 🔧 SchwabForexClient, ForexTradeJournal, ForexExecutionOrchestrator classes
- 🔧 DynamoDB schema details
- 🔧 Lambda environment variables and permissions
- **Action:** Reference if understanding specific technical components

### 5. **PHASE_1B_SUMMARY.md** (Architecture Overview)
- 🏗️ Complete Phase 1B technical specifications
- 🏗️ Integration with Phase 1A infrastructure
- 🏗️ Timeline for Phase 1C and Phase 2
- 🏗️ Roadmap through Q2 2027 Paylinq investor pitch
- **Action:** Review for understanding full system design

### 6. **PHASE_1A_SUMMARY.md** (Phase 1A Reference)
- 🏗️ Phase 1A infrastructure specifications
- 🏗️ Hybrid router (v3.0.33) with time-based mode detection
- 🏗️ Guardrails framework (G1-G4)
- 🏗️ Macro analysis engine
- **Action:** Reference if understanding Phase 1A infrastructure

---

## 🚀 Deployment Scripts

### deploy-phase-1a.sh
**Purpose:** Automate Phase 1A infrastructure deployment  
**Duration:** ~10-15 minutes  
**Creates:**
- DynamoDB tables: `mcelveen-forex-trades`, `mcelveen-forex-metrics`
- IAM role: `Lambda-EventBridge-Role` with required permissions
- Lambda function: `mcelveen-hybrid-trading-v3.0.33` (router)
- EventBridge rules: 15-minute execution, daily 4 PM reports

**Usage:**
```bash
./deploy-phase-1a.sh mcelveen
```

### deploy-phase-1b.sh
**Purpose:** Automate Phase 1B execution layer deployment  
**Duration:** ~10-15 minutes  
**Creates:**
- Lambda function: `mcelveen-forex-execution-v3.0.34` (execution)
- Router → Execution invocation chain
- Validation tests and configuration summary

**Usage:**
```bash
./deploy-phase-1b.sh mcelveen
```

---

## 📂 Code Files

### v3.0.33_hybrid_forex_system.py
**Router Function** - Time-based market mode detection and macro analysis  
- Detects market hours (EQUITY_TRADING vs FOREX_TRADING)
- Analyzes macro conditions (Fed/ECB/BOJ rates, conviction)
- Routes to appropriate execution layer
- Invokes v3.0.34 when FOREX_TRADING mode detected

**Lambda Configuration:**
- Handler: `v3.0.33_hybrid_forex_system.lambda_handler`
- Runtime: Python 3.11
- Memory: 512 MB
- Timeout: 60 seconds

### v3.0.34_forex_execution.py
**Execution Function** - Schwab API forex trading and trade journaling  
- SchwabForexClient: Low-level Schwab API integration
- ForexTradeJournal: Trade logging to DynamoDB
- ForexExecutionOrchestrator: High-level execution coordination
- Supports 7 major forex pairs (EUR/USD, GBP/USD, USD/JPY, etc.)

**Lambda Configuration:**
- Handler: `v3.0.34_forex_execution.lambda_handler`
- Runtime: Python 3.11
- Memory: 512 MB
- Timeout: 60 seconds

---

## 🔐 AWS Infrastructure

### DynamoDB Tables
| Table | Partition Key | Sort Key | Purpose |
|-------|---|---|---|
| `mcelveen-forex-trades` | Date (String) | Timestamp (String) | Trade journal logging |
| `mcelveen-forex-metrics` | Date (String) | MetricType (String) | Daily aggregated metrics |

### Lambda Functions
| Function | Invoked By | Invokes | Purpose |
|----------|-----------|---------|---------|
| `mcelveen-hybrid-trading-v3.0.33` | EventBridge (15-min) | v3.0.34 | Router/macro analysis |
| `mcelveen-forex-execution-v3.0.34` | v3.0.33 | DynamoDB, CloudWatch | Execution & logging |

### IAM Role
| Name | Permissions |
|------|-------------|
| `Lambda-EventBridge-Role` | DynamoDB RW, CloudWatch metrics, Lambda invoke, CloudWatch logs |

### EventBridge Rules
| Rule | Schedule | Target | Purpose |
|------|----------|--------|---------|
| `mcelveen-forex-trading-15min` | Every 15 minutes | v3.0.33 | Trigger forex analysis & execution |
| `mcelveen-forex-report-4pm` | Mon-Fri 4:01 PM ET | v3.0.33 | Daily report generation |

### CloudWatch
| Namespace | Metrics |
|-----------|---------|
| `McElveen/Forex` | DailyPnL, WinRate, TradesCompleted, TradesOpen, AveragePips |

---

## 📅 Timeline

### Oct 9-14: Pre-Flight (This Week)
- [ ] Complete DEPLOYMENT_PREFLIGHT.md checklist
- [ ] Verify AWS CLI configuration
- [ ] Obtain fresh Schwab refresh token
- [ ] Confirm IAM permissions

### Oct 15: Deployment Day (Next Week)
- **9:00 AM:** Run Phase 1A deployment script
- **10:00 AM:** Validate Phase 1A completion
- **1:00 PM:** Run Phase 1B deployment script
- **2:00 PM:** Update Schwab credentials in Lambda
- **3:00 PM:** Run validation tests
- **4:00 PM:** Confirm end-of-day checklist complete

### Oct 15-16: First Trades
- EventBridge triggers v3.0.33 every 15 minutes
- During forex hours (Sun-Fri 5 PM - Fri 4 PM ET)
- First trade should execute and be logged by Oct 16 morning

### Oct 15-Nov 5: Baseline Data Collection
- Target: 50+ trades
- Collect macro-only performance metrics
- Prepare data for Phase 1C ML training

### Nov 5-20: Phase 1C (ML Integration)
- Train regime detection model (RISK_ON/NEUTRAL/RISK_OFF)
- Train conviction scoring model
- A/B test: macro vs ML recommendations

### Nov 20-Feb 28: Phase 2 (Live ML Trading)
- Deploy ML-driven execution (v3.1.x)
- 12 weeks of live trading data
- Continuous model retraining

### Q2 2027: Investor Pitch
- 12 months of data (Sept 2026 - Sept 2027)
- Baseline vs ML performance comparison
- Autonomous 24/5 trading demonstration

---

## ✅ Deployment Checklist

### Before Oct 15
- [ ] DEPLOYMENT_PREFLIGHT.md completed
- [ ] AWS CLI working with mcelveen profile
- [ ] Fresh Schwab refresh token ready
- [ ] All scripts and code files in repository

### Oct 15 Morning
- [ ] Phase 1A script runs without errors
- [ ] DynamoDB tables created
- [ ] Lambda function deployed
- [ ] EventBridge rules configured

### Oct 15 Afternoon
- [ ] Phase 1B script runs without errors
- [ ] Execution Lambda deployed
- [ ] Schwab credentials updated in both Lambdas
- [ ] Router → Execution chain tested

### Oct 15 Evening
- [ ] Router test passes (status 200)
- [ ] Execution chain test passes (status 200)
- [ ] CloudWatch logs showing activity
- [ ] All infrastructure visible in AWS console

### Oct 16+
- [ ] First trade logged to DynamoDB by morning
- [ ] CloudWatch metrics showing daily P&L
- [ ] 7+ trades collected by Oct 23
- [ ] 50+ trades collected by Nov 5

---

## 🆘 Quick Troubleshooting

### Deployment Script Fails
1. Check AWS profile: `aws sts get-caller-identity --profile mcelveen`
2. Check IAM permissions (DynamoDB, Lambda, IAM, Events)
3. See DEPLOYMENT_GUIDE.md → Troubleshooting section

### Lambda Invocation Fails
1. Check CloudWatch logs: `/aws/lambda/mcelveen-*`
2. Verify Schwab credentials are fresh (< 30 min old)
3. Check DynamoDB table permissions in IAM role

### No Trades in DynamoDB
1. Check if v3.0.34 is being invoked (CloudWatch logs)
2. Verify Schwab API credentials validity
3. Check EventBridge rule is triggering (CloudWatch metrics)

### Schwab API Errors
1. Refresh OAuth token (token expires after 30 minutes)
2. Run v3.0.32 token refresh process
3. Update both Lambda environment variables with fresh token

---

## 📞 Support Resources

- **Deployment Issues:** See DEPLOYMENT_GUIDE.md troubleshooting
- **Phase 1B Questions:** See PHASE_1B_DEPLOYMENT_GUIDE.md
- **Architecture Questions:** See PHASE_1B_SUMMARY.md
- **AWS Console:** https://console.aws.amazon.com
- **Schwab API Docs:** https://developer.schwab.com
- **CloudWatch:** https://console.aws.amazon.com/cloudwatch

---

## 🎯 Success Metrics

### Deployment Success (Oct 15)
- ✅ Both phases deploy without errors
- ✅ All AWS resources created
- ✅ Tests pass with status 200
- ✅ CloudWatch logs show activity

### Operational Success (Oct 16+)
- ✅ First trade logged by Oct 16 morning
- ✅ Daily metrics published to CloudWatch
- ✅ 50+ trades collected by Nov 5
- ✅ Win-rate and P&L statistics ready for Phase 1C

### Phase 1C Success (Nov 5+)
- ✅ ML models trained on baseline data
- ✅ A/B testing begins comparing macro vs ML
- ✅ Phase 2 ML trading launches Nov 20

---

## 📈 Expected Performance (Baseline, Oct 15-Nov 5)

Based on macro-only trading (v3.0.34 execution of v3.0.33 macro analysis):
- **Trading Days:** ~22 (excluding weekends/US holidays)
- **Trades Per Day:** ~2-3 (15-minute intervals, forex hours)
- **Expected Total Trades:** 44-66 (target: 50+)
- **Expected Win Rate:** 45-55% (neutral macro environment)
- **Expected Avg Pips:** 20-40 pips per trade
- **Expected Daily P&L:** -$100 to +$300 (highly variable based on market conditions)

*Note: These are estimates. Actual results depend on market conditions, macro analysis accuracy, and execution quality.*

---

## 🚀 Next Steps

**Immediate (By Oct 14):**
1. Read DEPLOYMENT_PREFLIGHT.md
2. Complete all prerequisite checks
3. Report readiness for Oct 15 deployment

**On Oct 15:**
1. Print or open DEPLOYMENT_QUICK_REFERENCE.md
2. Run ./deploy-phase-1a.sh mcelveen at 9 AM
3. Validate Phase 1A completion
4. Run ./deploy-phase-1b.sh mcelveen at 1 PM
5. Update Schwab credentials
6. Run validation tests
7. Celebrate successful deployment 🎉

**Oct 15-Nov 5:**
1. Monitor CloudWatch metrics daily
2. Track trades in DynamoDB
3. Collect baseline data for Phase 1C

---

## 📖 Document Map

```
DEPLOYMENT_README.md (You are here)
├── DEPLOYMENT_PREFLIGHT.md (Start here - prerequisites checklist)
├── DEPLOYMENT_QUICK_REFERENCE.md (Oct 15 only - quick commands)
├── DEPLOYMENT_GUIDE.md (Complete deployment guide)
├── PHASE_1B_DEPLOYMENT_GUIDE.md (Technical Phase 1B details)
├── PHASE_1B_SUMMARY.md (Phase 1B architecture & roadmap)
├── PHASE_1A_SUMMARY.md (Phase 1A infrastructure details)
├── deploy-phase-1a.sh (Infrastructure automation)
├── deploy-phase-1b.sh (Execution layer automation)
├── v3.0.33_hybrid_forex_system.py (Router function code)
└── v3.0.34_forex_execution.py (Execution function code)
```

---

## 🎯 Goal

**Transform the McElveen Autonomous Trading System from development to production:**
- Deploy AWS infrastructure on your personal account
- Execute baseline data collection (Oct 15 - Nov 5)
- Prepare for Phase 1C ML integration (Nov 5 - 20)
- Enable Phase 2 live ML trading (Nov 20 - Feb 28)
- Generate 12-month data for Paylinq investor pitch (Q2 2027)

---

**Status:** ✅ Ready for Production Deployment on October 15, 2026

**When ready to begin, start with DEPLOYMENT_PREFLIGHT.md**

*McElveen Autonomous Trading System - Deployment Ready* 🚀
