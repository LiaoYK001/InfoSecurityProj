# Ubuntu 服务器部署指南 — SecureChat 多端演示

## 目录

1. [架构概述](#1-架构概述)
2. [前置条件](#2-前置条件)
3. [服务端部署](#3-服务端部署)
4. [Nginx 反向代理配置（HTTPS + WSS）](#4-nginx-反向代理配置https--wss)
5. [防火墙配置](#5-防火墙配置)
6. [启动与验证](#6-启动与验证)
7. [教室多端演示操作流程](#7-教室多端演示操作流程)
8. [常见问题排查](#8-常见问题排查)
9. [一键快速部署脚本](#9-一键快速部署脚本)
10. [方案 B：Nginx Proxy Manager 外部网关部署](#10-方案-b-nginx-proxy-manager-外部网关部署)

---

## 1. 架构概述

```
┌─────────────┐      HTTPS / WSS       ┌───────────────────────────────────┐
│ 同学1 笔记本 │ ◄──────────────────────► │                                   │
│  (用户 A)    │                          │  Ubuntu 服务器                     │
├─────────────┤      port 443            │                                   │
│ 教室电脑     │ ◄──────────────────────► │  nginx (SSL 终止)                 │
│  (用户 B)    │                          │    ├─ /          → 静态 Web 文件  │
├─────────────┤                          │    └─ /ws        → WebSocket 代理 │
│ 同学2 平板   │ ◄──────────────────────► │                                   │
│  (用户 C)    │                          │  chat_server.py (127.0.0.1:8765) │
└─────────────┘                          └───────────────────────────────────┘
```

**关键要点：**

- **Web Crypto API 要求安全上下文 (Secure Context)**：浏览器的 `crypto.subtle` 仅在 HTTPS 或 localhost 下可用。因此远程访问必须使用 HTTPS。
- **nginx 做 SSL 终止**：统一处理 HTTPS 和 WSS，后端 chat_server.py 仍使用普通 WebSocket。
- **所有设备只需浏览器**：不需要安装任何软件，打开网址即可使用。

---

## 2. 前置条件

| 项目     | 要求                                            |
| -------- | ----------------------------------------------- |
| 操作系统 | Ubuntu 20.04 / 22.04 / 24.04 LTS                |
| Python   | 3.10+                                           |
| 网络     | 服务器和演示设备在同一局域网，或服务器有公网 IP |
| 端口     | 80 和 443 端口可用                              |
| 权限     | sudo 权限                                       |

---

## 3. 服务端部署

### 3.1 上传项目文件

**方法一：Git 克隆**（如果仓库已推送到 GitHub/Gitee）

```bash
cd ~
git clone <你的仓库地址> SecureChat
cd SecureChat
```

**方法二：SCP/SFTP 上传**

```bash
# 在 Windows 上执行（PowerShell），将项目上传到服务器
scp -r C:\Users\czl1\Desktop\Project\InfoSecurityProj user@<服务器IP>:~/SecureChat
```

**方法三：U 盘拷贝后解压**

```bash
# 假设文件在 /media/usb/
cp -r /media/usb/InfoSecurityProj ~/SecureChat
cd ~/SecureChat
```

### 3.2 安装 Python 依赖

```bash
cd ~/SecureChat

# 确认 Python 版本
python3 --version   # 需要 3.10+

# 安装 pip（如未安装）
sudo apt update
sudo apt install -y python3-pip python3-venv

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install websockets cryptography
```

### 3.3 验证服务端可启动

```bash
cd ~/SecureChat
source .venv/bin/activate

# 测试启动（监听所有接口）
python3 chat_server.py --host 0.0.0.0 --port 8765
# 看到 "服务端启动: ws://0.0.0.0:8765" 即成功
# Ctrl+C 退出
```

---

## 4. Nginx 反向代理配置（HTTPS + WSS）

### 4.1 安装 Nginx

```bash
sudo apt update
sudo apt install -y nginx
```

### 4.2 生成自签名 SSL 证书

> 自签名证书在教室演示场景完全够用。浏览器会显示安全警告，手动点击"继续前往"即可。

```bash
# 创建证书目录
sudo mkdir -p /etc/nginx/ssl

# 生成自签名证书（有效期 365 天）
# 交互式会要求填写信息，全部直接回车或填任意值即可
sudo openssl req -x509 -nodes -days 365 \
  -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/securechat.key \
  -out /etc/nginx/ssl/securechat.crt \
  -subj "/CN=SecureChat/O=Demo/C=CN"
```

### 4.3 拷贝 Web 静态文件

```bash
# 将 web/ 目录拷贝到 nginx 可访问的位置
sudo mkdir -p /var/www/securechat
sudo cp -r ~/SecureChat/web/* /var/www/securechat/
sudo chown -R www-data:www-data /var/www/securechat
```

### 4.4 编写 Nginx 配置

```bash
sudo nano /etc/nginx/sites-available/securechat
```

**粘贴以下内容：**

```nginx
server {
    listen 80;
    server_name _;

    # HTTP 自动跳转 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/securechat.crt;
    ssl_certificate_key /etc/nginx/ssl/securechat.key;

    # Web 静态文件
    root /var/www/securechat;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }

    # WebSocket 反向代理
    location /ws {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;   # 24h，防止长连接超时
        proxy_send_timeout 86400;
    }
}
```

### 4.5 启用配置

```bash
# 创建符号链接启用站点
sudo ln -sf /etc/nginx/sites-available/securechat /etc/nginx/sites-enabled/securechat

# 删除默认站点（避免冲突）
sudo rm -f /etc/nginx/sites-enabled/default

# 测试配置是否正确
sudo nginx -t

# 重新加载 nginx
sudo systemctl reload nginx
```

---

## 5. 防火墙配置

```bash
# 允许 HTTP 和 HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 确认防火墙状态
sudo ufw status
```

> 如果 ufw 未启用，可以跳过。如果是云服务器，还需在云控制台安全组中放行 80 和 443 端口。

---

## 6. 启动与验证

### 6.1 启动服务端（使用 systemd 服务）

**方法一：前台运行（调试/演示时使用）**

```bash
cd ~/SecureChat
source .venv/bin/activate
python3 chat_server.py --host 0.0.0.0 --port 8765
```

**方法二：创建 systemd 服务（推荐，自动启动）**

```bash
sudo nano /etc/systemd/system/securechat.service
```

**粘贴以下内容（将 `<your-user>` 替换为你的 Ubuntu 用户名）：**

```ini
[Unit]
Description=SecureChat WebSocket Relay Server
After=network.target

[Service]
Type=simple
User=<your-user>
WorkingDirectory=/home/<your-user>/SecureChat
ExecStart=/home/<your-user>/SecureChat/.venv/bin/python3 chat_server.py --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable securechat    # 开机自启
sudo systemctl start securechat     # 立即启动
sudo systemctl status securechat    # 查看状态
```

### 6.2 查看服务器 IP 地址

```bash
# 查看局域网 IP
ip addr show | grep "inet " | grep -v 127.0.0.1
# 通常类似 192.168.1.xxx 或 10.x.x.x
```

记下 IP 地址，例如 `192.168.1.100`。

### 6.3 本机验证

```bash
# 验证 chat_server 是否运行
curl -s http://127.0.0.1:8765 || echo "WebSocket server is running (connection refused is expected for HTTP)"

# 验证 nginx 是否运行
curl -sk https://127.0.0.1/ | head -5
# 应看到 index.html 的 HTML 内容
```

### 6.4 远程验证

在另一台设备的浏览器中打开：

```
https://192.168.1.100/
```

> 因为使用自签名证书，浏览器会警告"不安全"。点击 **高级** → **继续前往** 即可。

如果页面正常加载，说明部署成功。

---

## 7. 教室多端演示操作流程

### 前置条件

- Ubuntu 服务器已按上述步骤部署完毕
- 服务器 IP 已知（例如 `192.168.1.100`）
- 所有演示设备（笔记本、教室电脑、平板）与服务器在同一局域网
- 每台设备上打开 **Chrome/Edge/Safari** 浏览器

### 演示场景

三个用户之间的点对点加密通信：

- **用户 A**（同学1 笔记本）↔ **用户 B**（教室电脑）
- **用户 A**（同学1 笔记本）↔ **用户 C**（同学2 平板）
- **用户 B**（教室电脑）↔ **用户 C**（同学2 平板）

### 步骤 1：所有设备打开网页

每台设备的浏览器访问：

```
https://<服务器IP>/
```

例如 `https://192.168.1.100/`

> **首次访问处理证书警告**：
>
> - Chrome/Edge：点击 **高级** → **继续前往 192.168.1.100（不安全）**
> - Safari (iPad)：点击 **继续** → 弹窗中选择 **继续访问此网站**
> - Firefox：点击 **高级** → **接受风险并继续**

### 步骤 2：每台设备生成密钥

在每台设备上：

1. 点击左侧 **「生成 RSA-2048 密钥对」** 按钮
2. 等待密钥生成完成，界面显示 ✅ 和指纹
3. 右侧 Crypto Console 显示密钥信息

| 设备         | 操作                        | 预期结果                        |
| ------------ | --------------------------- | ------------------------------- |
| 同学1 笔记本 | 点击 "生成 RSA-2048 密钥对" | 显示公钥指纹 (如 `a3b2c1d4...`) |
| 教室电脑     | 点击 "生成 RSA-2048 密钥对" | 显示公钥指纹 (如 `e5f6a7b8...`) |
| 同学2 平板   | 点击 "生成 RSA-2048 密钥对" | 显示公钥指纹 (如 `c9d0e1f2...`) |

### 步骤 3：各设备连接服务器

在每台设备上：

1. **服务器地址**：应自动填写 `wss://192.168.1.100/ws`（远程访问时自动检测）
2. **用户 ID**：分别输入不同名称
   - 同学1 笔记本：输入 `Alice`
   - 教室电脑：输入 `Bob`
   - 同学2 平板：输入 `Charlie`
3. 点击 **「连接」** 按钮
4. 状态变为 **已连接**，联系人列表自动显示其他在线用户

> **注意**：三个用户连接后，每个人的联系人列表应显示另外两个人。

### 步骤 4：演示 Alice ↔ Bob 通信

**Alice 端（同学1 笔记本）：**

1. 在联系人列表中点击 **Bob**
2. 在消息输入框输入：`你好 Bob，这是一条加密消息！`
3. 点击 **发送**
4. 观察右侧 Crypto Console 显示加密过程：
   - `生成随机 AES-256 会话密钥...`
   - `AES-GCM 加密完成`
   - `RSA-OAEP 包裹会话密钥完成`
   - `wrapped_key: 344 chars`

**Bob 端（教室电脑）：**

1. 在联系人列表中点击 **Alice**
2. 看到 Alice 发来的解密消息
3. Crypto Console 显示解密过程：
   - `收到来自 Alice 的加密消息`
   - `RSA-OAEP 解包会话密钥...`
   - `AES-GCM 解密成功，明文长度: XX`
4. 回复：`收到！Bob 回复中，消息已加密。`

**给老师展示的要点**：

- 打开 Crypto Console 展示完整的加密/解密日志
- 强调 `wrapped_key`、`nonce`、`ciphertext` 全部是 Base64 密文
- 服务端日志上只能看到 `payload_len=XXX`，完全无法看到聊天内容

### 步骤 5：演示 Alice ↔ Charlie 通信

**Alice 端（同学1 笔记本）：**

1. 在联系人列表中切换到 **Charlie**（之前和 Bob 的聊天记录仍然保留）
2. 输入消息：`Charlie，我是 Alice，端到端加密消息！`
3. 点击发送

**Charlie 端（同学2 平板）：**

1. 点击联系人 **Alice**
2. 看到解密后的消息
3. 回复：`收到，Charlie 这边也是加密的！`

### 步骤 6：（可选）展示服务端日志

在 Ubuntu 服务器终端查看服务端日志：

```bash
# 如果用前台运行，直接在终端查看
# 如果用 systemd，查看日志：
sudo journalctl -u securechat -f --no-pager
```

日志中只能看到：

```
收到消息: type=chat_message sender=Alice receiver=Bob payload_len=XXX
```

**没有任何明文内容** — 这就是"盲转发"的直接证据。

### 步骤 7：（可选）Wireshark 抓包演示

在服务器上或任一客户端设备上启动 Wireshark：

1. 过滤条件：`tcp.port == 443`
2. 发送一条消息
3. 找到 TLS 加密的 WebSocket 帧
4. 展示 payload 全部是密文

---

## 8. 常见问题排查

### Q1：浏览器显示"此网站的连接不安全"

**正常现象**。自签名证书会触发此警告。

- Chrome/Edge：**高级 → 继续前往**
- Safari：**继续 → 继续访问此网站**
- Firefox：**高级 → 接受风险并继续**

### Q2：WebSocket 连接失败 / `crypto.subtle is undefined`

**原因**：通过 HTTP（非 HTTPS）访问页面，浏览器阻止 Web Crypto API。

**解决**：确保通过 `https://` 而非 `http://` 访问。检查 nginx 的 HTTP→HTTPS 跳转是否生效。

### Q3：连接后看不到其他用户

**排查步骤**：

1. 确认所有用户都已点击"连接"并显示"已连接"
2. 检查服务端日志是否有"用户注册成功"
3. 检查服务器防火墙是否放行 443 端口

### Q4：消息发送后对方收不到

**排查步骤**：

1. 检查服务端日志中是否有 `type=chat_message` 的转发记录
2. 确认接收方的用户 ID 输入正确（区分大小写）
3. 查看 Crypto Console 是否有错误信息

### Q5：iPad / 手机上页面显示不正常

页面已做基础响应式适配。如果显示异常：

- 尝试横屏模式
- 使用 Chrome 或 Safari（推荐）

### Q6：想用公网 IP / 域名正式部署

将自签名证书替换为 Let's Encrypt 免费证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
# 按提示操作，证书会自动配置到 nginx
```

### Q7：服务端意外退出 / 重启后需要手动启动

如果使用了 systemd 服务（方法二），已配置 `Restart=always`，会自动重启。

查看状态：`sudo systemctl status securechat`
查看日志：`sudo journalctl -u securechat -f`

---

## 9. 一键快速部署脚本

将以下脚本保存为 `deploy.sh`，在 Ubuntu 服务器上运行：

```bash
#!/bin/bash
set -e

# ===== 配置 =====
PROJECT_DIR="$HOME/SecureChat"
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
WantedBy=multi-party.target
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
sudo systemctl status securechat --no-pager -l | head -10
echo ""
echo "提示: 浏览器首次访问时需要接受自签名证书警告"
```

**使用方法：**

```bash
cd ~/SecureChat
chmod +x deploy.sh
./deploy.sh
```

---

## 10. 方案 B：Nginx Proxy Manager 外部网关部署

> **适用场景**：Ubuntu 服务器只跑 HTTP 服务，另有一台网关服务器已安装 [Nginx Proxy Manager (NPM)](https://nginxproxymanager.com/)，由 NPM 统一做 HTTPS 终止和反向代理。
>
> 此方案 **不需要在 Ubuntu 上安装 nginx**，也不需要自签名证书。

### 10.0 架构示意

```
┌──────────┐    HTTPS/WSS     ┌──────────────────────┐    HTTP     ┌──────────────────────────┐
│  浏览器   │ ◄──────────────► │  网关服务器            │ ◄────────► │  Ubuntu 服务器             │
│          │   port 443       │  Nginx Proxy Manager  │            │                           │
│          │                  │  (SSL 终止 + 路由)     │  :8080 ──► │  python -m http.server    │
│          │                  │                        │  :8765 ──► │  chat_server.py (WS)      │
└──────────┘                  └──────────────────────┘            └──────────────────────────┘
```

### 10.1 Ubuntu 端：启动两个服务

需要启动 **两个进程**：

| 服务                     | 端口 | 作用                               |
| ------------------------ | ---- | ---------------------------------- |
| `chat_server.py`         | 8765 | WebSocket 中继转发（盲转发）       |
| `python3 -m http.server` | 8080 | 提供 Web UI 静态文件 (HTML/CSS/JS) |

> ⚠️ **注意**：Web 静态文件服务必须从 `~/SecureChat/web/` 目录启动（`cd ~/SecureChat/web`），**不是**项目根目录。否则访问 `/` 会显示项目目录列表而不是聊天页面。

#### 快速启动（tmux 方式，推荐演示用）

```bash
# SSH 登录 Ubuntu 后
cd ~/SecureChat
source .venv/bin/activate

# 启动 tmux（退出 SSH 后服务不会断）
tmux new -s securechat

# ── 窗格 1：WebSocket 服务端 ──
python3 chat_server.py --host 0.0.0.0 --port 8765

# 按 Ctrl+B 再按 % 分出第二个窗格

# ── 窗格 2：Web 静态文件服务 ──
cd ~/SecureChat/web
python3 -m http.server 8080 --bind 0.0.0.0
```

> **tmux 常用操作**：
>
> - 分离会话（退出 SSH 仍运行）：`Ctrl+B` 然后 `D`
> - 重新连接：`tmux attach -t securechat`
> - 切换窗格：`Ctrl+B` 然后方向键

#### 生产方式（systemd 服务，长期运行推荐）

**服务 1：WebSocket 中继服务端**

```bash
sudo tee /etc/systemd/system/securechat.service > /dev/null <<EOF
[Unit]
Description=SecureChat WebSocket Relay Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$HOME/SecureChat
ExecStart=$HOME/SecureChat/.venv/bin/python3 chat_server.py --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**服务 2：Web 静态文件服务器**

```bash
sudo tee /etc/systemd/system/securechat-web.service > /dev/null <<EOF
[Unit]
Description=SecureChat Web UI Static File Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$HOME/SecureChat/web
ExecStart=$HOME/SecureChat/.venv/bin/python3 -m http.server 8080 --bind 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

**启用并启动**

```bash
sudo systemctl daemon-reload
sudo systemctl enable securechat securechat-web
sudo systemctl start securechat securechat-web

# 验证
sudo systemctl status securechat securechat-web
```

### 10.2 Ubuntu 端：防火墙放行

```bash
sudo ufw allow 8080/tcp   # Web UI
sudo ufw allow 8765/tcp   # WebSocket
sudo ufw status
```

> 如果是云服务器，还需在云控制台安全组中放行 8080 和 8765。

### 10.3 验证 Ubuntu 端服务

```bash
# 验证 Web UI 可访问
curl -s http://127.0.0.1:8080/ | head -3
# 应看到: <!DOCTYPE html> ...

# 验证 WebSocket 端口在监听
ss -tlnp | grep -E '8080|8765'
# 应看到两行 LISTEN
```

### 10.4 Nginx Proxy Manager 配置

在 NPM Web 管理界面中操作：

#### 步骤 1：添加 Proxy Host

1. 登录 NPM 管理面板 → **Hosts** → **Proxy Hosts** → **Add Proxy Host**

2. **Details 选项卡**：

   | 字段                  | 值                                          |
   | --------------------- | ------------------------------------------- |
   | Domain Names          | `chat.yourdomain.com`（你的域名/子域名）    |
   | Scheme                | `http`                                      |
   | Forward Hostname / IP | Ubuntu 服务器的内网 IP（如 `192.168.1.50`） |
   | Forward Port          | `8080`                                      |
   | ✅ Websocket Support  | **开启**                                    |

3. **SSL 选项卡**：

   | 字段              | 值                                               |
   | ----------------- | ------------------------------------------------ |
   | SSL Certificate   | 选择已有证书或 **Request a new SSL Certificate** |
   | ✅ Force SSL      | 开启                                             |
   | ✅ HTTP/2 Support | 开启                                             |

4. 点击 **Save** — 此时 `https://chat.yourdomain.com/` 应该能打开 Web UI 页面。

#### 步骤 2：添加 WebSocket 自定义路径

1. 编辑刚创建的 Proxy Host → **Custom Locations** 选项卡

2. 点击 **Add Location**：

   | 字段                  | 值                                          |
   | --------------------- | ------------------------------------------- |
   | Location              | `/ws`                                       |
   | Scheme                | `http`                                      |
   | Forward Hostname / IP | Ubuntu 服务器的内网 IP（如 `192.168.1.50`） |
   | Forward Port          | `8765`                                      |

3. 点击该 Location 右侧的 **⚙️ 齿轮图标**，在 **Custom Nginx Configuration** 中粘贴：

   ```nginx
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection "upgrade";
   proxy_http_version 1.1;
   proxy_read_timeout 86400;
   proxy_send_timeout 86400;
   ```

4. 点击 **Save**。

#### 步骤 3：验证

浏览器访问 `https://chat.yourdomain.com/`：

- Web UI 页面正常加载 ✅
- 服务器地址输入框自动填充为 `wss://chat.yourdomain.com/ws` ✅（app.js 会自动检测）
- 输入用户名 → 点击连接 → 状态变为"已连接" ✅

> **原理**：`web/app.js` 中的 `autoDetectServerUrl()` 函数会自动检测：当通过非 localhost 的 HTTPS 访问时，自动将 WebSocket 地址设为 `wss://{当前域名}/ws`。无需手动填写。

### 10.5 完整操作速查

```bash
# ===== Ubuntu 端（SSH 登录后执行） =====

# 方式一：tmux 快速启动
cd ~/SecureChat && source .venv/bin/activate
tmux new -s securechat
python3 chat_server.py --host 0.0.0.0 --port 8765
# Ctrl+B, % 分屏
cd ~/SecureChat/web && python3 -m http.server 8080 --bind 0.0.0.0
# Ctrl+B, D 分离

# 方式二：systemd（如已配置）
sudo systemctl start securechat securechat-web

# 检查状态
ss -tlnp | grep -E '8080|8765'
```

```
===== NPM 端 =====
Proxy Host:
  Domain:   chat.yourdomain.com
  Forward:  http://<Ubuntu-IP>:8080
  WebSocket Support: ✅
  SSL: ✅ Force SSL

Custom Location:
  /ws → http://<Ubuntu-IP>:8765
  + WebSocket upgrade headers
```

---

## 附录：快速参考卡片

演示当天随身携带此卡片：

```
┌────────────────────────────────────────────────┐
│  SecureChat 演示快速参考                         │
│                                                  │
│  访问地址: https://<服务器IP>/                    │
│  WebSocket: 自动检测 (wss://<IP>/ws)             │
│                                                  │
│  操作流程:                                       │
│  1. 打开网页 → 接受证书警告                       │
│  2. 点击 "生成 RSA-2048 密钥对"                   │
│  3. 输入用户名 → 点击 "连接"                      │
│  4. 点击联系人 → 输入消息 → 发送                  │
│                                                  │
│  展示要点:                                       │
│  - Crypto Console: 完整加解密日志                 │
│  - 服务端日志: 只有 payload_len, 无明文           │
│  - 跨平台: 笔记本+电脑+平板 同时互通             │
│                                                  │
│  排错:                                           │
│  - 页面空白 → 确认 https:// 而非 http://         │
│  - 连不上 → sudo systemctl status securechat     │
│  - 重启服务 → sudo systemctl restart securechat  │
└────────────────────────────────────────────────┘
```
