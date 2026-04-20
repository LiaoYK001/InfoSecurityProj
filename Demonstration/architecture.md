# 系统架构解读

> **项目**：端到端加密即时通讯软件  
> **技术栈**：Python 3.12 + websockets + cryptography | HTML/JS + Web Crypto API  
> **本文档**：面向 PPT 答辩，配套 Mermaid 架构图  
> **高清 PNG 图片**：`Demonstration/png/` 目录下，可直接插入 PPT

### PNG 文件索引

| 图编号 | 文件                              | 用途                      |
| ------ | --------------------------------- | ------------------------- |
| 图 1   | `png/01_layered_architecture.png` | 五层系统架构总览          |
| 图 2   | `png/02_module_dependency.png`    | 模块依赖关系              |
| 图 3   | `png/03_security_topology.png`    | 通信安全拓扑 + 信任边界   |
| 图 4   | `png/04_encrypt_flow.png`         | 消息加密流程（4 步）      |
| 图 5   | `png/05_decrypt_flow.png`         | 消息解密流程（3 步）      |
| 图 6   | `png/06_key_exchange.png`         | 密钥交换时序              |
| 图 7   | `png/07_message_sequence.png`     | 完整消息收发时序          |
| 图 8   | `png/08_file_transfer.png`        | 文件传输架构（分块/整体） |

---

## 一、总体分层架构

系统采用**五层架构**，自上而下为：表现层 → 会话管理层 → 网络通信层 → 协议层 → 密码学层。桌面端（Python/Tkinter）与 Web 端（HTML/JS）共享相同的协议与加密参数，通过同一中继服务端实现跨平台互通。

```mermaid
graph TB
    classDef pres fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#000
    classDef sess fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef net fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef proto fill:#fce4ec,stroke:#c62828,stroke-width:2px,color:#000
    classDef crypto fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000
    classDef ext fill:#eceff1,stroke:#455a64,stroke-width:2px,color:#000

    subgraph L1["表现层 Presentation"]
        direction LR
        GUI["desktop_chat_gui.py\nTkinter 桌面聊天 GUI"]:::pres
        WEB["web/index.html + app.js\n浏览器 Web 客户端"]:::pres
        RSA_GUI["InfoSecurWork_GUI.py\nRSA 独立工具 GUI"]:::pres
    end

    subgraph L2["会话管理层 Session"]
        SM["session_manager.py\n密钥生命周期 · 联系人公钥 · 加解密门面"]:::sess
    end

    subgraph L3["网络通信层 Network"]
        direction LR
        CLIENT["chat_client.py\nWebSocket 客户端\n后台线程 asyncio"]:::net
        SERVER["chat_server.py\nWebSocket 盲中继服务端\n路由转发 · 心跳管理"]:::net
    end

    subgraph L4["协议层 Protocol"]
        direction LR
        PROTO_PY["chat_protocol.py\nJSON 消息信封 · 类型校验"]:::proto
        PROTO_JS["web/protocol.js\n等价 JS 实现"]:::proto
    end

    subgraph L5["密码学层 Crypto"]
        direction LR
        MC["message_crypto.py\n混合加密编排"]:::crypto
        AES["aes_core.py\nAES-256-GCM"]:::crypto
        RSA["rsa_core.py\nRSA-2048 OAEP"]:::crypto
        CRYPTO_JS["web/crypto.js\nWeb Crypto API 等价实现"]:::crypto
    end

    subgraph L6["外部依赖"]
        direction LR
        LIB_PY["cryptography.hazmat\nPython 密码学库"]:::ext
        LIB_WS["websockets\nWebSocket 实现"]:::ext
        LIB_WC["Web Crypto API\n浏览器原生加密"]:::ext
    end

    GUI --> SM
    WEB -.->|"直接调用 JS 模块"| CRYPTO_JS
    RSA_GUI --> RSA

    SM --> CLIENT
    SM --> MC

    CLIENT --> PROTO_PY
    SERVER --> PROTO_PY
    CLIENT <-->|"WebSocket\ntcp:8765"| SERVER

    MC --> AES
    MC --> RSA
    CRYPTO_JS -.-> PROTO_JS

    AES --> LIB_PY
    RSA --> LIB_PY
    CLIENT --> LIB_WS
    SERVER --> LIB_WS
    CRYPTO_JS -.-> LIB_WC
```

### 各层职责

