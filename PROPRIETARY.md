# Proprietary Notice

This repository is the **public architecture reference** for the McElveen Autonomous Trading System.

## What's Proprietary

The following components are maintained in a **private repository** and are not included here:

### 1. Core Trading Algorithm
- Profit-taking strategy implementation (2%+, 3%+, 5%+ daily targets)
- Position sizing and risk calculation logic
- Trade frequency and concentration rules
- Portfolio rebalancing decision rules
- Market regime detection and adaptation

### 2. Implementation Code
- `lambda_function.py` — Live Lambda deployment code
- `mcelveen_autonomous_trading_v*.py` — All algorithm implementations (equities day trading)
- Execution, order placement, and settlement logic

### 3. Configuration & Parameters
- Live trading parameters and thresholds
- Sector concentration limits
- Risk guardrail settings
- VIX-based adjustments and scaling factors
- Claude API integration patterns and prompts

### 4. Operational Infrastructure
- AWS Lambda configuration and deployment scripts
- Schwab OAuth token management (stored in DynamoDB)
- CloudWatch monitoring and alerting rules
- DynamoDB table schemas and indexes
- Actual credentials and API keys

---

## What's Public (This Repo)

This repository contains:
- **Architecture documentation** — System design, component roles, data flow
- **Integration patterns** — How to connect to Schwab API, DynamoDB, CloudWatch
- **Setup helpers** — OAuth token generator, DynamoDB setup scripts
- **Configuration examples** — `.env.example`, trading mode templates
- **Version history** — CHANGELOG documenting improvements over time

---

## Why This Split

**McElveen Autonomous Trading System** is:
- The **foundation** for Paylinq Autonomous Trading System (Q2 2027 launch)
- A **licensable platform** for institutional partners and RIAs
- **Proprietary intellectual property** and competitive advantage
- Core business moat for Paylinq OS ecosystem

**This public repository** serves as:
- **Architecture reference** for understanding system design patterns
- **Educational material** for broker integration and multi-agent orchestration
- **Transparency** about our approach (without revealing implementation secrets)
- **Credibility signal** that the system is openly architected, not a black box

---

## Access & Licensing

### For Personal/Research Use
- Study the public architecture
- Implement your own trading system using these patterns
- Reference the integration approach

### For Institutional/Commercial Use
- Private repository access (NDA required)
- Licensing arrangement discussion
- Integration with Paylinq Autonomous Trading platform

**Contact:** Kevin McElveen | kmcelveen@getpaylinq.com

---

## Security & Compliance

All proprietary code and configurations are:
- Stored in a **private GitHub repository**
- Protected by **AWS IAM policies** (Lambda execution role)
- Secured by **encryption at rest** (DynamoDB, AWS Secrets Manager)
- Audited via **CloudWatch logs** and **DynamoDB audit trails**
- Subject to **RIA compliance requirements** (as of Paylinq launch)

This arrangement ensures that while our architecture is transparent, our competitive implementation remains protected.
