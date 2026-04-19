# 设计决策与原创性说明

本文档记录项目开发过程中的关键技术决策及其理由，用于支撑答辩时"理解并主导了实现"的说明。

---

## 1. 为什么使用 RSA + AES-GCM 混合加密

**决策**：不直接用 RSA 加密全部消息，而是每条消息生成一次性 AES-256 密钥，用 AES-GCM 加密正文，再用 RSA-OAEP 包裹会话密钥。

**理由**：

- RSA 加密有长度限制（1024-bit 密钥最大只能加密约 86 字节），不适合直接加密任意长度的聊天消息。
- AES-GCM 是 AEAD（认证加密）模式，同时提供加密和完整性保护，无需额外 HMAC。
- 一次性会话密钥保证了前向安全性：即使某条消息的会话密钥泄露，也不影响其他消息。
- 这是 TLS、Signal Protocol 等成熟方案的标准做法。

## 2. 为什么服务端采用盲转发

**决策**：中继服务端（`chat_server.py`）只负责用户注册、在线列表广播和消息路由，完全不解密任何消息 payload。

**理由**：

- 端到端加密的核心原则是"只有通信双方能看到明文"，服务端不应持有解密能力。
- 盲转发大幅降低服务端实现复杂度：不需要管理密钥、不需要信任模型。
- 服务端日志只记录消息类型、发送方、接收方和 payload 长度，可以作为"服务端看不到明文"的直接证据。
- 攻击者即使控制了服务端，也无法获取聊天内容。

## 3. 为什么桌面端使用 Crypto Console

**决策**：在 GUI 中专门开辟一个 Crypto Console 面板，实时显示加密和解密的每一步操作日志。

**理由**：

- 课程设计需要"结果说明"和"运行截图"，Crypto Console 让加解密全过程可视化，方便截图和演示。
- 直观展示混合加密链路：密钥生成 → AES-GCM 加密 → RSA-OAEP 包裹 → 发送（共 5 步），接收端反向 4 步。
- 调试字段（`wrapped_key_length`、`nonce_length`、`session_key_bits`）帮助验证加密参数的正确性。
- 答辩时可以对照 Crypto Console 日志逐步讲解加密过程。

## 4. 为什么选择 WebSocket 而非原生 Socket

**决策**：使用 `websockets` 库实现客户端与服务端的通信，而非直接使用 `socket` 模块。

**理由**：

- WebSocket 是全双工协议，天然支持双向实时通信，无需自行实现粘包/拆包。
- `websockets` 库提供异步 API，配合 `asyncio` 实现高效 I/O。
- JSON 消息可以直接通过 WebSocket 帧传输，无需自定义分隔符或长度前缀。
- 未来如果扩展 Web 客户端，WebSocket 是浏览器原生支持的协议。

## 5. 为什么保留 InfoSecurWork_GUI.py

**决策**：项目中保留了 `InfoSecurWork_GUI.py`（RSA 单机加解密工具），但当前课设主程序是 `desktop_chat_gui.py`。

**理由**：

- `InfoSecurWork_GUI.py` 是前 4 周 RSA 加密工具的实现成果，课设要求后 4 周"结合前 4 周成果"。
- 保留它体现了项目的演进过程：从单机 RSA 工具 → 集成到即时通讯系统的 RSA 密钥交换模块。
- `rsa_core.py` 中的 `RSAService` 类是为旧 GUI 提供的门面层，`RSAKeyManager` 则是新系统使用的核心类。
- 两者共存不冲突，旧工具作为附属交付物，新聊天系统作为主交付物。

## 6. 协议设计的统一性

**决策**：所有消息统一使用 `{type, sender_id, receiver_id, timestamp, payload}` 的 JSON 格式。

**理由**：

- 统一格式降低了服务端路由逻辑的复杂度——只需检查 `type` 和 `receiver_id`。
- 7 种消息类型（register, public_key, chat_message, ack, error, heartbeat, user_list）覆盖了即时通讯的核心场景。
- `parse_message()` 函数统一校验格式，`strict_payload` 参数支持灵活解析。
- 这种设计便于后续扩展新消息类型（如文件传输），只需新增 type 常量和构造函数。

## 7. 测试策略

**决策**：采用分层测试（单元测试 → 协议测试 → 集成测试）+ 人工验收手册的策略。

**理由**：

- 加密层的正确性最关键，`test_crypto.py` 覆盖了 AES 和 RSA 的所有边界条件。
- 协议层的解析错误会导致消息丢失，`test_protocol.py` 和 `test_protocol_v2.py` 覆盖了格式校验和异常输入。
- `test_integration.py` 验证了从明文到密文再回明文的完整链路。
- GUI 交互无法完全自动化，因此用 `tests/manual_acceptance.md` 作为可复现的人工验收手册。
