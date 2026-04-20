# Windows EXE 打包与分发指南

## 前置条件

| 项目        | 要求                             |
| ----------- | -------------------------------- |
| Python      | 3.10+（推荐 3.12）               |
| PyInstaller | 6.x                              |
| 系统        | Windows 10/11                    |
| 依赖        | cryptography, websockets, Pillow |

```bash
pip install pyinstaller
```

---

## 打包命令

### 1. SecureChat 桌面客户端（窗口模式）

```bash
pyinstaller --onefile --windowed --name SecureChat \
  --hidden-import chat_client \
  --hidden-import chat_protocol \
  --hidden-import session_manager \
  --hidden-import message_crypto \
  --hidden-import rsa_core \
  --hidden-import aes_core \
  desktop_chat_gui.py
```

- `--onefile`：打包为单个 exe
- `--windowed`：隐藏控制台窗口（GUI 应用）
- `--hidden-import`：显式包含项目本地模块（PyInstaller 静态分析可能遗漏这些动态导入）
- 产物：`dist/SecureChat.exe`（约 170 MB）

> ⚠️ **必须加 `--hidden-import`**。不加的话 exe 只有约 14 MB，运行时报 `ModuleNotFoundError: No module named 'chat_client'`。

### 2. SecureChatServer 服务端（控制台模式）

```bash
pyinstaller --onefile --console --name SecureChatServer \
  --hidden-import chat_protocol \
  chat_server.py
```

- `--console`：保留控制台窗口（查看服务端日志）
- 产物：`dist/SecureChatServer.exe`（约 10 MB）

### 3. RSA_Encrypt_Decrypt_Tool 独立加解密工具（窗口模式）

```bash
pyinstaller --onefile --windowed --name RSA_Encrypt_Decrypt_Tool InfoSecurWork_GUI.py
```

- 产物：`dist/RSA_Encrypt_Decrypt_Tool.exe`（约 13 MB）

---

## 一键构建全部

在项目根目录执行：

```bash
# 清理旧构建
rmdir /s /q build 2>nul
del *.spec 2>nul

# 构建三个 exe
pyinstaller --onefile --windowed --name SecureChat --hidden-import chat_client --hidden-import chat_protocol --hidden-import session_manager --hidden-import message_crypto --hidden-import rsa_core --hidden-import aes_core desktop_chat_gui.py -y
pyinstaller --onefile --console --name SecureChatServer --hidden-import chat_protocol chat_server.py -y
pyinstaller --onefile --windowed --name RSA_Encrypt_Decrypt_Tool InfoSecurWork_GUI.py -y

# 清理中间文件
rmdir /s /q build
del *.spec
```

产物全部在 `dist/` 目录下。

---

## dist/ 文件清单

| 文件                           | 大小    | 用途                       |
| ------------------------------ | ------- | -------------------------- |
| `SecureChat.exe`               | ~170 MB | 桌面聊天客户端（双击运行） |
| `SecureChatServer.exe`         | ~10 MB  | WebSocket 中继服务端       |
| `RSA_Encrypt_Decrypt_Tool.exe` | ~13 MB  | 独立 RSA 加解密演示工具    |

---

## 使用方式

### 服务端

```bash
# 命令行启动（默认 127.0.0.1:8765）
SecureChatServer.exe

# 指定监听地址和端口
SecureChatServer.exe --host 0.0.0.0 --port 8765

# 指定不活跃超时（秒）
SecureChatServer.exe --host 0.0.0.0 --port 8765 --timeout 300
```

### 客户端

双击 `SecureChat.exe` 即可启动，在界面中填写服务器地址和用户名后连接。

### RSA 工具

双击 `RSA_Encrypt_Decrypt_Tool.exe` 即可启动，用于独立的 RSA 密钥生成、加密、解密演示。

---

## 分发给他人

只需将 `dist/` 目录下的 exe 文件拷贝给对方即可，**无需安装 Python 或任何依赖**。

### 最小分发包

```
SecureChat-dist/
├── SecureChat.exe           # 客户端
├── SecureChatServer.exe     # 服务端（仅需部署方携带）
└── README.txt               # 简单使用说明
```

### 注意事项

1. **Windows Defender / 杀毒软件**：PyInstaller 打包的 exe 可能触发误报，需要在杀毒软件中添加信任或临时关闭实时防护。
2. **首次启动较慢**：单文件模式会先解压到临时目录再运行，首次启动需等待几秒。
3. **Web 端不需要 exe**：Web UI 通过浏览器访问服务器即可使用，参见 `ubuntu_deploy_guide.md`。
4. **exe 文件较大**：因为打包了完整的 Python 运行时和 cryptography 库（含 OpenSSL）。

---

## 常见问题

### Q: 双击 exe 后闪退 / 没有反应

先从命令行运行查看错误信息：

```bash
cd dist
SecureChat.exe
```

### Q: 打包后 exe 无法连接服务器

确认服务端已启动，且客户端中填写的地址和端口正确。如果是远程服务器，确认防火墙已放行端口。

### Q: 如何减小 exe 体积

```bash
# 使用 UPX 压缩（需先安装 UPX 并加入 PATH）
pyinstaller --onefile --windowed --name SecureChat desktop_chat_gui.py --upx-dir /path/to/upx
```

### Q: 想添加自定义图标

```bash
pyinstaller --onefile --windowed --name SecureChat --icon=myicon.ico desktop_chat_gui.py
```
