#!/usr/bin/env bash
# usage:  bash <(wget -qO- https://raw.githubusercontent.com/happyuk/net-config-ui/main/bootstrap_private_repo.sh)

set -e

# --- CONFIGURATION ---
APP_DIR="$HOME/net-config-ui"
GIT_URL="git@github.com:happyuk/net-config-ui.git"
# ---------------------

clear
echo "======================================================="
echo "   NET-CONFIG-UI INSTALLATION WIZARD"
echo "======================================================="
echo ""

echo "Step 1: Preparing your system..."
sudo apt update -qq
sudo apt install -y curl git python3-venv python3-dev build-essential libssl-dev libffi-dev > /dev/null
echo "✓ System dependencies ready."
echo ""

# --- SSH KEY AUTOMATION ---
if [[ "$GIT_URL" == git@* ]]; then
    echo "Step 2: Setting up secure access..."
    SSH_DIR="$HOME/.ssh"
    KEY_FILE="$SSH_DIR/id_ed25519"
    
    mkdir -p "$SSH_DIR"
    chmod 700 "$SSH_DIR"

    if [ ! -f "$KEY_FILE" ]; then
        ssh-keygen -t ed25519 -N "" -f "$KEY_FILE" -q
        echo "✓ New security key generated."
    else
        echo "✓ Existing security key found."
    fi

    # Pre-authorize GitHub to prevent "Are you sure (yes/no)?"
    DOMAIN=$(echo "$GIT_URL" | cut -d'@' -f2 | cut -d':' -f1)
    ssh-keyscan "$DOMAIN" >> "$SSH_DIR/known_hosts" 2>/dev/null

    echo ""
    echo "-------------------------------------------------------"
    echo "INSTRUCTION: To access the private repository, you must"
    echo "register this machine's key with the company account."
    echo ""
    echo "1. Highlight and COPY the code below:"
    echo ""
    cat "${KEY_FILE}.pub"
    echo ""
    echo "2. GO TO: https://github.com/settings/keys"
    echo "3. Click 'New SSH Key', paste the code, and click 'Add'."
    echo "-------------------------------------------------------"
    echo ""
    
    # Validation loop: Don't let them proceed until the key works
    while true; do
        read -p "Have you saved the key on the website? (y/n): " choice
        if [[ "$choice" =~ ^[Yy]$ ]]; then
            echo "Checking connection..."
            if ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
                echo "✓ Success! GitHub has recognized your machine."
                break
            else
                echo "X Error: Connection failed. Please ensure the key was saved correctly."
                echo "  (Make sure there are no extra spaces when you pasted it)."
                echo ""
            fi
        fi
    done
fi

echo ""
echo "Step 3: Downloading the application..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR"
    git remote set-url origin "$GIT_URL"
    git pull
else
    git clone "$GIT_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

echo ""
echo "Step 4: Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip > /dev/null
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null
fi

echo ""
echo "======================================================="
echo "   INSTALLATION COMPLETE!"
echo "======================================================="
echo "To start the application run this command:"
echo ""
echo "cd $APP_DIR && source venv/bin/activate && python main.py"
echo "======================================================="