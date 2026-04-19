# 端到端加密即时通讯软件设计与实现 — 课程设计报告

<!-- markdownlint-disable MD047 MD033 -->

> **说明**：本文件为 Markdown 格式的报告正文。最终提交时可导出为 Word/PDF。截图占位符标记为 `![描述](screenshots/文件名.png)`，采集截图后替换即可。

---

## 第一章 任务分析

### 1.1 课程设计任务

本课程设计选题为"端到端加密的即时通讯软件设计与实现"（任务 1）。要求基于前 4 周实现的 RSA 加密工具，在后 4 周内完成一个能够进行端到端加密聊天的即时通讯软件。

### 1.2 核心需求分析

根据课程任务书，本系统必须满足以下三项硬性要求：

1. **消息加密算法**：程序必须能够对聊天消息进行加密和解密。本项目选择 AES-256-GCM 作为消息体的对称加密算法，提供加密与完整性保护。
2. **密钥交换机制**：通信双方必须能够安全地协商加密密钥。本项目利用前 4 周实现的 RSA 公私钥机制，通过 RSA-OAEP(SHA-256) 安全传输一次性 AES 会话密钥。
3. **即时通信功能**：程序必须是完整的通信软件，传输过程中消息为密文，接收端自动解密展示。本项目使用 WebSocket 协议实现全双工实时通信。

### 1.3 安全目标

- 消息在传输链路上全程为密文
- 中继服务端作为盲转发节点，无法获取聊天内容
- 每条消息使用独立的一次性 AES-256 会话密钥
- 公钥指纹可用于带外验证，防止中间人攻击

### 1.4 与前 4 周成果的关系

前 4 周完成了 RSA 加密工具（`InfoSecurWork_GUI.py`），实现了 RSA 密钥生成、文件加解密和文本加解密功能。后 4 周将 RSA 模块（`rsa_core.py`）集成到即时通讯系统中，用于密钥交换环节，体现了课设的延续性和完整性。

---

## 第二章 相关理论及技术基础

### 2.1 网络通信协议 — WebSocket

WebSocket 是一种在单个 TCP 连接上进行全双工通信的协议（RFC 6455）。与传统 HTTP 请求-响应模式不同，WebSocket 建立连接后，客户端和服务端可以随时互发消息，无需轮询。

**选型理由**：

- 全双工通信天然适合即时通讯场景
- 消息以帧为单位传输，无需自行处理粘包/拆包
- 浏览器原生支持 WebSocket，为未来扩展 Web 客户端预留了可能性
- Python `websockets` 库提供简洁的异步 API

本项目定义了统一的 JSON 消息协议，所有消息格式为：

```json
{
  "type": "消息类型",
  "sender_id": "发送方",
  "receiver_id": "接收方",
  "timestamp": "ISO 时间戳",
  "payload": { ... }
}
```

共 7 种消息类型：`register`（注册）、`public_key`（公钥交换）、`chat_message`（聊天消息）、`ack`（确认回执）、`error`（错误通知）、`heartbeat`（心跳）、`user_list`（在线用户列表）。

### 2.2 消息加密算法 — AES-GCM

AES（Advanced Encryption Standard）是当前最广泛使用的对称加密算法。GCM（Galois/Counter Mode）是 AES 的一种 AEAD（Authenticated Encryption with Associated Data）工作模式。

**AES-GCM 的核心特性**：

- **加密与认证一体化**：GCM 模式在加密的同时生成认证标签（Authentication Tag），接收方可以验证密文是否被篡改。
- **无需额外 HMAC**：传统 AES-CBC 模式需要单独计算 HMAC 来保证完整性，而 GCM 自带完整性校验。
- **并行化友好**：GCM 基于 CTR 模式，加密过程可以并行执行。

本项目使用的参数：

| 参数       | 值                            |
| ---------- | ----------------------------- |
| 密钥长度   | 256 bit                       |
| Nonce 长度 | 12 byte（96 bit）             |
| 认证标签   | 128 bit（自动附加到密文末尾） |

**为什么选 AES-GCM 而非 AES-CBC**：AES-CBC 只提供加密，不提供完整性保护。如果攻击者篡改了密文，CBC 模式下接收方无法检测到。而 GCM 模式的认证标签可以立即发现篡改，安全性更高。

### 2.3 密钥交换机制 — RSA-OAEP

