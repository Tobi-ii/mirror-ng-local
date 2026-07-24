#!/usr/bin/env bash
set -euo pipefail

# ==============================================================
# Mirror.ng — Oracle Cloud Always Free VM Bootstrap
# Run this ONCE on a fresh Ubuntu 22.04+ VM.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Tobi-ii/mirror-ng/main/scripts/bootstrap-oracle.sh | bash
#
# After it finishes:
#   1. cd ~/mirror-ng && cp .env.example .env && nano .env
#   2. docker compose up -d
#   3. Update Caddyfile with your domain, then: docker compose restart caddy
# ==============================================================

REPO_URL="https://github.com/Tobi-ii/mirror-ng.git"
APP_DIR="$HOME/mirror-ng"

echo "=== 1. Installing Docker ==="
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash
    sudo usermod -aG docker "$USER"
fi

if ! command -v docker compose &>/dev/null; then
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

echo "=== 2. Cloning repo ==="
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR" && cd "$APP_DIR"
fi

echo "=== 3. Creating .env from template ==="
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo ">>> IMPORTANT: Edit .env with your API keys:"
    echo "    nano $APP_DIR/.env"
    echo ""
    echo "    Then run: cd $APP_DIR && docker compose up -d"
    echo ""
    echo "    For HTTPS with your domain:"
    echo "    1. Edit Caddyfile with your domain"
    echo "    2. docker compose restart caddy"
    echo ""
else
    echo "    .env already exists — skipping"
fi

echo "=== 4. Building and starting ==="
docker compose build
docker compose up -d

echo ""
echo "=== Done! ==="
echo "    App running at http://$(curl -4 -fsSL ifconfig.me)"
echo ""
echo "    To update after git push:"
echo "    cd $APP_DIR && git pull && docker compose build && docker compose up -d"
