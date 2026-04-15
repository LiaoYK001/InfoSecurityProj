# Code Plan 1

## 1. 目标

本文件只服务于代码实现，不包含报告、汇报、提交物、截图整理等人类文档工作。

目标是完成 P0 最低合规版代码实现：

1. 使用 Python。
2. 使用 AES-GCM 加密聊天消息正文。
3. 使用 RSA-OAEP(SHA-256) 交换 AES 会话密钥。
4. 有一个服务端和两个桌面客户端。
5. 客户端 A 发送的是密文消息包。
6. 服务端只转发，不解密。
7. 客户端 B 自动解密并显示明文。
8. 核心代码具有充分注释和 docstring。
9. 有最小可运行测试和最小手工验证路径。
10. 使用uv管理依赖，提供 requirements.txt

---

## 2. 范围

### 2.1 本轮只做这些

- 改造 rsa_core.py。
- 新增 aes_core.py。
- 新增 message_crypto.py。
- 新增 chat_protocol.py。
- 新增 chat_server.py。
- 新增 chat_client.py。
- 新增 session_manager.py。
- 新增 desktop_chat_gui.py。
- 新增 tests/test_crypto.py。
- 新增 tests/test_protocol.py。
- 新增 tests/manual_acceptance.md。
- 如当前仓库缺失依赖声明，可新增 requirements.txt。

### 2.2 本轮明确不做这些

- Web 客户端。
- 文件传输。
- Wireshark 抓包材料。
- exe 打包。
- 报告、PPT、提交材料。
- 群聊、历史记录、用户系统、云端消息存储。

说明：

- InfoSecurWork_GUI.py 保持为现有 RSA 单机演示工具，不将其直接改造成聊天主程序。
- 聊天主程序使用 desktop_chat_gui.py 独立实现。

---

## 3. 固定技术决策

本轮实现不再摇摆，直接按下面的具体方案写代码。

### 3.1 运行时和依赖

- Python 版本：3.10 及以上。
- 已有依赖：cryptography。
- 新增网络依赖：websockets。
- 测试框架：unittest，避免引入 pytest。
- GUI：tkinter。
- 并发模型：GUI 主线程 + 网络后台线程 + 线程安全队列。

### 3.2 网络方案

- 服务端使用 websockets 库实现 asyncio WebSocket 中继。
- 客户端网络层也使用 websockets。
- GUI 不直接接触 asyncio event loop。
- chat_client.py 在后台线程内运行自己的 asyncio loop。
- GUI 通过 queue.Queue 轮询网络事件。

### 3.3 加密方案

- RSA 仅用于：
  - 本地密钥对管理。
  - 使用对方公钥加密 AES 会话密钥。
  - 使用本地私钥解密 AES 会话密钥。
- AES-GCM 用于：
  - 聊天消息正文加密。
  - 完整性校验。
- 不允许用 RSA 直接作为聊天正文主加密路径。

### 3.4 底线聊天流程

1. 双方各自拥有本地 RSA 密钥对。
2. 客户端连接服务端后发送 register 消息，附带 public_key。
3. 发送方已知接收方公钥。
4. 发送方生成一次性 AES 会话密钥。
5. 发送方用 AES-GCM 加密明文。
6. 发送方用接收方 RSA 公钥加密 AES 会话密钥。
7. 发送方把 wrapped_key、nonce、ciphertext 打包发送。
8. 服务端盲转发。
9. 接收方用本地 RSA 私钥解密 wrapped_key。
10. 接收方用 AES-GCM 解密正文并显示。

---

## 4. 目标文件结构

```text
InfoSecurityProj/
├─ rsa_core.py
├─ InfoSecurWork_GUI.py
├─ aes_core.py
├─ message_crypto.py
├─ chat_protocol.py
├─ chat_server.py
├─ chat_client.py
├─ session_manager.py
├─ desktop_chat_gui.py
├─ requirements.txt
└─ tests/
   ├─ test_crypto.py
   ├─ test_protocol.py
   └─ manual_acceptance.md
```