| 层级           | 职责                                                | 核心文件                                                           |
| -------------- | --------------------------------------------------- | ------------------------------------------------------------------ |
| **表现层**     | 用户交互界面、事件处理、消息展示                    | `desktop_chat_gui.py`, `web/`, `InfoSecurWork_GUI.py`              |
| **会话管理层** | 本地密钥对管理、多联系人公钥映射、加解密统一入口    | `session_manager.py`                                               |
| **网络通信层** | WebSocket 连接管理、消息收发、心跳保活              | `chat_client.py`, `chat_server.py`                                 |
| **协议层**     | JSON 消息信封定义、字段校验、类型常量               | `chat_protocol.py`, `web/protocol.js`                              |
| **密码学层**   | AES-GCM 对称加密、RSA-OAEP 非对称加密、混合加密编排 | `message_crypto.py`, `aes_core.py`, `rsa_core.py`, `web/crypto.js` |

---

## 二、模块依赖关系图

展示所有 Python 模块之间的 import 依赖关系，箭头表示"依赖于"。

```mermaid
graph LR
    classDef gui fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#000
    classDef core fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef net fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef crypto fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#000

    DCG["desktop_chat_gui.py\n桌面聊天 GUI"]:::gui
    IGUI["InfoSecurWork_GUI.py\nRSA 工具 GUI"]:::gui

    SM["session_manager.py\n会话管理器"]:::core
    CC["chat_client.py\n网络客户端"]:::net
    CS["chat_server.py\n中继服务端"]:::net
    CP["chat_protocol.py\n协议定义"]:::net

    MC["message_crypto.py\n混合加密"]:::crypto
    AES["aes_core.py\nAES-256-GCM"]:::crypto
    RSA["rsa_core.py\nRSA-2048 OAEP"]:::crypto

    DCG --> CC
    DCG --> SM
    SM --> MC
    SM --> RSA
    MC --> AES
    MC --> RSA
    CC --> CP
    CS --> CP
    IGUI --> RSA
```

---

## 三、通信拓扑图

展示客户端、服务端之间的通信拓扑与安全边界。

```mermaid
graph TB
    classDef client fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef server fill:#fff8e1,stroke:#f57f17,stroke-width:2px,color:#000
    classDef attacker fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#000,stroke-dasharray:5 5

    subgraph TrustZone_A["🔒 Alice 信任域"]
        A_GUI["桌面客户端\nAlice"]:::client
        A_KEY["🔑 Alice 私钥\n(仅本地持有)"]:::client
    end

    subgraph Untrusted["⚠️ 不可信区域"]
        SRV["中继服务端\nchat_server.py\n(盲转发节点)"]:::server
        NET["网络链路\nWebSocket / TCP"]:::server
        ATK["🕵️ 潜在攻击者\n(窃听 / 入侵服务端)"]:::attacker
    end

    subgraph TrustZone_B["🔒 Bob 信任域"]
        B_GUI["桌面/Web 客户端\nBob"]:::client
        B_KEY["🔑 Bob 私钥\n(仅本地持有)"]:::client
    end

    A_GUI -->|"密文消息\nwrapped_key + nonce + ciphertext"| NET
    NET --> SRV
    SRV -->|"原样转发\n不解密 payload"| NET
    NET -->|"密文消息"| B_GUI

    ATK -.->|"❌ 无法解密\n缺少私钥"| SRV
    ATK -.->|"❌ 无法解密\n缺少私钥"| NET

    A_KEY -.->|"解密自己收到的消息"| A_GUI
    B_KEY -.->|"解密自己收到的消息"| B_GUI
```

### 盲转发设计要点

| 设计原则           | 实现方式                                                     |
| ------------------ | ------------------------------------------------------------ |
| **不持有私钥**     | 服务端代码无任何密码学 import                                |
| **不解密 payload** | `_handle_chat_message()` 原样 JSON 转发                      |
| **日志不泄露**     | 仅记录 `type, sender, receiver, payload_len`                 |
| **无持久化**       | 内存中仅维护 `{uid → ws}` 和 `{uid → pub_pem}`，不存聊天记录 |
| **路由依据**       | 仅读取 `msg["receiver_id"]` 决定转发目标                     |

---

## 四、消息加密数据流

### 4.1 发送方加密流程

```mermaid
flowchart LR
    classDef data fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef process fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef output fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000

    PT["📝 明文消息\n'Hello Bob'"]:::data

    GEN["① 生成一次性\nAES-256 密钥\n(32 bytes random)"]:::process
    AES_ENC["② AES-GCM 加密\n明文 → 密文\n+ 12-byte Nonce\n+ 128-bit Tag"]:::process
    RSA_ENC["③ RSA-OAEP 加密\nAES 密钥 → wrapped_key\n用 Bob 公钥加密"]:::process
    B64["④ Base64 编码\n打包 JSON"]:::process

    CIPHER["📦 加密消息\n{wrapped_key,\nnonce,\nciphertext}"]:::output

    PT --> GEN --> AES_ENC --> RSA_ENC --> B64 --> CIPHER
```

