# 端到端加密即时通讯系统

基于 RSA-OAEP + AES-GCM 混合加密的桌面即时通讯系统，课程设计项目。

## 项目简介

本项目实现了一个端到端加密的即时通讯系统，核心特性：

- **混合加密**：RSA-OAEP(SHA-256) 交换一次性 AES-256 会话密钥，AES-GCM 加密消息正文
- **盲转发服务端**：中继服务器只转发密文，不解密任何 payload，服务端日志不含明文
- **桌面 GUI 客户端**：Tkinter 界面，含联系人列表、聊天区、Crypto Console 实时加解密日志
- **自动密钥交换**：选择联系人时自动交换公钥，无需手动操作
- **指纹验证**：显示本地和对端公钥 SHA-256 指纹，支持带外核验

## 项目结构

```
├── chat_server.py          # WebSocket 中继服务端
├── desktop_chat_gui.py     # 桌面聊天客户端（主程序入口）
├── chat_client.py          # 客户端网络层
├── chat_protocol.py        # 消息协议（JSON 序列化）
├── session_manager.py      # 密钥与会话状态管理
├── message_crypto.py       # 混合加密（RSA + AES-GCM）
├── aes_core.py             # AES-GCM 对称加密
├── rsa_core.py             # RSA 密钥管理与加解密
├── InfoSecurWork_GUI.py    # 旧版 RSA 单机加解密工具（历史保留）
├── requirements.txt        # pip 依赖清单
├── pyproject.toml          # uv 项目配置
├── tests/                  # 自动化测试 + 人工验收手册
└── document/               # 课程文档与验收记录
```

## 环境要求

| 项目     | 要求                     |
| -------- | ------------------------ |
| Python   | ≥ 3.10                   |
| 操作系统 | Windows / macOS / Linux  |
| 核心依赖 | cryptography, websockets |

## 快速开始

### 1. 安装依赖

**方式一：pip（推荐）**

```bash
pip install -r requirements.txt
```

**方式二：uv**

```bash
uv sync
```

> 详细的 uv 用法参见 `document/uv_usage.md`。

### 2. 运行自动化测试

```bash
python -m unittest discover -s tests -v
```

预期结果：57 项测试全部通过。

### 3. 启动服务端

打开一个终端：

```bash
python chat_server.py --host 127.0.0.1 --port 8765
```

可选参数：

| 参数        | 默认值      | 说明             |
| ----------- | ----------- | ---------------- |
| `--host`    | `127.0.0.1` | 监听地址         |
| `--port`    | `8765`      | 监听端口         |
| `--timeout` | `120`       | 不活跃超时（秒） |

### 4. 启动客户端

打开另一个终端：

```bash
python desktop_chat_gui.py
```

GUI 操作步骤：

1. 点击「生成密钥」生成 RSA-2048 密钥对
2. 输入用户 ID（如 `alice`），点击「连接」
3. 左侧联系人列表选择在线用户即可开始聊天
4. Crypto Console 面板实时显示加解密过程

> 完整的双客户端演示步骤参见 `tests/manual_acceptance.md`。

## 打包为可执行文件

### 安装 PyInstaller

```bash
pip install pyinstaller
```

### 打包聊天客户端

```bash
pyinstaller --onefile --windowed --name SecureChat desktop_chat_gui.py
```

产物位于 `dist/SecureChat.exe`。

### 打包服务端

```bash
pyinstaller --onefile --console --name SecureChatServer chat_server.py
```

产物位于 `dist/SecureChatServer.exe`。

> **注意**：`dist/RSA_Encrypt_Decrypt_Tool.exe` 是前期 RSA 单机工具的历史产物，不是当前课设主交付程序。

## 常见问题

**Q: 测试报 `ModuleNotFoundError: No module named 'websockets'`**

A: 执行 `pip install -r requirements.txt` 安装全部依赖。

**Q: 连接服务端失败**

A: 确认服务端已启动，且客户端地址栏与服务端 `--host`/`--port` 一致。默认地址为 `ws://127.0.0.1:8765`。

**Q: 消息发送后对方看不到**

A: 确认双方均已生成密钥并成功连接。选中联系人后系统会自动交换公钥，Crypto Console 会显示公钥交换日志。

## 许可证

本项目使用 MIT 许可证，详见 [LICENSE](LICENSE)。
