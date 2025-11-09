#!/bin/bash
set -e

# --- CONFIGURATION ---
# !!! UPDATE THIS TO YOUR ACTUAL REPO URL !!!
REPO_URL="https://github.com/rajats45/DBF.git"
INSTALL_DIR="/opt/mongo-tool"

if [ "$EUID" -ne 0 ]; then echo "Please run as root (sudo)."; exit 1; fi

echo "--- STARTING INSTALLATION ---"

# 1. Cleanup (Force kill old processes to prevent hangs)
echo "Cleaning up old installation..."
systemctl disable --now mongo-tool 2>/dev/null || true
pkill -9 -f python3 2>/dev/null || true
rm -rf "$INSTALL_DIR" /usr/local/bin/mongo-tool /etc/systemd/system/mongo-tool.service

# 2. Dependencies
echo "Installing dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null
apt-get install -y curl git python3-pip python3-venv -qq >/dev/null
if ! command -v docker &> /dev/null; then curl -fsSL https://get.docker.com | sh >/dev/null 2>&1; fi

# 3. Clone Repository
echo "Cloning latest version..."
git clone "$REPO_URL" "$INSTALL_DIR" -q
cd "$INSTALL_DIR"

# 4. Setup Environment
echo "Configuring environment..."
python3 -m venv venv
./venv/bin/pip install Flask python-dotenv -qq

# Create secure password file if missing
if [ ! -f .env ]; then
    echo "MONGO_PASSWORD='CHANGE_ME'" > .env
    chmod 600 .env
fi

# 5. Install Systemd Service
echo "Installing system service..."
cat <<EOF > /etc/systemd/system/mongo-tool.service
[Unit]
Description=Mongo Manager
After=docker.service network.target
[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/app.py
Restart=always
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now mongo-tool

# 6. Helper Scripts
echo -e "#!/bin/bash\nnano $INSTALL_DIR/.env\nsystemctl restart mongo-tool\necho 'Password set & server restarted.'" > /usr/local/bin/mongo-setpass
chmod +x /usr/local/bin/mongo-setpass

echo ""
echo "=== INSTALLATION COMPLETE ==="
echo "1. Run: sudo mongo-setpass"
echo "2. Open: http://$(hostname -I | awk '{print $1}'):5000"