RSA 是经典的非对称加密算法，基于大整数分解的困难性。OAEP（Optimal Asymmetric Encryption Padding）是 RSA 的推荐填充方案（PKCS#1 v2），比旧版 PKCS#1 v1.5 更安全。

**RSA-OAEP 在本项目中的角色**：

RSA 不直接加密聊天消息（1024-bit 密钥最多只能加密约 86 字节），而是用于安全传输 AES 会话密钥。这就是"混合加密"方案：

1. 发送方生成一次性 AES-256 随机密钥
2. 用 AES-GCM 加密消息正文
3. 用接收方的 RSA 公钥加密（OAEP 填充）AES 会话密钥
4. 将加密后的会话密钥（`wrapped_key`）、Nonce 和密文一起发送

接收方用自己的 RSA 私钥解密 `wrapped_key`，得到 AES 密钥，再用 AES-GCM 解密消息正文。

**公钥指纹**：本项目对公钥做 SHA-256 哈希，取前 16 位十六进制作为指纹，用于用户之间的带外验证，防止中间人攻击。

---

## 第三章 解决思路与设计

### 3.1 概要设计

#### 3.1.1 系统架构

本系统采用"客户端-中继服务端-客户端"的三层架构：

```
┌──────────────┐    WebSocket     ┌──────────────────┐    WebSocket     ┌──────────────┐
│  客户端 A    │ ──────────────→ │  中继服务端       │ ──────────────→ │  客户端 B    │
│ (Alice)      │ ←────────────── │  (盲转发，不解密) │ ←────────────── │ (Bob)        │
│              │    密文传输      │                  │    密文传输      │              │
└──────────────┘                 └──────────────────┘                 └──────────────┘
```

**盲转发设计**：中继服务端只负责用户注册、在线列表广播和消息路由，完全不解密任何消息 payload。服务端日志只记录消息类型、发送方、接收方和 payload 长度，不包含任何聊天明文。这样即使攻击者控制了服务端，也无法获取聊天内容。

#### 3.1.2 模块划分

| 层级   | 模块文件              | 职责                               |
| ------ | --------------------- | ---------------------------------- |
| 加密层 | `aes_core.py`         | AES-GCM 对称加密/解密              |
| 加密层 | `rsa_core.py`         | RSA 密钥管理、OAEP 加解密、指纹    |
| 加密层 | `message_crypto.py`   | 混合加密封装（RSA + AES-GCM 组合） |
| 协议层 | `chat_protocol.py`    | JSON 消息构造与解析                |
| 网络层 | `chat_client.py`      | 客户端 WebSocket 连接与事件分发    |
| 网络层 | `chat_server.py`      | 服务端 WebSocket 中继与用户管理    |
| 会话层 | `session_manager.py`  | 密钥状态管理与会话操作             |
| 表现层 | `desktop_chat_gui.py` | Tkinter 桌面 GUI 客户端            |

### 3.2 详细设计

#### 3.2.1 加密链路

**发送消息时的加密流程（5 步）**：

1. 用户输入明文消息
2. 生成一次性 AES-256 随机密钥（32 字节）
3. 使用 AES-GCM 加密明文 → 得到 Nonce（12 字节）+ 密文
4. 使用接收方 RSA 公钥 + OAEP 填充加密 AES 会话密钥 → 得到 `wrapped_key`
5. 将 `{wrapped_key, nonce, ciphertext}` 封装为 JSON 并通过 WebSocket 发送

**接收消息时的解密流程（4 步）**：

1. 收到 JSON 消息，提取 `wrapped_key`、`nonce`、`ciphertext`
2. 使用本地 RSA 私钥 + OAEP 解密 `wrapped_key` → 得到 AES 会话密钥
3. 使用 AES-GCM 解密密文 → 得到明文
4. 在聊天区显示明文，在 Crypto Console 显示解密过程日志

#### 3.2.2 密钥交换流程

1. 用户生成 RSA-2048 密钥对（或从文件加载已有私钥）
2. 连接服务端时发送公钥进行注册
3. 选择联系人时，自动发送本地公钥给对方
4. 对方收到公钥后自动导入，Crypto Console 显示指纹信息
5. 用户可对比指纹进行带外验证

#### 3.2.3 协议消息格式