### 4.2 接收方解密流程

```mermaid
flowchart LR
    classDef data fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef process fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef output fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000

    CIPHER["📦 收到加密消息\n{wrapped_key,\nnonce,\nciphertext}"]:::data

    RSA_DEC["① RSA-OAEP 解密\nwrapped_key → AES 密钥\n用 Bob 私钥解密"]:::process
    AES_DEC["② AES-GCM 解密\n密文 → 明文\n验证完整性 Tag"]:::process
    SHOW["③ 展示明文\n写入 Crypto Console"]:::process

    PT["📝 明文消息\n'Hello Bob'"]:::output

    CIPHER --> RSA_DEC --> AES_DEC --> SHOW --> PT
```

### 4.3 密钥交换时序图

```mermaid
sequenceDiagram
    participant A as Alice (客户端)
    participant S as Server (盲中继)
    participant B as Bob (客户端)

    Note over A: generate_rsa_key_pair(2048)
    A->>S: register {sender_id: "alice", payload: {public_key: alice_pub_pem}}

    Note over B: generate_rsa_key_pair(2048)
    B->>S: register {sender_id: "bob", payload: {public_key: bob_pub_pem}}

    S->>A: user_list {users: {"alice": alice_pub, "bob": bob_pub}}
    S->>B: user_list {users: {"alice": alice_pub, "bob": bob_pub}}

    Note over A: 自动导入 Bob 公钥<br/>load_public_key_from_pem()
    Note over B: 自动导入 Alice 公钥<br/>load_public_key_from_pem()

    Note over A,B: 🔒 此后双方可互发端到端加密消息
```

---

## 五、完整消息收发时序图

```mermaid
sequenceDiagram
    participant A as Alice
    participant SM_A as SessionManager<br/>(Alice)
    participant C_A as ChatClient<br/>(Alice)
    participant S as Server
    participant C_B as ChatClient<br/>(Bob)
    participant SM_B as SessionManager<br/>(Bob)
    participant B as Bob

    A->>SM_A: send_message("Hello Bob", "bob")
    activate SM_A
    SM_A->>SM_A: ① generate_aes_key(256)
    SM_A->>SM_A: ② aes_core.encrypt_text()
    SM_A->>SM_A: ③ rsa_core.encrypt_bytes()<br/>用 Bob 公钥加密 AES 密钥
    SM_A-->>A: Crypto Console 显示加密日志
    deactivate SM_A

    SM_A->>C_A: send(chat_message)
    C_A->>S: WebSocket: {type: "chat_message",<br/>sender: "alice", receiver: "bob",<br/>payload: {wrapped_key, nonce, ciphertext}}

    Note over S: 盲转发：仅读 receiver_id<br/>不解析 payload

    S->>C_B: WebSocket: 原样转发

    C_B->>SM_B: on_message(chat_message)
    activate SM_B
    SM_B->>SM_B: ① rsa_core.decrypt_bytes()<br/>用 Bob 私钥恢复 AES 密钥
    SM_B->>SM_B: ② aes_core.decrypt_text()<br/>AES-GCM 解密 + 完整性校验
    SM_B-->>B: Crypto Console 显示解密日志
    deactivate SM_B

    B->>B: 聊天界面显示 "Hello Bob"
    C_B->>S: ack {ack_for: msg_timestamp}
    S->>C_A: 转发 ack
```

---

## 六、文件传输架构

```mermaid
flowchart TB
    classDef small fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef big fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000
    classDef common fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000

    FILE["📎 用户选择文件"]:::common
    CHECK{"文件大小\n≤ 5 MB?"}:::common

    subgraph SmallFile["小文件：整体传输"]
        direction TB
        S1["读取完整文件字节"]:::small
        S2["encrypt_file_data()\nAES-GCM 加密 + RSA 包裹密钥"]:::small
        S3["make_file_transfer_message()\n单条消息发送"]:::small
    end

    subgraph BigFile["大文件：分块传输"]
        direction TB
        B1["按 1 MB 切分为 N 块"]:::big
        B2["每块独立 encrypt_file_data()"]:::big
        B3["make_file_chunk_message()\ntransfer_id + chunk_index + total_chunks"]:::big
        B4["顺序发送 N 条消息"]:::big
    end

    RECV_S["接收方：直接解密\n→ 文件字节"]:::common
    RECV_B["接收方：逐块解密\n→ 缓存 → 全部到齐后拼装"]:::common
    SHOW["图片自动预览 🖼️\n其他文件提供保存按钮 💾"]:::common

    FILE --> CHECK
    CHECK -->|"是"| SmallFile
    CHECK -->|"否"| BigFile
    S1 --> S2 --> S3
    B1 --> B2 --> B3 --> B4
    S3 --> RECV_S --> SHOW
    B4 --> RECV_B --> SHOW
```

