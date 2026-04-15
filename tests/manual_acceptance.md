# 手工验收步骤

## 前置条件

1. Python 3.10+
2. 已安装依赖：`pip install -r requirements.txt`

## 步骤 1：启动服务端

```powershell
python chat_server.py
```

预期输出：`[HH:MM:SS] INFO 服务端启动: ws://127.0.0.1:8765`

## 步骤 2：启动客户端 A

```powershell
python desktop_chat_gui.py
```

操作：

1. 点击「生成密钥」。
2. 在用户 ID 输入 `alice`。
3. 点击「连接」。

预期：状态栏显示「已连接」，Crypto Console 显示密钥生成和连接成功日志。

## 步骤 3：启动客户端 B

再开一个终端窗口：

```powershell
python desktop_chat_gui.py
```

操作：

1. 点击「生成密钥」。
2. 在用户 ID 输入 `bob`。
3. 点击「连接」。

预期：

- 两个客户端的在线用户列表中均能看到对方。
- Crypto Console 显示自动导入对方公钥的日志。

## 步骤 4：发送加密消息

在客户端 A 中：
1. 在左侧联系人列表中点击 `bob`。
2. 在输入框输入 `你好，Bob！这是一条加密消息。`
3. 点击「发送」或按回车。

预期（客户端 A）：
- 聊天区显示自己发送的消息。
- Crypto Console 依次显示：
  - 原文和长度
  - AES 会话密钥已生成
  - wrapped_key 已生成
  - 密文已发送

预期（客户端 B）：
- 聊天区自动显示来自 alice 的明文消息。
- Crypto Console 依次显示：
  - 收到密文
  - wrapped_key 长度
  - 解密成功

## 步骤 5：反向测试

在客户端 B 中向 alice 发送消息，验证双向通信正常。

## 步骤 6：验证服务端盲转发

检查服务端终端日志：
- 应只看到 `type=chat_message sender=alice receiver=bob payload_len=xxx`。
- **不**应看到任何明文内容。

## 步骤 7：运行自动化测试

```powershell
python -m unittest discover -s tests -v
```

预期：所有测试通过。

## 验收通过标准

- [ ] 双客户端可连接服务端并互相看到在线状态。
- [ ] 公钥自动交换成功。
- [ ] 消息以密文形式经过服务端。
- [ ] 接收方自动解密并显示明文。
- [ ] Crypto Console 完整记录了加密/解密过程。
- [ ] 服务端日志不含任何明文。
- [ ] 自动化测试全部通过。