所有消息统一为 JSON 格式 `{type, sender_id, receiver_id, timestamp, payload}`。7 种消息类型覆盖：用户注册、公钥交换、加密聊天、确认回执、错误通知、心跳保活、在线用户列表。

#### 3.2.4 GUI 线程模型

桌面客户端采用双线程架构：

- **主线程**：Tkinter GUI 事件循环，负责界面渲染和用户交互
- **后台线程**：WebSocket 网络 I/O，负责消息收发
- **通信机制**：`queue.Queue` 消息队列 + `after()` 每 100ms 轮询，确保线程安全

---

## 第四章 实现与测试

### 4.1 开发环境

| 项目         | 版本/说明                      |
| ------------ | ------------------------------ |
| 操作系统     | Windows 11                     |
| Python       | 3.12.12 (conda: infosecur_env) |
| cryptography | 46.0.7                         |
| websockets   | 16.0                           |
| GUI 框架     | Tkinter（Python 内置）         |
| IDE          | Visual Studio Code             |
| 版本管理     | Git                            |

### 4.2 关键实现

#### 4.2.1 AES-GCM 加解密（`aes_core.py`）

提供 `generate_aes_key()`、`encrypt_text()`、`decrypt_text()` 三个核心函数。密钥通过 `os.urandom()` 生成，Nonce 为 12 字节随机值，所有输入输出使用 Base64 编码。内部 `_validate_key()` 校验密钥长度必须为 128/192/256 bit。

#### 4.2.2 RSA-OAEP 密钥管理（`rsa_core.py`）

包含 `RSAKeyManager` 类（管理公私钥对和对端公钥）和顶层函数（`generate_rsa_key_pair`、`encrypt_bytes`、`decrypt_bytes`、序列化/反序列化等）。支持分块 RSA 加密以处理超长数据。公钥指纹通过 `get_public_key_fingerprint()` 计算 SHA-256 前 16 位 hex。

#### 4.2.3 混合加密封装（`message_crypto.py`）

`encrypt_chat_message()` 函数执行完整加密链路（生成 AES 密钥 → AES-GCM 加密 → RSA-OAEP 包裹），返回含 `wrapped_key`、`nonce`、`ciphertext` 和 `debug` 字段的字典。`decrypt_chat_message()` 执行反向解密。`debug` 字段包含 `wrapped_key_length`、`nonce_length`、`session_key_bits`，用于 Crypto Console 展示。

#### 4.2.4 WebSocket 中继服务端（`chat_server.py`）

`ChatRelayServer` 类处理连接管理、用户注册、消息路由和不活跃超时检测。服务端完全不解密 payload，只检查 `type` 和 `receiver_id` 进行转发。支持命令行参数 `--host`、`--port`、`--timeout`。

#### 4.2.5 桌面 GUI 客户端（`desktop_chat_gui.py`）

`DesktopChatApp` 类继承 `tk.Tk`，包含 5 个界面区域：登录区、密钥区、联系人区、聊天区、Crypto Console。Crypto Console 使用彩色文本标签显示加解密每一步的详细日志，直观展示混合加密全过程。

### 4.3 测试

#### 4.3.1 自动化测试

使用 Python `unittest` 框架，共 57 项测试全部通过：

| 测试文件              | 测试数 | 覆盖范围                               |
| --------------------- | ------ | -------------------------------------- |
| `test_crypto.py`      | 15     | AES-GCM 加解密、RSA 密钥管理、混合加密 |
| `test_protocol.py`    | 14     | 消息构造与解析、类型校验               |
| `test_protocol_v2.py` | 17     | 协议增强场景、边界条件                 |
| `test_integration.py` | 11     | 端到端加解密、会话管理集成             |

执行命令：`python -m unittest discover -s tests -v`

#### 4.3.2 人工验收

按 `tests/manual_acceptance.md` 完成双客户端全流程演示，验证项包括：密钥生成、连接注册、自动公钥交换、加密聊天、Crypto Console 日志、服务端盲转发、断连处理。

---

## 第五章 任务结果说明与结果分析

### 5.1 功能完成度

| 需求                     | 完成情况 |
| ------------------------ | -------- |
| 消息加密算法（AES-GCM）  | ✅ 完成  |
| 密钥交换机制（RSA-OAEP） | ✅ 完成  |
| 即时通信功能             | ✅ 完成  |
| 传输过程消息为密文       | ✅ 完成  |
| 接收端自动解密展示       | ✅ 完成  |