---

## 七、协议消息类型总览

```mermaid
graph LR
    classDef c2s fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef s2c fill:#fff8e1,stroke:#f57f17,stroke-width:2px,color:#000
    classDef p2p fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000

    subgraph ClientToServer["Client → Server"]
        direction TB
        REG["register\n上线注册+公钥"]:::c2s
        HB["heartbeat\n心跳保活 30s"]:::c2s
    end

    subgraph ServerToClient["Server → Client"]
        direction TB
        UL["user_list\n在线用户+公钥广播"]:::s2c
        ERR["error\n错误通知"]:::s2c
    end

    subgraph PeerToPeer["Client ↔ Client (经 Server 转发)"]
        direction TB
        PK["public_key\n主动发送公钥"]:::p2p
        CM["chat_message\n加密聊天消息"]:::p2p
        FT["file_transfer\n小文件整体传输"]:::p2p
        FC["file_chunk\n大文件分块传输"]:::p2p
        ACK["ack\n送达确认回执"]:::p2p
    end
```

### 统一消息信封

```json
{
  "type": "chat_message",
  "sender_id": "alice",
  "receiver_id": "bob",
  "timestamp": "2026-04-20T12:00:00.000Z",
  "payload": {
    "wrapped_key": "Base64...",
    "nonce": "Base64...",
    "ciphertext": "Base64..."
  }
}
```

---

## 八、桌面端与 Web 端对照

两端使用**完全一致的加密参数**，通过同一中继服务端实现**跨平台互通**。

```mermaid
graph TB
    classDef py fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef js fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#000
    classDef shared fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000

    subgraph Desktop["🖥️ 桌面端 (Python)"]
        direction TB
        D_GUI["desktop_chat_gui.py\nTkinter GUI"]:::py
        D_SM["session_manager.py"]:::py
        D_CC["chat_client.py"]:::py
        D_MC["message_crypto.py"]:::py
        D_AES["aes_core.py"]:::py
        D_RSA["rsa_core.py"]:::py
    end

    subgraph Web["🌐 Web 端 (JavaScript)"]
        direction TB
        W_UI["index.html + app.js\nHTML/CSS/JS GUI"]:::js
        W_CR["crypto.js\nWeb Crypto API"]:::js
        W_PR["protocol.js"]:::js
    end

    subgraph Shared["🔗 共享"]
        SRV["chat_server.py\n中继服务端"]:::shared
        PARAM["统一加密参数\nRSA-2048 OAEP SHA-256\nAES-256-GCM 12B Nonce\nBase64 编码 · SPKI PEM"]:::shared
    end

    D_CC <-->|"WebSocket"| SRV
    W_UI <-->|"WebSocket"| SRV

    D_MC -.->|"相同算法"| PARAM
    W_CR -.->|"相同算法"| PARAM

    Desktop ~~~ Shared ~~~ Web
```

---

## 九、加密参数汇总

| 参数         | 值                   | 说明                             |
| ------------ | -------------------- | -------------------------------- |
| 对称算法     | AES-256-GCM          | AEAD 模式，同时加密 + 完整性校验 |
| 对称密钥长度 | 256 bit (32 bytes)   | 每条消息独立生成                 |
| Nonce 长度   | 12 bytes             | 随机生成，NIST 推荐长度          |
| Auth Tag     | 128 bit              | GCM 完整性标签                   |
| 非对称算法   | RSA-2048 OAEP        | SHA-256 + MGF1-SHA-256           |
| 公钥格式     | SPKI PEM             | 标准 X.509 公钥格式              |
| 公钥指纹     | SHA-256 前 16 hex    | 用于身份确认展示                 |
| 编码         | Base64 (标准)        | 所有密文/密钥/Nonce 统一编码     |
| 会话密钥     | 一次性 (per-message) | 前向隔离：单条泄露不影响其他     |
| 传输协议     | WebSocket (TCP:8765) | 全双工长连接                     |
| 心跳间隔     | 30 秒                | 客户端主动发送                   |
| 超时踢出     | 120 秒               | 服务端定期巡检                   |
| 大文件分块   | 1 MB / chunk         | 超过 5 MB 自动分块               |
