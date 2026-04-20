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
python -m PyInstaller SecureChat.spec
```

- `--onefile`：打包为单个 exe
- `--windowed`：隐藏控制台窗口（GUI 应用）
- `SecureChat.spec`：已显式收集本地模块和 `websockets` 包，避免运行时报 `ModuleNotFoundError`
- 产物：`dist/SecureChat.exe`

> ⚠️ **请在安装了项目依赖的 Python 环境中执行**。推荐先激活虚拟环境，再运行 `python -m PyInstaller SecureChat.spec`。

### 2. SecureChatServer 服务端（控制台模式）

```bash
python -m PyInstaller SecureChatServer.spec
```

- `--console`：保留控制台窗口（查看服务端日志）
- `SecureChatServer.spec`：已显式收集 `chat_protocol` 和 `websockets`，避免运行时报缺包
- 产物：`dist/SecureChatServer.exe`

### 3. RSA_Encrypt_Decrypt_Tool 独立加解密工具（窗口模式）

```bash
python -m PyInstaller --onefile --windowed --name RSA_Encrypt_Decrypt_Tool InfoSecurWork_GUI.py
```

- 产物：`dist/RSA_Encrypt_Decrypt_Tool.exe`（约 13 MB）

---

## 一键构建全部

在项目根目录执行：

```bash
# 清理旧构建
rmdir /s /q build 2>nul

# 构建三个 exe
python -m PyInstaller SecureChat.spec -y
python -m PyInstaller SecureChatServer.spec -y
python -m PyInstaller --onefile --windowed --name RSA_Encrypt_Decrypt_Tool InfoSecurWork_GUI.py -y

# 清理中间文件
rmdir /s /q build
```

或者直接执行：

```powershell
.\build_exes.ps1
```

如果只想构建聊天相关程序，可执行：

```powershell
.\build_exes.ps1 -Targets client,server
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
python -m PyInstaller SecureChat.spec --upx-dir /path/to/upx
```

### Q: 想添加自定义图标

```bash
python -m PyInstaller SecureChat.spec --icon=myicon.ico
```

### Q: 运行 `SecureChat.exe` 报 `No module named 'websockets'`

说明你打包时没有使用安装了项目依赖的 Python 环境，或者使用了旧的命令。重新激活虚拟环境后执行：

```bash
python -m PyInstaller SecureChat.spec -y
```

如果仍有问题，先删除旧的 `dist/SecureChat.exe` 后再重打包，避免误运行历史产物。

### Q: 以后每个 exe 都要手写 spec 吗

不需要。只有下面两类场景才建议用 spec：

1. 依赖存在动态导入、数据文件或二进制扩展，例如 `websockets` 这类包。
2. 需要把打包方式长期固定下来，避免不同机器上命令漂移。

像 `RSA_Encrypt_Decrypt_Tool` 这种纯入口脚本、依赖简单的程序，继续用普通 `python -m PyInstaller ...` 命令就够了。

如果只是嫌命令麻烦，直接运行 `build_exes.ps1` 即可，不需要手动敲所有命令。

如果脚本提示某个输出文件正在使用，先关闭对应 exe 再重试；这是为了避免 PyInstaller 在覆盖被占用文件时中途失败。
