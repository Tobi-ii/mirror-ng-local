# Mirror.ng - Your Financial Mirror

Track all your Nigerian bank accounts in one place. No APIs needed - just your email alerts.

> See [README-DATA.md](./README-DATA.md) for the data engineering, ML, and AI agent deep-dive.

**Live instance → [mirror-ng.vercel.app](https://mirror-ng.vercel.app/)** — no setup required, just visit and connect your email.

## Features

- **Privacy First** - Only reads bank alert emails, stores nothing else
- **Multi-Bank Support** - Sterling, Wema/ALAT, Kuda, Opay, GTBank, Access, Stanbic, Standard Chartered, Moniepoint, PalmPay, FirstBank
- **Real-time Mirror** - Automatic balance updates from email alerts
- **Open Source** - Fully auditable, self-hostable
- **Manual Adjustments** - Fix balances anytime
- **ML-Powered Suggestions** - Smart transaction categorization and alias recommendations
- **AI Agent Chat** - Ask questions about your finances using LLMs
- **Anchor Accounts** - Pin one account to track your true financial position

---

## Prerequisites

- **Python 3.9+**
- **Node.js 18+**
- **A Yahoo or Gmail account** with app password enabled (for bank email alerts)
- **(Optional) Docker** for containerized deployment

---

## API Keys You'll Need

Mirror.ng uses several external services. You only need to configure the ones you want to use:

| Key | Required For | How to Get |
|-----|-------------|------------|
| `OPENROUTER_API_KEY` | AI Agent Chat | Sign up at [openrouter.ai](https://openrouter.ai) and create an API key |
| `NVIDIA_API_KEY` | AI Agent Chat (fallback) | Sign up at [build.nvidia.com](https://build.nvidia.com) and get an API key |
| `GROQ_API_KEY` | ML Insights | Sign up at [console.groq.com](https://console.groq.com) |
| `DEEPSEEK_API_KEY` | ML Insights | Sign up at [platform.deepseek.com](https://platform.deepseek.com) |
| `SECRET_KEY` | JWT signing (security) | Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SESSION_SECRET_KEY` | OAuth sessions (security) | Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `EMAIL_ENCRYPTION_KEY` | Password encryption (security) | Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ADMIN_KEY` | Admin API endpoints (optional) | Any secure random string |
| `GOOGLE_CLIENT_ID/SECRET` | Gmail OAuth login | Set up a Web Application OAuth Client ID on [Google Cloud Console](https://console.cloud.google.com) |

---

## Quick Start

### 1. Clone & Setup Environment

```bash
git clone https://github.com/YOUR_USERNAME/mirror-ng-local.git
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

**Edit `backend/.env`** and fill in your credentials. At minimum, you need:
- `SECRET_KEY`, `SESSION_SECRET_KEY`, `EMAIL_ENCRYPTION_KEY` - generate these
- `YAHOO_EMAIL` / `YAHOO_APP_PASSWORD` - your Yahoo email and app password
- `OPENROUTER_API_KEY` - if you want AI features

Start the backend:
```bash
uvicorn app.main:app --reload
```

The backend runs on `http://localhost:8000`.

### 3. Frontend Setup

Open a new terminal:
```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173`.

### 4. Open in Browser

Visit **http://localhost:5173** and log in with your email credentials.

---

## Docker Setup (Alternative)

```bash
# Copy the root .env template
cp .env.example .env

# Edit .env with all your credentials
# (This is the Docker-compatible env — includes all required vars)

# Start everything
docker compose up -d
```

Open http://localhost:80

---

## Configuration Reference

### `backend/.env` (for manual setup)

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | JWT signing secret (required, generate 32+ char hex) |
| `SESSION_SECRET_KEY` | Session middleware secret (required, generate 32+ char hex) |
| `EMAIL_ENCRYPTION_KEY` | Fernet key for password encryption (required) |
| `ADMIN_KEY` | Admin API key (optional) |
| `OPENROUTER_API_KEY` | OpenRouter API key for AI agent |
| `NVIDIA_API_KEY` | NVIDIA NIM API key for AI agent (fallback) |
| `GROQ_API_KEY` | Groq API key for ML insights |
| `DEEPSEEK_API_KEY` | DeepSeek API key for ML insights |
| `EMAIL_PROVIDER` | `yahoo`, `gmail`, or `gmail_oauth` |
| `YAHOO_EMAIL` | Your Yahoo email address |
| `YAHOO_APP_PASSWORD` | Yahoo app password (requires 2FA enabled) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `FRONTEND_URL` | Frontend URL for OAuth redirects |

### `.env` (root, for Docker setup)

Same variables as above plus `DATABASE_URL`.

---

## How It Works

1. You log in with your **Yahoo or Gmail** credentials
2. The app fetches **only bank alert emails** (filtered by sender address)
3. Bank-specific parsers extract transaction details (amount, type, balance, narration)
4. ML classifier categorizes each transaction
5. Balances update automatically as new alerts arrive
6. AI Agent answers questions about your spending

---

## Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS
- **Backend**: FastAPI, SQLAlchemy, SQLite
- **ML/AI**: scikit-learn, OpenRouter, NVIDIA NIM, Groq, DeepSeek
- **Email**: IMAP (Yahoo/Gmail), Gmail API (OAuth)

---

## License

MIT
