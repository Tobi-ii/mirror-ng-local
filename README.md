# Mirror.ng | AI-Powered Financial Data & Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-blue.svg)](https://reactjs.org/)
[![scikit-learn](https://img.shields.io/badge/ML-scikit--learn-orange.svg)](https://scikit-learn.org/)
[![Live Demo](https://img.shields.io/badge/Live_Demo-Vercel-000000.svg)](https://mirror-ng.vercel.app/)

Mirror.ng is a production-grade, full-stack financial data platform that automates the ingestion of unstructured bank alerts, applies machine learning for financial insights, and provides an LLM-powered AI agent for natural-language data querying. 

🔗 **Live Production App:** [https://mirror-ng.vercel.app/](https://mirror-ng.vercel.app/)

---

## 🚀 Key Features

- **Automated ETL Pipeline**: Custom Python parsers convert unstructured bank alert emails (supporting 11+ Nigerian banks) into normalized, structured transaction records in real-time.
- **AI Agent Chat**: An LLM-powered assistant that reasons over user intents, executes tool-use via custom API endpoints, and retrieves structured financial data.
- **Machine Learning Insights**: Integrated `scikit-learn` models for automated transaction categorization, spend forecasting, and anomaly detection.
- **Data Quality & Validation**: Rigorous schema validation and data cleaning rules ensure transaction integrity and ledger accuracy before storage.
- **Privacy-First Architecture**: Designed to read only bank alert emails, storing no extraneous personal data. Fully auditable and self-hostable.

---

## 🧠 AI Agent & Orchestration Architecture

The AI Agent Chat is designed around the core principles of agentic AI workflows, bridging the gap between natural language and structured databases:
1. **Intent Recognition**: The LLM analyzes natural language queries to determine the user's financial goal.
2. **Tool-Use Interface**: The agent executes structured API calls to backend FastAPI endpoints to retrieve transaction history, run forecasts, or query account balances.
3. **Multi-Step Reasoning**: Capable of chaining requests (e.g., "Show me my spending trends this month and flag any anomalies").
4. **Resilient Fallback**: Orchestrates across multiple LLM providers (OpenRouter, NVIDIA NIM, Groq, DeepSeek) to ensure high availability and reliable data retrieval.

---

## 🔄 Data Pipeline & Quality Assurance

Built with robust data engineering practices to handle messy, real-world financial data:
- **Ingestion**: IMAP and Gmail API (OAuth) listeners continuously poll for new bank alerts.
- **Transformation**: Custom parsers extract entities (date, amount, merchant, balance, narration) from highly variable, unstructured email formats across 11 different banking institutions.
- **Data Cleaning & Validation**: Validation layers check for schema compliance, duplicate detection, and logical consistency (e.g., balance reconciliation) before committing to the database.
- **Conceptual Modeling**: Designed with a medallion-style architecture in mind: *Bronze* (raw email payloads) → *Silver* (parsed, validated transactions) → *Gold* (aggregated insights and ML features).

---

## 📊 Data Science & Machine Learning

The platform goes beyond simple data storage, applying statistical and ML techniques to generate predictive insights:
- **Spend Forecasting**: Linear regression and exponential smoothing models predict future cash flow based on historical transaction patterns.
- **Anomaly Detection**: Statistical methods flag unusual transactions or balance discrepancies for user review, ensuring data integrity.
- **Transaction Categorization**: `scikit-learn` classifiers automatically tag transactions based on merchant names and historical user behavior.
- **Model Serving**: All ML capabilities are exposed via clean, typed FastAPI endpoints with strict Pydantic JSON schemas, making them easily consumable by the AI agent and frontend.

---

## 🛠️ Tech Stack

| Domain | Technologies |
| :--- | :--- |
| **Backend & API** | Python, FastAPI, SQLAlchemy, SQLite, Pydantic, Uvicorn |
| **Frontend** | React 18, Vite, Tailwind CSS |
| **Data Science & ML** | scikit-learn, Pandas, NumPy, Linear Regression, Exponential Smoothing |
| **AI & LLMs** | OpenRouter, NVIDIA NIM, Groq, DeepSeek, Prompt Engineering |
| **Data & ETL** | IMAP, Gmail API (OAuth), Custom Regex/NLP Parsers |
| **DevOps & Infra** | Docker, Docker Compose, Git, GitHub, Vercel (Production) |

---

## ⚡ Quick Start (Local Development)

### 1. Clone & Setup Environment
```bash
git clone https://github.com/Tobi-ii/mirror-ng-local.git
cd mirror-ng-local
```

### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create your .env file from the template
cp .env.example .env
```
*Edit `backend/.env` and fill in your credentials. At minimum, you need `SECRET_KEY`, `SESSION_SECRET_KEY`, `EMAIL_ENCRYPTION_KEY`, and your email credentials.*

Start the backend:
```bash
uvicorn app.main:app --reload
```
*The backend runs on `http://localhost:8000`*

### 3. Frontend Setup
Open a new terminal:
```bash
cd frontend
npm install
npm run dev
```
*The frontend runs on `http://localhost:5173`*

### 4. Docker Setup (Alternative)
```bash
# Copy the root .env template
cp .env.example .env

# Edit .env with all your credentials
# Start everything
docker compose up -d
```
*Access the local application at `http://localhost:80`*

---

## 📦 Production Deployment

The live, production version of this application is deployed at **[https://mirror-ng.vercel.app/](https://mirror-ng.vercel.app/)**. 

The production environment includes:
- Cloud database integration (Supabase/PostgreSQL)
- Advanced CI/CD pipelines via GitHub Actions
- Production-grade monitoring, logging, and secret management

*Note: This local repository showcases the core AI orchestration, data pipeline logic, and ML model serving architecture. Production-specific configurations and sensitive infrastructure code are maintained in a private repository to ensure security and compliance.*

---


---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
```

