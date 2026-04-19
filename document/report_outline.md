# 课程设计报告骨架

> 本文件为最终报告的章节骨架，按课程任务书要求编排。撰写正文时逐章填充即可。

---

## 第一章 任务分析

- 课程设计任务：端到端加密的即时通讯软件设计与实现
- 核心需求拆解
  - 消息加密算法的选择与实现
  - 密钥交换/分发机制的设计
  - 即时通信软件的基础功能（发送、接收、传输密文、自动解密展示）
- 安全目标：传输链路上只存在密文，服务端不可见明文

## 第二章 相关理论及技术基础

### 2.1 网络通信协议

- WebSocket 协议原理与选型理由（全双工、低延迟）
- JSON 消息协议设计（`chat_protocol.py` 中的 7 种消息类型）

### 2.2 消息加密算法

- AES-GCM 对称加密原理
  - 256-bit 密钥、12-byte Nonce、AEAD 认证加密
  - 为什么选 AES-GCM 而非 AES-CBC（完整性保护、无需额外 HMAC）

### 2.3 密钥交换机制

- RSA-OAEP(SHA-256) 非对称加密原理
  - 公私钥生成、OAEP 填充、分块加密
  - 公钥指纹（SHA-256 前 16 位 hex）用于带外验证
- 混合加密方案：一次性 AES 会话密钥 + RSA 包裹

## 第三章 解决思路与设计

### 3.1 概要设计

- 系统架构图：客户端 A ↔ 中继服务端 ↔ 客户端 B
- 模块划分
  - 加密层：`aes_core.py` / `rsa_core.py` / `message_crypto.py`
  - 协议层：`chat_protocol.py`
  - 网络层：`chat_client.py` / `chat_server.py`
  - 会话层：`session_manager.py`
  - 表现层：`desktop_chat_gui.py`
- 盲转发设计：服务端只负责路由，不解密 payload

### 3.2 详细设计

- 加密链路时序图：明文 → AES-256 密钥生成 → AES-GCM 加密 → RSA-OAEP 包裹会话密钥 → JSON 封装 → WebSocket 发送
- 解密链路时序图：收到密文 → RSA-OAEP 解包会话密钥 → AES-GCM 解密 → 明文展示
- 密钥交换流程：选择联系人 → 自动发送公钥 → 对端导入 → 指纹可核验
- 协议消息格式：`{type, sender_id, receiver_id, timestamp, payload}`
- GUI 线程模型：主线程 Tkinter + 后台线程网络 I/O + Queue 消息桥

## 第四章 实现与测试

### 4.1 开发环境

- Python 3.12, cryptography 46.0.7, websockets 16.0
- IDE: VS Code, 版本管理: Git

### 4.2 关键实现

- AES-GCM 加解密实现（`aes_core.py`）
- RSA-OAEP 密钥管理与加解密（`rsa_core.py`）
- 混合加密封装（`message_crypto.py`）
- WebSocket 中继服务端（`chat_server.py`）
- 桌面 GUI 客户端（`desktop_chat_gui.py`）

### 4.3 测试

- 自动化测试：57 项单元测试 + 集成测试全部通过
  - `test_crypto.py`：加密层测试（15 项）
  - `test_protocol.py`：协议层测试（14 项）
  - `test_protocol_v2.py`：协议增强测试（17 项）
  - `test_integration.py`：端到端集成测试（11 项）
- 人工验收：按 `tests/manual_acceptance.md` 完成双客户端全流程演示

## 第五章 任务结果说明与结果分析

- 功能完成度总结（参见 `document/result_note.md`）
- 安全性分析
  - 传输密文验证（Wireshark 抓包证据）
  - 服务端日志不含明文
  - 会话密钥一次性使用
- 性能与局限性分析

## 第六章 运行截图

> 撰写时插入以下截图：

- [ ] 服务端启动日志
- [ ] 客户端 A 生成密钥并连接
- [ ] 客户端 B 连接后联系人列表自动更新
- [ ] 双方聊天消息 + Crypto Console 加解密日志
- [ ] 服务端日志（不含明文）
- [ ] Wireshark 抓包 — 传输数据为密文

## 第七章 程序使用说明

- 环境安装（`pip install -r requirements.txt`）
- 服务端启动命令与参数
- 客户端启动与 GUI 操作流程
- 打包为可执行文件的方法

## 第八章 团队分工情况

> 参见 `document/team_division.md`
