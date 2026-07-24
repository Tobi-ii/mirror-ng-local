# Mirror.ng — Data Engineering & ML Case Study

A personal project that ingests Nigerian bank email alerts, normalizes them into structured data, runs ML analytics, and serves everything through a dashboard with a natural language AI agent.

**Live app**: [mirror-ng.fly.dev](https://mirror-ng.fly.dev)

---

## Data Pipeline

```
Email (IMAP/Gmail API)
  → Bank-specific parsers (regex extraction)
  → SQLite warehouse (transactions, balances, aliases)
  → FastAPI REST layer
  → React dashboard + ML engine + AI agent
```

Six bank parsers handle the variety of Nigerian email alert formats — different date formats, amount positions, balance placements, and narration styles. Each normalizes unstructured email text into structured transaction records with consistent fields: `bank, tx_type, amount, balance, narration, account_last4, timestamp, category`.

## ML & AI

### 7-Day Spend Forecast
Linear regression on daily transaction totals. Extrapolates the trend line forward 7 days. Model retrains automatically as more transactions sync. Code: `backend/app/intent_agent.py`

### Anomaly Detection
Z-score based — flags transactions >2σ from their category mean. In ~50 transactions over 30 days, surfaced 4 anomalous transactions worth ~₦45,000. Code: `backend/app/intent_agent.py`

### AI Agent ("Ask Mirror")
Natural language → SQL via Groq LLM and DeepSeek API. Handles queries like "How much did I spend on transfers?" and "What number do I buy airtime for most?" by converting intent to parameterized SQL queries. Code: `backend/app/agent.py`

### Transaction Intelligence
- Category-based spend breakdown with volume analysis
- ML alias suggestions (groups similar narrations)
- Executive View: aggregate stats, daily trends, credit/debit ratios

## Project Structure

```
backend/app/
├── main.py                 # FastAPI (20+ REST endpoints)
├── agent.py                # AI agent — NL → query execution
├── intent_agent.py         # Forecasting + anomaly detection
├── balance_manager.py      # Running balance computation
├── parsers/                # 6 bank-specific regex parsers
├── email_fetcher.py        # IMAP ingestion
└── database.py             # SQLite schema & initialization
frontend/src/
├── pages/                  # Dashboard, Settings, Forecast
├── services/               # API client, IndexedDB local storage
└── components/             # Charts, ML groups, transaction rows
```

## Why This Matters for Data Roles

This project demonstrates the full data lifecycle:

1. **Ingestion** — Unstructured email text → structured records via regex
2. **Storage** — SQLite schema design with proper indexes
3. **Transformation** — Balance computation, alias mapping, narration cleaning
4. **Analysis** — Aggregation queries, daily/weekly/monthly trends
5. **ML** — Linear regression forecasting, z-score anomaly detection
6. **AI** — Natural language interface to data
7. **Visualization** — React dashboard with category breakdowns, spend trends, volume analysis
8. **Production** — Deployed on Fly.io with Docker, CI/CD via GitHub

**Tools used**: Python, pandas, scikit-learn, FastAPI, SQLite, React, Groq LLM, DeepSeek API, Docker, Fly.io, Git.

## Contact

[LinkedIn](https://www.linkedin.com/in/tobiloba-ogunwoye/)
