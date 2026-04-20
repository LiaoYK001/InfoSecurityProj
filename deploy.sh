#!/bin/bash
# SecureChat 一键部署脚本 — Ubuntu 服务器
# 用法: chmod +x deploy.sh && ./deploy.sh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="/var/www/securechat"
CERT_DIR="/etc/nginx/ssl"
SERVICE_USER="$(whoami)"

echo "===== SecureChat 一键部署 ====="
echo "项目目录: $PROJECT_DIR"
echo "运行用户: $SERVICE_USER"
echo ""

# 1. 系统依赖
echo "[1/7] 安装系统依赖..."
sudo apt update -qq
sudo apt install -y python3 python3-pip python3-venv nginx openssl

# 2. Python 虚拟环境
echo "[2/7] 配置 Python 虚拟环境..."
cd "$PROJECT_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -q websockets cryptography

# 3. 自签名证书
echo "[3/7] 生成自签名 SSL 证书..."
sudo mkdir -p "$CERT_DIR"
if [ ! -f "$CERT_DIR/securechat.crt" ]; then
    sudo openssl req -x509 -nodes -days 365 \
        -newkey rsa:2048 \
        -keyout "$CERT_DIR/securechat.key" \
        -out "$CERT_DIR/securechat.crt" \
        -subj "/CN=SecureChat/O=Demo/C=CN" 2>/dev/null
    echo "  证书已生成"
else
    echo "  证书已存在，跳过"
fi

# 4. Web 静态文件
echo "[4/7] 部署 Web 静态文件..."
sudo mkdir -p "$WEB_DIR"
sudo cp -r "$PROJECT_DIR/web/"* "$WEB_DIR/"
sudo chown -R www-data:www-data "$WEB_DIR"

# 5. Nginx 配置
echo "[5/7] 配置 Nginx..."
sudo tee /etc/nginx/sites-available/securechat > /dev/null <<'NGINX'
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name _;
    ssl_certificate     /etc/nginx/ssl/securechat.crt;
    ssl_certificate_key /etc/nginx/ssl/securechat.key;
    root /var/www/securechat;
    index index.html;
    location / {
        try_files $uri $uri/ =404;
    }
    location /ws {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/securechat /etc/nginx/sites-enabled/securechat
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

# 6. Systemd 服务
echo "[6/7] 创建 systemd 服务..."
sudo tee /etc/systemd/system/securechat.service > /dev/null <<EOF
[Unit]
Description=SecureChat WebSocket Relay Server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python3 chat_server.py --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable securechat
sudo systemctl restart securechat

# 7. 防火墙
echo "[7/7] 配置防火墙..."
sudo ufw allow 80/tcp 2>/dev/null || true
sudo ufw allow 443/tcp 2>/dev/null || true

# 完成
echo ""
echo "===== 部署完成 ====="
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "服务器 IP: $SERVER_IP"
echo "访问地址: https://$SERVER_IP/"
echo "WebSocket: wss://$SERVER_IP/ws"
echo ""
echo "服务端状态:"
sudo systemctl status securechat --no-pager -l 2>&1 | head -10
echo ""
echo "提示: 浏览器首次访问时需要接受自签名证书警告"
