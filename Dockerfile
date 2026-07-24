# ==============================================================
# Mirror.ng — Single image for Fly.io deployment
# Builds frontend + backend together
# ==============================================================

# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# --- Stage 2: Build backend + serve everything ---
FROM python:3.11-slim

# Hugging Face Spaces runs containers as UID 1000
RUN useradd -m -u 1000 user

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy backend code
COPY backend/ .

# Copy built frontend into backend's frontend/dist directory
COPY --from=frontend-builder /app/dist /app/frontend/dist

# Set environment defaults (override via Space secrets or --env)
ENV PYTHONUNBUFFERED=1
ENV CORS_ORIGINS=http://localhost:7860,http://localhost:3000
ENV FRONTEND_URL=http://localhost:7860

# Switch to non-root user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

# Hugging Face Spaces expects port 7860 by default
EXPOSE 7860

CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "120"]
