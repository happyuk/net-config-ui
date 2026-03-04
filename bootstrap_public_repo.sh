#!/usr/bin/env bash
# usage:  bash <(wget -qO- https://raw.githubusercontent.com/happyuk/net-config-ui/main/bootstrap_public_repo.sh)

set -e

APP_DIR="$HOME/net-config-ui"

echo "Installing system dependencies..."
sudo apt update -qq
sudo apt install -y python3-venv python3-dev build-essential libssl-dev libffi-dev

echo "Cloning or updating repository..."

if [ -d "$APP_DIR" ]; then
    echo "Existing install found. Pulling latest..."
    cd "$APP_DIR"
    git pull
else
    git clone https://github.com/happyuk/net-config-ui.git "$APP_DIR"
    cd "$APP_DIR"
fi

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Installation complete."
echo "Run the app with:"
echo "cd $APP_DIR && source venv/bin/activate && python main.py"