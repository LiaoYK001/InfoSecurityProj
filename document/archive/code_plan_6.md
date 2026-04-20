# Code Plan 6 执行大纲 Executive Summary

<!-- markdownlint-disable MD047 -->

## 1. 阶段结论

五阶段已经完成，当前仓库状态满足进入六阶段的前置条件。

本次检查结果如下：

- **报告正文**：`document/final_report.md` 已按 8 章骨架填充完整正文，所有章节有实质内容。
- **代码注释**：`rsa_core.py` 补齐了模块级 docstring 和 `RSAService` 类 10 个方法的 docstring。8/8 核心文件注释覆盖达标。
- **截图体系**：`document/screenshots/` 目录已创建，含命名规范和采集说明（实际截图需人工完成）。
- **打包脚本**：`pack_submission.py` 可一键清理临时文件并生成提交用 zip 压缩包（52 文件、31.4 MB）。
- **汇报脚本**：`document/week8_demo_script.md` 补充了演练前检查清单、计时参考和常见问题处理。
- **自动化测试**：57 项测试全部通过，代码无静态错误。

因此，六阶段转入"**自我拓展阶段 — Web 网页端开发**"。

六阶段的核心判断是：

1. 五阶段已将桌面端课设从开发到交付的完整链路收口完毕。
2. 六阶段是课题的自我拓展部分，目标是为现有系统增加一个 Web 网页客户端，类似 Discord 同时提供桌面客户端和网页端。
3. 服务端（`chat_server.py`）采用标准 WebSocket + JSON 协议，且为盲转发模式——这意味着 Web 端只需要在浏览器中实现相同的加密逻辑和协议格式，即可与桌面端互通，**服务端几乎不需要改动**。

---

## 2. 六阶段目标

六阶段的目标是开发一个**浏览器端 Web 客户端**，与现有桌面客户端共用同一个中继服务端，实现跨平台端到端加密聊天。

六阶段完成后，项目应达到以下状态：

1. 用户可以通过浏览器访问 Web 客户端，完成与桌面客户端相同的端到端加密聊天。
2. Web 端与桌面端可以互通聊天：Alice 用桌面端、Bob 用网页端，双方可以正常加密通信。
3. Web 端使用浏览器原生 Web Crypto API 实现 RSA-OAEP + AES-GCM，加密参数与桌面端完全一致。
4. 服务端保持盲转发设计不变，不因 Web 端的加入而降低安全性。
5. Web 端的 UI 提供与桌面端对等的核心功能：密钥管理、联系人列表、聊天区和 Crypto Console。

---

## 3. 六阶段范围

### 3.1 本阶段要完成的内容

- 开发 Web 前端客户端（HTML + CSS + JavaScript）。
- 使用 Web Crypto API 实现与桌面端一致的加密逻辑。
- 为服务端添加静态文件服务能力（或单独使用一个简单 HTTP 服务器）。
- 实现 Web 端与桌面端的跨客户端互通测试。
- 补充 Web 端相关的文档说明。

### 3.2 本阶段明确不做的内容

- 不使用前端框架（React/Vue/Angular）——保持原生 HTML/CSS/JS，降低依赖复杂度。
- 不做用户认证系统（与桌面端一致，仍然使用用户 ID + RSA 公钥的简单身份模型）。
- 不做消息持久化或离线消息。
- 不修改现有加密、协议和服务端的核心逻辑。
- 不破坏桌面端的任何功能——Web 端是增量扩展。

---

## 4. 技术方案

### 4.1 架构总览

```
┌────────────────────┐                    ┌──────────────────────────┐
│  桌面客户端 (Tkinter) │                    │  Web 客户端 (浏览器)       │
│  desktop_chat_gui.py │                    │  web/index.html            │
│  Python              │                    │  HTML + CSS + JS           │
│  cryptography 库     │                    │  Web Crypto API            │
└─────────┬──────────┘                    └───────────┬──────────────┘
          │ WebSocket (JSON)                          │ WebSocket (JSON)
          └────────────────┬──────────────────────────┘
                           │
                    ┌──────┴──────────┐
                    │ 中继服务端       │
                    │ chat_server.py   │
                    │ (盲转发，不改动) │
                    └─────────────────┘
```

### 4.2 Web Crypto API 与 Python cryptography 对齐

Web 端必须使用与桌面端完全一致的加密参数，才能互通：