如果 requirements.txt 当前不存在，则本轮一并创建。

---

## 5. 文件级接口约定

这一节直接给 Code Agent 用，尽量减少实现时重新设计接口。

## 5.1 rsa_core.py

目标：最小修改，保留现有能力，补足聊天所需辅助函数。

保留：

- RSAKeyManager
- RSAFileCipher
- RSAService
- 会话密钥加解密相关函数

新增或补强：

- `get_public_key_fingerprint(public_key: rsa.RSAPublicKey) -> str`
- `RSAKeyManager.get_local_public_key_fingerprint() -> str`
- `RSAKeyManager.get_peer_public_key_fingerprint() -> str | None`

必须满足：

- 所有对外方法补全 docstring。
- 注释明确说明：长文本 RSA 加密仅保留为教学演示。

## 5.2 aes_core.py

目标：提供稳定、最小、可测试的 AES-GCM 接口。

建议公开接口：

- `generate_aes_key(key_size_bits: int = 256) -> bytes`
- `encrypt_text(plaintext: str, key: bytes) -> dict[str, str]`
- `decrypt_text(cipher_payload: dict[str, str], key: bytes) -> str`

输出字典固定字段：

- `nonce`
- `ciphertext`

要求：

- 输入输出统一 Base64 字符串。
- 明确抛出空消息、无效 key、篡改密文的异常。

## 5.3 message_crypto.py

目标：封装混合加密主链路。

建议公开接口：

- `encrypt_chat_message(plaintext: str, peer_public_key, sender_key_manager) -> dict[str, object]`
- `decrypt_chat_message(message_payload: dict[str, object], local_private_key) -> dict[str, object]`

发送输出结构建议：

```json
{
  "wrapped_key": "base64_wrapped_key",
  "nonce": "base64_nonce",
  "ciphertext": "base64_ciphertext",
  "debug": {
    "plaintext_length": 0,
    "ciphertext_length": 0,
    "peer_key_fingerprint": "..."
  }
}
```

解密输出结构建议：

```json
{
  "plaintext": "hello",
  "debug": {
    "plaintext_length": 5,
    "ciphertext_length": 128
  }
}
```

## 5.4 chat_protocol.py

目标：定义所有网络消息结构。

消息类型常量：

- `register`
- `public_key`
- `chat_message`
- `ack`
- `error`
- `heartbeat`

建议公开接口：

- `make_register_message(sender_id: str, public_key: str) -> str`
- `make_public_key_message(sender_id: str, receiver_id: str, public_key: str) -> str`
- `make_chat_message(sender_id: str, receiver_id: str, payload: dict[str, object]) -> str`
- `make_ack_message(sender_id: str, receiver_id: str, ack_for: str) -> str`
- `make_error_message(message: str, sender_id: str | None = None) -> str`
- `make_heartbeat_message(sender_id: str) -> str`
- `parse_message(raw_message: str) -> dict[str, object]`

统一字段：

- `type`
- `sender_id`
- `receiver_id`
- `timestamp`
- `payload`

## 5.5 chat_server.py

目标：实现最小可运行的盲转发服务端。

建议实现一个类：

- `ChatRelayServer`

建议最少包含：

- `clients: dict[str, WebSocketServerProtocol]`
- `public_keys: dict[str, str]`

建议方法：

- `start(host: str = "127.0.0.1", port: int = 8765)`
- `handle_connection(websocket)`
- `handle_register(message, websocket)`
- `handle_chat_message(message)`
- `handle_public_key_message(message)`
- `handle_heartbeat(message)`
- `safe_send(receiver_id: str, raw_message: str)`
- `cleanup_disconnected_client(user_id: str)`

要求：

- 日志不打印明文 payload。
- 只打印 type、sender_id、receiver_id、payload length。

