# SecureChat Web 客户端

基于浏览器的端到端加密聊天客户端，与桌面端（Tkinter）共用同一个 WebSocket 中继服务端。

## 快速启动

### 1. 启动中继服务端

```bash
python chat_server.py --host 127.0.0.1 --port 8765
```

### 2. 启动 Web 静态文件服务器

```bash
cd web
python -m http.server 8080
```

### 3. 打开浏览器

访问 `http://localhost:8080`，即可使用 Web 客户端。

可以同时打开多个浏览器标签页，每个标签页作为一个独立用户。

## 功能

- **RSA-2048 密钥对生成** — 使用浏览器原生 Web Crypto API
- **端到端加密聊天** — RSA-OAEP + AES-256-GCM 混合加密
- **在线联系人列表** — 实时显示在线用户及公钥指纹
- **Crypto Console** — 实时展示加密/解密过程日志
- **跨客户端互通** — 可与桌面端 (Tkinter) 客户端互相发送加密消息

## 技术栈

- 原生 HTML + CSS + JavaScript（无框架依赖）
- Web Crypto API（RSA-OAEP SHA-256 + AES-256-GCM）
- WebSocket（浏览器原生）

## 文件结构

| 文件        | 说明                              |
| ----------- | --------------------------------- |
| index.html  | 主页面（UI 布局）                 |
| style.css   | 深色主题样式（类 Discord 风格）   |
| app.js      | 主应用逻辑（WebSocket + UI）      |
| crypto.js   | 加密模块（Web Crypto API 封装）   |
| protocol.js | 消息协议（对应 chat_protocol.py） |

## 加密参数

与桌面端完全一致：

| 参数     | 值                      |
| -------- | ----------------------- |
| RSA      | 2048-bit, OAEP, SHA-256 |
| AES      | 256-bit, GCM            |
| Nonce    | 12 bytes                |
| Auth Tag | 128-bit (16 bytes)      |
| 公钥格式 | SPKI PEM                |
| 编码     | 标准 Base64             |

## 已知限制

- 密钥仅存在于内存中，刷新页面后密钥丢失。
- 不支持消息持久化（与桌面端一致）。
- 不支持离线消息。
- 需要 HTTPS 或 localhost 环境才能使用 Web Crypto API。