### 5.2 安全性分析

**传输密文验证**：使用 Wireshark 抓包（过滤 `tcp.port == 8765`），WebSocket 帧 payload 中 `wrapped_key`、`nonce`、`ciphertext` 均为 Base64 编码的密文，不含任何可识别的聊天明文。

**服务端安全**：服务端日志在整个演示过程中只显示消息类型和 payload 长度，不出现任何聊天明文。

**会话密钥安全**：每条消息生成独立的一次性 AES-256 随机密钥，即使某条消息的会话密钥被泄露，也不影响其他消息的安全性。

### 5.3 异常场景验证

| 场景                   | 预期行为               | 实际结果 |
| ---------------------- | ---------------------- | -------- |
| 未生成密钥就发消息     | 提示需要先生成密钥     | 符合预期 |
| 发送给已下线用户       | 提示对方不在线         | 符合预期 |
| 服务端关闭后客户端操作 | 客户端检测到断连并提示 | 符合预期 |

### 5.4 性能与局限性

- 本系统面向课程设计场景，未针对高并发进行优化
- RSA-2048 密钥交换安全性足够，但未采用前向安全的 Diffie-Hellman 密钥协商
- 当前不支持离线消息存储和消息持久化
- 不支持群聊和文件传输

---

## 第六章 运行截图

> 以下截图采集自实际运行演示，截图文件保存在 `document/screenshots/` 目录。

### 6.1 服务端启动

![服务端启动日志](screenshots/01_server_start.png)

### 6.2 客户端密钥生成与连接

![客户端 A 生成密钥](screenshots/02_alice_keygen.png)

![客户端 A 连接成功](screenshots/03_alice_connected.png)

### 6.3 联系人列表与公钥交换

![客户端 B 联系人列表](screenshots/04_bob_contact_list.png)

### 6.4 加密聊天过程

![Alice 发送消息](screenshots/05_alice_send_msg.png)

![Alice 端 Crypto Console 加密日志](screenshots/06_alice_crypto_log.png)

![Bob 收到消息](screenshots/07_bob_recv_msg.png)

![Bob 端 Crypto Console 解密日志](screenshots/08_bob_crypto_log.png)

### 6.5 服务端日志验证

![服务端日志不含明文](screenshots/09_server_log_noclear.png)

### 6.6 Wireshark 抓包验证

![Wireshark 捕获列表](screenshots/10_wireshark_list.png)

![Wireshark 帧 payload 为密文](screenshots/11_wireshark_payload.png)

---

## 第七章 程序使用说明

### 7.1 环境要求

- Python ≥ 3.10
- 操作系统：Windows / macOS / Linux

### 7.2 安装依赖

```bash
pip install -r requirements.txt
```

核心依赖：`cryptography`（加密库）、`websockets`（WebSocket 通信）。

### 7.3 运行自动化测试

```bash
python -m unittest discover -s tests -v
```

### 7.4 启动服务端

```bash
python chat_server.py --host 127.0.0.1 --port 8765
```

### 7.5 启动客户端

```bash
python desktop_chat_gui.py
```

操作步骤：

1. 点击"生成密钥"生成 RSA-2048 密钥对
2. 输入用户 ID，点击"连接"
3. 在左侧联系人列表选择在线用户
4. 在输入框输入消息，按 Enter 或点击"发送"
5. Crypto Console 面板实时显示加解密过程

### 7.6 打包为可执行文件

```bash
# 客户端
pyinstaller --onefile --windowed --name SecureChat desktop_chat_gui.py

# 服务端
pyinstaller --onefile --console --name SecureChatServer chat_server.py
```

产物分别为 `dist/SecureChat.exe` 和 `dist/SecureChatServer.exe`。

---

## 第八章 团队分工情况

> 请根据实际情况填写。如果是个人项目，保留"个人完成"部分。

本项目由个人独立完成，涵盖以下全部工作：

- 系统架构设计与技术选型
- RSA-OAEP + AES-GCM 混合加密实现
- WebSocket 中继服务端开发
- 桌面 GUI 客户端开发
- 消息协议设计与实现
- 自动化测试编写（57 项）
- 人工验收手册编写
- PyInstaller 打包
- 最终报告撰写