## 5.6 chat_client.py

目标：提供 GUI 可调用的同步外观接口，内部隐藏异步网络实现。

建议实现一个类：

- `ChatClient`

建议公开接口：

- `connect(server_url: str, user_id: str, public_key: str) -> None`
- `disconnect() -> None`
- `send_chat_message(receiver_id: str, payload: dict[str, object]) -> None`
- `send_public_key(receiver_id: str, public_key: str) -> None`
- `poll_event(timeout: float = 0.0) -> dict[str, object] | None`

内部实现建议：

- 后台线程启动 asyncio event loop。
- 后台线程接收消息后写入 event_queue。
- GUI 使用 `after()` 定时轮询 `poll_event()`。

事件结构建议：

- `{"event": "connected"}`
- `{"event": "disconnected"}`
- `{"event": "chat_message", "data": {...}}`
- `{"event": "error", "message": "..."}`

## 5.7 session_manager.py

目标：统一包装密钥状态和聊天加解密行为。

建议实现一个类：

- `SessionManager`

建议公开接口：

- `generate_local_keys(key_size: int) -> None`
- `load_local_private_key(file_path: str) -> None`
- `export_local_public_key() -> str`
- `set_peer_public_key(peer_id: str, public_key_pem: str) -> None`
- `get_peer_public_key(peer_id: str) -> str | None`
- `get_local_fingerprint() -> str`
- `get_peer_fingerprint(peer_id: str) -> str | None`
- `encrypt_for_peer(peer_id: str, plaintext: str) -> dict[str, object]`
- `decrypt_from_message(message_payload: dict[str, object]) -> dict[str, object]`

## 5.8 desktop_chat_gui.py

目标：形成可直接演示的桌面聊天主程序。

建议实现主类：

- `DesktopChatApp(tk.Tk)`

界面区块：

- 登录区
- 密钥区
- 联系人区
- 聊天区
- 状态区
- Crypto Console 区

最小控件集合：

- 服务器地址输入框
- 用户 ID 输入框
- 连接按钮
- 生成密钥按钮
- 加载私钥按钮
- 导出公钥按钮
- 导入对方公钥按钮
- 联系人 ID 输入框
- 消息列表文本区
- 消息输入框
- 发送按钮
- 状态标签
- Crypto Console 滚动日志框

必须实现的 GUI 方法：

- `_build_layout()`
- `_connect_to_server()`
- `_disconnect_from_server()`
- `_generate_keys()`
- `_load_local_key()`
- `_export_public_key()`
- `_import_peer_key()`
- `_send_message()`
- `_append_chat_message(role: str, text: str)`
- `_append_crypto_log(text: str)`
- `_poll_network_events()`
- `_handle_network_event(event: dict[str, object])`

要求：

- 收到网络事件后自动解密。
- GUI 主线程内更新所有 tkinter 控件。
- Crypto Console 至少记录：
  - 原文
  - AES 会话密钥已生成
  - wrapped_key 已生成
  - 密文已发送
  - 收到密文
  - 解密成功

---

## 6. 线程与事件模型

这是实现时最容易出错的点，固定如下。

### 6.1 原则

- tkinter 只能在主线程更新。
- 网络接收循环不能阻塞 tkinter 主线程。
- 网络线程与 GUI 线程之间只通过 queue 传递事件。

### 6.2 数据流

1. GUI 调用 chat_client.connect()。
2. chat_client 在后台线程建立 WebSocket 连接。
3. 服务端消息到达后写入 event_queue。
4. GUI 用 `after(100, _poll_network_events)` 轮询队列。
5. GUI 收到 `chat_message` 事件后调用 session_manager 解密。
6. GUI 更新消息区和 Crypto Console。

### 6.3 不允许的实现

- 不允许在后台线程直接操作 tkinter 组件。
- 不允许让 GUI 直接调用 asyncio 事件循环。
- 不允许让服务端或客户端日志打印明文消息。