| 参数           | 桌面端 (Python)                 | Web 端 (JavaScript)                    |
| -------------- | ------------------------------- | -------------------------------------- |
| RSA 算法       | RSA-OAEP, SHA-256               | `RSA-OAEP` + `SHA-256`                 |
| RSA 密钥长度   | 2048 bit                        | 2048 bit                               |
| RSA 公钥格式   | PEM (PKCS#1 / SubjectPublicKey) | SPKI (需要 PEM ↔ SPKI 互转)            |
| AES 算法       | AES-256-GCM                     | `AES-GCM` + 256-bit key                |
| AES Nonce 长度 | 12 byte                         | 12 byte (iv)                           |
| AES 密钥长度   | 256 bit (32 byte)               | 256 bit                                |
| Base64 编码    | Python `base64.b64encode`       | `btoa()` / `Uint8Array` + 手动转换     |
| 公钥指纹       | SHA-256 前 16 位 hex            | `crypto.subtle.digest('SHA-256', ...)` |

**关键互通点**：

1. RSA 公钥在 Python 端序列化为 PEM 格式。Web 端需要将 PEM 解析为 SPKI 格式的 `ArrayBuffer`，再通过 `crypto.subtle.importKey('spki', ...)` 导入。
2. AES-GCM 的 tag（认证标签）在 Python `cryptography` 库中自动附加在密文末尾。Web Crypto API 的 `encrypt()` 也将 tag 附加在密文末尾（默认 128-bit tag）。两端行为一致。
3. `wrapped_key`、`nonce`、`ciphertext` 均使用标准 Base64 编码传输。

### 4.3 文件结构规划

```
web/
├── index.html          # 主页面
├── style.css           # 样式
├── app.js              # 主应用逻辑（UI + WebSocket）
├── crypto.js           # Web Crypto API 封装（对应桌面端 aes_core + rsa_core + message_crypto）
├── protocol.js         # 消息协议（对应桌面端 chat_protocol.py）
└── README.md           # Web 端说明
```

### 4.4 服务端改动评估

**核心结论：服务端不需要改动。**

原因：

- 服务端是盲转发模式，不解析 payload 内容，只看 `type`、`sender_id`、`receiver_id` 字段。
- WebSocket 协议和 JSON 消息格式对于桌面端和 Web 端完全一致。
- Web 端浏览器原生支持 WebSocket，可以直接连接 `ws://host:port`。

可选改动（低优先级）：

- 为方便开发，可在服务端增加一个简易静态文件服务器，通过 HTTP 提供 `web/` 目录下的文件。
- 或者直接使用 `python -m http.server` 单独提供 Web 文件，服务端只负责 WebSocket。

---

## 5. 六阶段开发顺序

### 任务 A：搭建 Web 端项目骨架

目标：创建 `web/` 目录，建立基本的 HTML/CSS/JS 文件结构和 UI 布局。

必须完成：

- 创建 `web/index.html`，包含登录区、密钥区、联系人列表、聊天区和 Crypto Console 五个区域。
- 创建 `web/style.css`，实现类似 Discord 风格的深色主题布局。
- 创建 `web/app.js`，实现基本的 UI 交互逻辑（按钮事件、消息显示等）。
- 创建 `web/protocol.js`，移植 `chat_protocol.py` 的消息构造和解析函数。
- 确认页面可以在浏览器中打开并显示正确的布局。

完成标准：

- `web/index.html` 在浏览器中打开后，UI 布局完整，五个区域可见。
- `web/protocol.js` 可以正确构造和解析 7 种消息类型。

### 任务 B：实现 Web Crypto 加密层

目标：使用 Web Crypto API 实现与桌面端完全一致的 RSA-OAEP + AES-GCM 加密逻辑。

必须完成：

- 创建 `web/crypto.js`，封装以下功能：
  - `generateRSAKeyPair()` — 生成 RSA-2048 密钥对
  - `exportPublicKeyPEM()` — 导出公钥为 PEM 格式字符串
  - `importPublicKeyFromPEM()` — 从 PEM 字符串导入对端公钥
  - `getPublicKeyFingerprint()` — 计算公钥 SHA-256 指纹
  - `encryptMessage()` — 混合加密（AES-GCM + RSA-OAEP 包裹）
  - `decryptMessage()` — 混合解密
- PEM ↔ SPKI/PKCS8 格式互转工具函数。
- 所有加密参数与桌面端一致（RSA-2048 OAEP SHA-256、AES-256-GCM、12-byte nonce）。

完成标准：

- 在浏览器控制台中可以完成一次完整的加密 → 解密往返。
- 生成的 `wrapped_key`、`nonce`、`ciphertext` 格式与桌面端一致（Base64 编码）。

### 任务 C：实现 WebSocket 通信与核心聊天功能

目标：在 `web/app.js` 中实现 WebSocket 连接、消息收发和完整的聊天交互。

必须完成：

- 连接管理：连接、断开、自动重连提示。
- 用户注册：连接后发送 `register` 消息（含公钥）。
- 在线列表：接收 `user_list` 消息，更新联系人面板。
- 公钥交换：选择联系人时自动发送公钥，接收对方公钥并导入。
- 加密发送：输入消息 → 调用 `crypto.js` 加密 → 构造 `chat_message` → WebSocket 发送。
- 解密接收：收到 `chat_message` → 调用 `crypto.js` 解密 → 显示明文。
- Crypto Console：实时显示加解密过程日志（与桌面端风格一致）。

完成标准：

- Web 端可以连接服务端，显示联系人列表。
- 两个 Web 客户端之间可以完成端到端加密聊天。
- Crypto Console 显示完整的加密/解密步骤日志。

### 任务 D：桌面端与 Web 端跨客户端互通测试

目标：验证桌面客户端和 Web 客户端可以互相发送加密消息。

必须完成：

- 测试场景 1：桌面端 (Alice) → Web 端 (Bob) 发送加密消息，Bob 能正确解密。
- 测试场景 2：Web 端 (Bob) → 桌面端 (Alice) 发送加密消息，Alice 能正确解密。
- 测试场景 3：混合场景 — 三人聊天，1 个桌面端 + 2 个 Web 端。
- 验证两端 Crypto Console 日志的加密参数一致（key length、nonce length 等）。
- 记录测试结果。

完成标准：

- 桌面端和 Web 端可以双向加密通信。
- 加密参数完全一致，无兼容性问题。

### 任务 E：Web 端文档与整合

目标：补充 Web 端的文档说明，更新项目整体文档。

必须完成：

- 创建 `web/README.md`，说明 Web 端的启动方式、功能和已知限制。
- 更新项目根目录 `README.md`，增加 Web 端的启动说明。
- 更新 `document/result_note.md`，补充 Web 端跨平台互通的测试结果。
- 如有时间，更新 `document/final_report.md`，增加 Web 端作为自我拓展内容的章节。

完成标准：

- Web 端有独立的使用说明。
- 项目级文档体现了 Web 端的拓展。

---

## 6. 六阶段建议优先级

### 第一优先级：加密层正确性（任务 B）

- 这是互通的基础。如果 Web Crypto API 的加密参数与桌面端不一致，后续所有功能都无法工作。
- 建议先独立在浏览器控制台中测试加密 → 解密往返，再接入 UI。

### 第二优先级：WebSocket 通信与聊天功能（任务 A + C）

- UI 和通信是用户可见的部分，需要在加密层稳定后快速搭建。

### 第三优先级：跨客户端互通（任务 D）

- 这是 Web 端的核心价值。桌面端和 Web 端的互通测试是六阶段的关键验收点。

### 第四优先级：文档整合（任务 E）

- 在功能稳定后补充文档。

---

## 7. 六阶段验收标准

当以下条件全部满足时，六阶段可以结束：

1. Web 端可以在浏览器中打开，UI 布局完整。
2. Web 端可以生成 RSA 密钥对，连接服务端，显示在线用户。
3. 两个 Web 客户端之间可以完成端到端加密聊天。
4. 桌面端和 Web 端可以双向加密通信（跨客户端互通）。
5. Web 端 Crypto Console 显示完整的加解密步骤日志。
6. 服务端未做破坏性改动，桌面端功能不受影响。
7. Web 端有独立的使用说明文档。

---

## 8. 技术风险与应对

| 风险                                | 影响               | 应对方案                                                    |
| ----------------------------------- | ------------------ | ----------------------------------------------------------- |
| PEM ↔ SPKI 格式转换出错             | 公钥无法导入       | 编写专门的 PEM 解析函数，添加单元测试                       |
| AES-GCM tag 位置不一致              | 解密失败           | 两端均使用 128-bit tag 并附加在密文末尾，保持一致           |
| Base64 编码差异（URL-safe vs 标准） | 解密失败           | 统一使用标准 Base64（`+/=`），不使用 URL-safe 变体          |
| 浏览器 CORS 限制                    | WebSocket 连接失败 | WebSocket 不受 CORS 限制，但 HTTP 静态文件需同源或配置 CORS |
| RSA 密钥大小对齐                    | 加密后长度不匹配   | 两端统一使用 2048-bit                                       |

---

## 9. 阶段边界说明

六阶段的重点，是让现有的端到端加密聊天系统**多一个浏览器入口**。

如果六阶段重新转向以下内容，应视为越界：

- 引入前端框架（React/Vue/Angular）或构建工具（Webpack/Vite）。
- 实现用户认证、注册、密码系统。
- 实现群聊、文件传输、消息持久化。
- 大幅重构服务端架构。

Web 端应与桌面端功能对等，不超过桌面端的功能范围。

---

## 10. 最后结论

从当前项目状态看，五阶段已将桌面端课设收口完毕。六阶段是自我拓展阶段。

Web 端开发的可行性很高，原因是：

1. 服务端已经使用 WebSocket 协议，浏览器原生支持。
2. 服务端是盲转发模式，不解析 payload，不需要改动。
3. Web Crypto API 原生支持 RSA-OAEP 和 AES-GCM，与桌面端加密参数可以完全对齐。
4. JSON 消息协议在 JavaScript 中处理起来比 Python 更自然。

最大的技术难点在于 PEM 格式公钥与 Web Crypto API 的 SPKI 格式之间的互转，以及确保 Base64 编码/解码在两端完全一致。只要加密层的互通测试通过，其余部分都是常规 Web 开发。
