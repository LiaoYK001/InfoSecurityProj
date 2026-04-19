# 实验结果说明

## 1. 运行环境

| 项目         | 版本/说明                      |
| ------------ | ------------------------------ |
| 操作系统     | Windows 11                     |
| Python       | 3.12.12 (conda: infosecur_env) |
| cryptography | 46.0.7                         |
| websockets   | 16.0                           |
| GUI 框架     | Tkinter（Python 内置）         |

## 2. 启动方式

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务端
python chat_server.py --host 127.0.0.1 --port 8765

# 3. 启动客户端（可同时开多个）
python desktop_chat_gui.py
```

## 3. 自动化测试结果

执行命令：

```bash
python -m unittest discover -s tests -v
```

结果：**57 项测试全部通过**，覆盖以下模块：

| 测试文件            | 测试数 | 覆盖范围                               |
| ------------------- | ------ | -------------------------------------- |
| test_crypto.py      | 15     | AES-GCM 加解密、RSA 密钥管理、混合加密 |
| test_protocol.py    | 14     | 消息构造与解析、类型校验               |
| test_protocol_v2.py | 17     | 协议增强场景、边界条件                 |
| test_integration.py | 11     | 端到端加解密、会话管理集成             |

无失败、无跳过。

## 4. 人工演示结果

按 `tests/manual_acceptance.md` 完成的双客户端全流程演示，验证结果：

1. **服务端启动**：日志输出 `服务端启动: ws://127.0.0.1:8765`，后续日志只显示消息类型和 payload 长度，**不含任何聊天明文**。
2. **密钥生成与连接**：两个客户端分别生成 RSA-2048 密钥对并连接服务端，Crypto Console 显示密钥指纹。
3. **自动公钥交换**：选择联系人后自动交换公钥，Crypto Console 显示 `[密钥] 已导入 xxx 的公钥`。
4. **加密聊天**：
   - 发送方 Crypto Console 依次显示：明文 → AES-256 密钥生成 → AES-GCM 加密 → RSA-OAEP 包裹会话密钥 → 发送密文
   - 接收方 Crypto Console 依次显示：收到密文 → RSA-OAEP 解包会话密钥 → AES-GCM 解密 → 还原明文
   - 聊天区自动显示解密后的明文
5. **断连处理**：一方断开后，另一方联系人列表自动更新，连接状态正确切换。

## 5. 异常场景验证

| 场景                   | 预期行为               | 实际结果 |
| ---------------------- | ---------------------- | -------- |
| 未生成密钥就发消息     | 提示需要先生成密钥     | 符合预期 |
| 发送给已下线用户       | 提示对方不在线         | 符合预期 |
| 服务端关闭后客户端操作 | 客户端检测到断连并提示 | 符合预期 |

## 6. 抓包验证

使用 Wireshark 过滤 `tcp.port == 8765`，捕获到的 WebSocket 帧 payload 为 JSON 格式，其中 `wrapped_key`、`nonce`、`ciphertext` 字段均为 Base64 编码的密文，**不含任何可识别的聊天明文**。

## 7. 打包验证

| 产物                        | 打包命令                                                                 | 验证结果       |
| --------------------------- | ------------------------------------------------------------------------ | -------------- |
| `dist/SecureChat.exe`       | `pyinstaller --onefile --windowed --name SecureChat desktop_chat_gui.py` | 双击可启动 GUI |
| `dist/SecureChatServer.exe` | `pyinstaller --onefile --console --name SecureChatServer chat_server.py` | 控制台可运行   |

## 8. Web 端跨平台互通测试

### 8.1 测试环境

Web 端使用浏览器原生 HTML/CSS/JS + Web Crypto API，无需任何前端框架。

启动方式：

```bash
cd web
python -m http.server 8080
# 浏览器访问 http://localhost:8080
```

### 8.2 Web↔Web 互通

| 测试场景            | 结果    | 说明                                                    |
| ------------------- | ------- | ------------------------------------------------------- |
| WebUser1 → WebUser2 | ✅ 通过 | 加密消息正确发送和解密，Crypto Console 日志完整         |
| WebUser2 → WebUser1 | ✅ 通过 | 双向通信正常，加密参数一致                              |
| 双方 Crypto Console | ✅ 一致 | wrapped_key=344 chars, nonce=16 chars, AES-GCM 解密成功 |

### 8.3 加密参数验证

Web 端与桌面端使用完全一致的加密参数：

| 参数         | Web 端 (Web Crypto API) | 桌面端 (Python cryptography) |
| ------------ | ----------------------- | ---------------------------- |
| RSA 算法     | RSA-OAEP, SHA-256       | RSA-OAEP, SHA-256            |
| RSA 密钥长度 | 2048 bit                | 2048 bit                     |
| AES 算法     | AES-GCM, 256-bit        | AES-GCM, 256-bit             |
| Nonce 长度   | 12 bytes                | 12 bytes                     |
| Auth Tag     | 128-bit                 | 128-bit                      |
| 公钥格式     | SPKI PEM                | SPKI PEM                     |
| Base64 编码  | 标准 Base64             | 标准 Base64                  |

### 8.4 服务端兼容性

服务端未做任何修改。由于服务端采用盲转发模式，只读取消息信封中的 `type`、`sender_id`、`receiver_id` 字段，不解析 payload 内容，因此 Web 端和桌面端的消息可以被服务端透明转发。

## 9. 结论

本系统成功实现了端到端加密即时通讯的核心功能：

- 消息在传输链路上全程为密文
- 服务端作为盲转发节点，无法获取聊天内容
- 每条消息使用独立的一次性 AES-256 会话密钥
- 自动化测试和人工验收均验证通过
- Web 端与桌面端使用相同加密参数，可跨平台互通