---

## 7. 分阶段实施计划

Code Agent 需要按阶段推进，每一阶段结束都要形成可运行检查点。

## 阶段 1：密码模块闭环

改动范围：

- rsa_core.py
- aes_core.py
- message_crypto.py

目标：

- 能完成“明文 -> AES-GCM -> wrapped_key -> 解密还原”的完整本地闭环。

检查点：

- 新增或运行 test_crypto.py。
- 先不涉及网络和 GUI。

完成条件：

- 单元测试通过。

## 阶段 2：协议和服务端

改动范围：

- chat_protocol.py
- chat_server.py

目标：

- 服务端可以接收 register 和 chat_message，并转发给目标用户。

检查点：

- 可以手工构造 JSON 消息并验证服务端转发。
- 运行 test_protocol.py。

完成条件：

- 两个逻辑客户端注册后可被服务端识别。

## 阶段 3：客户端网络层和会话层

改动范围：

- chat_client.py
- session_manager.py

目标：

- 客户端能连接服务端，发送密文消息，接收消息并解密。

检查点：

- 暂时可用简单脚本而不是 GUI 验证。

完成条件：

- 在非 GUI 环境下跑通双端消息收发。

## 阶段 4：桌面聊天 GUI

改动范围：

- desktop_chat_gui.py

目标：

- 形成最终的最低合规版演示程序。

检查点：

- 双窗口连接到同一服务端。
- A 输入消息。
- B 自动显示解密结果。

完成条件：

- GUI 全链路跑通。

## 阶段 5：最小测试和手工验收文档

改动范围：

- tests/test_crypto.py
- tests/test_protocol.py
- tests/manual_acceptance.md

目标：

- 确保项目可重复运行与验收。

完成条件：

- 自动化测试可运行。
- 手工验收步骤清晰。

---

## 8. 验收命令建议

如果当前仓库没有统一命令入口，按下面方式作为最小运行标准。

### 8.1 依赖安装

```powershell
pip install -r requirements.txt
```

requirements.txt 最少包含：

- cryptography
- websockets

### 8.2 启动服务端

```powershell
python chat_server.py
```

### 8.3 启动桌面客户端

```powershell
python desktop_chat_gui.py
```

### 8.4 运行测试

```powershell
python -m unittest discover -s tests
```

---

## 9. 注释执行规则

本轮实现必须把注释放在代码阶段完成，不能留到最后补。

### 9.1 每个文件最低要求

- 文件顶部写模块说明。
- public class / function 必须有 docstring。
- 复杂逻辑前要有解释性注释。

### 9.2 特别要注释的部分

- AES-GCM 为什么用于正文加密。
- RSA 为什么只用于会话密钥交换。
- 服务端为什么不能解密。
- chat_client 的后台线程与 GUI 轮询关系。
- Crypto Console 每条日志对应的实际加解密步骤。

---

## 10. Done 定义

只有满足下面全部条件，Code Agent 才能认为 P0 代码实现完成。

1. rsa_core.py 支持会话密钥交换和公钥指纹。
2. aes_core.py 可独立完成加解密。
3. message_crypto.py 可独立完成混合加密闭环。
4. chat_protocol.py 可稳定序列化、反序列化消息。
5. chat_server.py 可注册用户并盲转发消息。
6. chat_client.py 可在后台线程中稳定收发消息。
7. session_manager.py 可统一完成加解密入口。
8. desktop_chat_gui.py 可完成双客户端文本聊天演示。
9. test_crypto.py 和 test_protocol.py 可运行通过。
10. 代码具备足够注释，且没有把报告类内容混进代码实现任务。

---

## 11. 后续计划边界

只有在 Code Plan 1 全部完成后，才允许进入下一轮代码计划：

- Web 端客户端。
- 文件传输。
- 打包。
- 抓包验证辅助代码。

当前 Code Agent 不要提前实现这些增强项。