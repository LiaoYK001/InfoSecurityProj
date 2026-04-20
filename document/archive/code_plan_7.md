# Code Plan 7 执行大纲 Executive Summary

<!-- markdownlint-disable MD047 -->

## 1. 阶段结论

六阶段已经完成，当前仓库状态满足进入七阶段（最终收尾）的前置条件。

本次检查结果如下：

- **Web 端骨架**：`web/` 目录已建立，包含 `index.html`、`style.css`、`app.js`、`crypto.js`、`protocol.js` 五个文件，UI 为 Discord 风格深色主题。
- **加密互通**：Web Crypto API (RSA-OAEP SHA-256 + AES-256-GCM) 与桌面端 Python `cryptography` 库使用完全一致的加密参数，已通过双向加密聊天验证。
- **Web↔Web 通信**：两个浏览器标签页（WebUser1 / WebUser2）可以在中继服务端上正确注册、交换公钥、发送和接收加密消息。Crypto Console 日志完整（wrapped_key=344 chars, nonce=16 chars, 解密成功）。
- **服务端零改动**：`chat_server.py` 未做任何修改，盲转发模式对 Web 端完全透明。
- **文档更新**：`web/README.md` 已创建；项目 `README.md` 已增加 Web 端说明和启动步骤；`document/result_note.md` 已补充 Web 端互通测试结果。
- **桌面端回归**：57 项自动化测试全部通过，桌面端功能未受任何影响。

因此，七阶段转入"**最终收尾与交付阶段**"——这是本课题任务的最后一个阶段。

七阶段的核心判断是：

1. 六阶段解决了"项目能不能做到跨平台（桌面+Web）端到端加密聊天"的问题。
2. 七阶段要解决"项目能不能从代码仓库状态变成一个正式的课程设计提交物"的问题。
3. 七阶段不再有任何新功能开发，所有工作都围绕**最终报告撰写、截图采集、提交包整理和验收检查**。

---

## 2. 七阶段目标

七阶段的唯一主目标：把项目从"代码仓库状态"收敛为一份**可以直接提交给老师的完整课程设计作品**。

七阶段完成后，应达到以下状态：

1. 最终报告已按 8 章结构撰写完毕，含运行截图、抓包截图和程序使用说明。
2. 所有截图已实际采集并放入 `document/screenshots/` 目录。
3. 压缩包已按"第X组+题目"命名规范打包，内含源码、报告、可运行程序和实验说明。
4. `document/submission_checklist.md` 所有条目已勾选完毕。
5. 发送至提交邮箱 `xiongf@bjtu.edu.cn`。

---

## 3. 七阶段范围

### 3.1 本阶段要完成的内容

- 采集全部运行截图（GUI、服务端日志、Wireshark 抓包、Web 端）。
- 将 `document/final_report.md` 转换为正式的 Word/PDF 报告，补充截图和格式调整。
- 更新提交包（运行 `pack_submission.py` 或手动整理）。
- 逐条勾选 `document/submission_checklist.md`。
- 完成最终提交。

### 3.2 本阶段明确不做的内容

- 不开发任何新功能。
- 不重构代码。
- 不添加新的测试。
- 不修改加密逻辑、协议或服务端。

---

## 4. 七阶段开发顺序

### 任务 A：采集运行截图

目标：按 `document/screenshots/README.md` 中的清单，实际采集全部截图。

必须完成：

- 桌面端截图：
  - 客户端启动界面（密钥生成前）
  - 密钥生成后的界面（显示指纹）
  - 双客户端聊天界面（含消息气泡和 Crypto Console）
  - 服务端控制台日志（显示消息转发但不含明文）
- Web 端截图：
  - Web 客户端聊天界面（双向消息 + Crypto Console）
- Wireshark 截图：
  - 过滤 `tcp.port == 8765` 的 WebSocket 帧
  - 展开 payload 显示 `wrapped_key`、`nonce`、`ciphertext`（均为 Base64 密文）
  - 确认 payload 中不含任何可识别的聊天明文
- 异常场景截图（可选）：
  - 未生成密钥时的提示
  - 一方断连后联系人列表变化

完成标准：

- `document/screenshots/` 目录下至少有 8 张实际截图。
- 截图按 `README.md` 中的编号命名（如 `01_client_startup.png`）。

#### 人工操作流程

**A-1. 桌面端截图（编号 01-09）**

```
1. 打开终端，启动服务端：
   python chat_server.py
   → 截图 01_server_start.png（显示 "服务端启动: ws://127.0.0.1:8765"）

2. 双击 dist/SecureChat.exe 或执行 python desktop_chat_gui.py 启动客户端 A
   → 截图 02_alice_keygen.png（密钥生成后，显示指纹）

3. 输入用户名 Alice，点击"连接"
   → 截图 03_alice_connected.png（状态栏显示"已连接"）

4. 再启动一个客户端 B，用户名 Bob，连接服务端
   → 截图 04_bob_contact_list.png（联系人列表显示 Alice）

5. Alice 端：选择 Bob → 输入消息 → 发送
   → 截图 05_alice_send_msg.png（消息气泡显示发送的消息）
   → 截图 06_alice_crypto_log.png（Crypto Console 显示加密日志）

6. Bob 端：选择 Alice → 查看收到的消息
   → 截图 07_bob_recv_msg.png（消息气泡显示接收的解密消息）
   → 截图 08_bob_crypto_log.png（Crypto Console 显示解密日志）

7. 切回服务端终端
   → 截图 09_server_log_noclear.png（日志只有 type/sender/receiver/payload_len，无明文）
```

**A-2. Wireshark 截图（编号 10-11）**

```
1. 打开 Wireshark → 选择本地回环接口（Loopback / lo / Npcap Loopback）
2. 过滤条件输入：tcp.port == 8765
3. 在桌面端客户端发送一条消息
4. Wireshark 中找到包含数据的 TCP 帧
   → 截图 10_wireshark_list.png（捕获列表概览）
5. 点击该帧，展开 payload
   → 截图 11_wireshark_payload.png（显示 wrapped_key / nonce / ciphertext 等 Base64 密文字段）
6. 确认 payload 中搜索不到聊天明文
```

**A-3. Web 端截图**

```
1. 确保服务端仍在运行
2. 打开终端，在项目根目录执行：python -m http.server 8080 --directory web
3. 打开浏览器 Tab 1：http://localhost:8080 → 用户名 WebAlice → 生成密钥 → 连接
4. 打开浏览器 Tab 2：http://localhost:8080 → 用户名 WebBob → 生成密钥 → 连接
5. WebAlice 选择 WebBob，发送消息；WebBob 选择 WebAlice 查看并回复
   → 截图保存为 12_web_chat.png
```

### 任务 B：完成最终报告

目标：将 `document/final_report.md` 的内容整理为正式的最终报告文档。

必须完成：

- 确认报告按 8 章结构完整（任务分析、理论基础、设计、实现与测试、结果分析、运行截图、使用说明、团队分工）。
- 在报告中插入任务 A 采集的截图。
- 补充 Web 端自我拓展内容作为加分亮点（在"结果分析"或"实现与测试"章节中体现）。
- 检查报告中的技术描述与实际代码一致。
- 导出为 Word (.docx) 或 PDF 格式。

完成标准：

- 报告文档可独立阅读，不依赖仓库中的其他文件。
- 报告中的截图清晰可辨，标注完整。

#### 人工操作流程

**方法一：使用 Pandoc 转换（推荐）**

```
1. 安装 Pandoc：
   - Windows: 下载 https://pandoc.org/installing.html 安装
   - 或: winget install --id JohnMacFarlane.Pandoc

2. 转换为 Word：
   cd document
   pandoc final_report.md -o final_report.docx --toc

3. 用 Word 打开 final_report.docx：
   - 插入 screenshots/ 目录下的截图到对应章节
   - 调整格式（字体：宋体/Times New Roman，字号：小四）
   - 添加封面页（课程名、题目、姓名、学号、日期）
   - 另存为 PDF 备份
```

**方法二：在 Word 中直接编写**

```
1. 打开 Word → 新建空白文档
2. 参照 document/report_outline.md 的章节结构逐章粘贴
3. 从 document/final_report.md 中复制文本内容
4. 插入截图，添加图注（如"图 5-1 Alice 端加密日志"）
5. 保存为 .docx，同时导出 PDF
```

**报告中 Web 端亮点内容模板**（可直接写入"结果分析"章节）：

```
5.X Web 端自我拓展

本项目在完成桌面端功能后，自主拓展实现了 Web 浏览器客户端，
采用原生 HTML/CSS/JavaScript + Web Crypto API，无需任何前端框架。

Web 端与桌面端使用完全一致的加密参数：
- RSA-2048 OAEP (SHA-256, MGF1-SHA-256)
- AES-256-GCM (12 字节 nonce, 128 位 tag)
- 公钥格式: SPKI PEM
- 编码: 标准 Base64

两端可通过同一中继服务端无缝互通，验证了"一套协议、多端互操作"的设计目标。
```

### 任务 C：更新提交包

目标：生成最终版本的提交压缩包。

必须完成：

- 运行 `pack_submission.py` 或手动整理，确保压缩包包含：
  - 完整的项目源码（所有 `.py` 文件 + `web/` 目录）
  - `dist/` 目录下的可执行文件
  - `document/` 目录下的文档材料
  - 最终报告文件（Word/PDF）
  - `README.md`、`requirements.txt`、`pyproject.toml`
- 压缩包命名为"第X组+端到端加密即时通讯软件设计与实现"。
- 确认压缩包中不含 `.git/`、`__pycache__/`、`.vscode/` 等不必要的目录。

完成标准：

- 解压后可直接按 `README.md` 安装依赖、运行测试、启动程序。
- 压缩包大小合理（≤ 50 MB）。

#### 人工操作流程

**使用 PowerShell 打包（Windows）：**

```powershell
# 进入项目上级目录
cd C:\Users\czl1\Desktop\Project

# 创建打包目录（排除不必要文件）
$dest = "第X组+端到端加密即时通讯软件设计与实现"
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest

# 复制需要的文件（排除 .git, __pycache__, .vscode, node_modules）
robocopy InfoSecurityProj $dest /E /XD .git __pycache__ .vscode .mypy_cache .pytest_cache others Assistance /XF *.pyc

# 将最终报告 Word/PDF 也复制进去（如果不在 document/ 里）
# Copy-Item "path/to/final_report.docx" "$dest/document/"

# 压缩
Compress-Archive -Path $dest -DestinationPath "$dest.zip" -Force

# 检查大小
(Get-Item "$dest.zip").Length / 1MB
# 应 ≤ 50 MB

# 验证：解压到临时目录测试
Expand-Archive "$dest.zip" -DestinationPath "verify_temp" -Force
# 检查 verify_temp/ 下的文件结构是否完整
```

**打包前检查清单：**

```
□ .git/ 目录未包含
□ __pycache__/ 目录未包含
□ .vscode/ 目录未包含
□ dist/SecureChat.exe 已包含
□ dist/SecureChatServer.exe 已包含
□ web/ 目录完整（5个文件 + README.md）
□ document/final_report.docx 或 .pdf 已包含
□ 所有 .py 源文件已包含
□ requirements.txt 已包含
□ README.md 已包含
```

### 任务 D：逐条勾选提交检查单

目标：按 `document/submission_checklist.md` 逐条检查并勾选。

必须完成：

- 程序源码检查（注释充分、核心文件齐全、依赖清单完整）。
- 可运行程序检查（exe 文件存在且可启动）。
- 自动化测试检查（57 项全部通过）。
- 文档材料检查（报告骨架、实验结果、设计决策、团队分工、汇报脚本）。
- 最终报告检查（8 章结构、截图已插入）。
- 演示准备检查（汇报脚本、演示环境、抓包截图）。
- 打包提交检查（命名规范、压缩包内容）。

完成标准：

- `document/submission_checklist.md` 所有条目已勾选为 `[x]`。
- 任何未勾选的条目都已记录原因或已解决。

#### 当前勾选状态

已自动确认通过的条目（2026-04-20 机器验证）：

- ✅ 一、程序源码检查 — **全部通过**（8 个核心文件均有 docstring，requirements.txt / pyproject.toml / README.md 完整）
- ✅ 二、可运行程序检查 — **全部通过**（dist/ 下 exe 文件存在）
- ✅ 三、自动化测试检查 — **全部通过**（57/57 tests OK）
- ✅ 四、文档材料检查 — **全部通过**（6 个文档文件均存在）
- 🔶 五、最终报告检查 — **部分通过**，待人工操作：插入截图到报告、导出 Word/PDF
- 🔶 六、演示准备检查 — **部分通过**，待人工操作：通读汇报脚本、Wireshark 抓包
- 🔶 七、打包提交检查 — **待人工操作**：确认组号、打包、发送邮件

#### 剩余人工操作

```
1. 完成任务 A（截图采集）后 → 回到 checklist 勾选 五、六 中截图相关条目
2. 完成任务 B（报告定稿）后 → 勾选 五 中报告导出条目
3. 完成任务 C（打包）后 → 勾选 七 全部条目
4. 完成任务 E（邮件发送）后 → 勾选最后一条
```

### 任务 E：最终提交

目标：将最终压缩包发送至提交邮箱。

必须完成：

- 确认压缩包内容完整。
- 发送至 `xiongf@bjtu.edu.cn`。
- 记录提交时间和确认信息。

完成标准：

- 邮件已发送，附件为完整的压缩包。

#### 人工操作流程

```
1. 最终检查：
   - 解压压缩包到空目录，确认文件完整
   - 在解压目录中运行 python -m unittest discover -s tests -v → 全部通过
   - 打开 dist/SecureChat.exe 确认可启动
   - 打开 document/ 确认报告 Word/PDF 存在

2. 发送邮件：
   - 收件人: xiongf@bjtu.edu.cn
   - 主题: 第X组+端到端加密即时通讯软件设计与实现
   - 正文:
       老师您好，
       附件为第X组课程设计作品"端到端加密即时通讯软件设计与实现"。
       组员：XXX（学号 XXXXXXXX）
       请查收，谢谢！
   - 附件: 第X组+端到端加密即时通讯软件设计与实现.zip

3. 确认：
   - 检查"已发送"邮箱确认邮件发出
   - 截图保存发送记录备查
```

---

## 5. 七阶段验收标准

当以下条件全部满足时，七阶段可以结束，**课题任务全部完成**：

1. 运行截图已全部采集（≥ 8 张）。
2. 最终报告已导出为 Word/PDF，包含 8 章结构和截图。
3. 提交压缩包已生成，命名规范，内容完整。
4. `document/submission_checklist.md` 所有条目已勾选。
5. 压缩包已发送至提交邮箱。

---

## 6. 七阶段注意事项

### 6.1 报告是重中之重

课程评分中报告占 50%。报告的质量直接决定最终成绩。七阶段的主要时间应投入到报告撰写和截图采集上，而不是代码开发。

### 6.2 截图必须真实

截图必须来自实际运行的程序，不能使用模拟或编辑过的截图。Wireshark 抓包截图尤为关键——它是证明"传输链路上全程为密文"的直接证据。

### 6.3 Web 端是加分亮点

Web 端是自我拓展内容，在报告中应作为亮点展示：

- 强调"一套服务端，多端互通"的架构设计
- 展示 Web Crypto API 与 Python cryptography 库的加密参数对齐方案
- 附上 Web 端的截图作为跨平台互通的证据

### 6.4 提交前最终检查

提交前务必：

- 解压压缩包到一个空目录，验证可以按 README 从零运行。
- 检查报告中的所有截图是否正确显示。
- 检查报告中的技术描述是否与实际代码一致。

---

## 8. Ubuntu 服务器部署（多端现场演示）

七阶段新增了远程部署能力，使得演示可以在教室中多设备同时进行。

**完整指南**：[document/ubuntu_deploy_guide.md](document/ubuntu_deploy_guide.md)

### 核心架构

```
浏览器 (HTTPS) → nginx (443, SSL 终止) → 静态 Web 文件
浏览器 (WSS)   → nginx (443, /ws 路径) → chat_server.py (8765)
```

### 关键技术决策

| 决策                   | 原因                                                                  |
| ---------------------- | --------------------------------------------------------------------- |
| 必须使用 HTTPS         | Web Crypto API (`crypto.subtle`) 仅在安全上下文可用                   |
| nginx 反向代理         | SSL 终止 + WebSocket 升级 + 静态文件服务，一站式解决                  |
| 自签名证书             | 教室演示场景够用，浏览器接受警告即可                                  |
| WebSocket 地址自动检测 | `web/app.js` 已添加自动检测逻辑：远程访问时自动填入 `wss://<host>/ws` |

### 代码改动

- `web/app.js`：新增远程部署自动检测 WebSocket 地址（底部 `autoDetectServerUrl()`）
- `chat_server.py`：无改动，已支持 `--host 0.0.0.0`

### 快速部署流程

```bash
# 1. 上传项目到 Ubuntu 服务器
scp -r InfoSecurityProj user@server:~/SecureChat

# 2. 在服务器上运行一键部署脚本
ssh user@server
cd ~/SecureChat
chmod +x deploy.sh
./deploy.sh

# 3. 各演示设备浏览器访问
#    https://<服务器IP>/
```

---

## 7. 项目总体回顾

从 code_plan_1 到 code_plan_7，项目经历了以下阶段：

| 阶段        | 目标                              | 状态      |
| ----------- | --------------------------------- | --------- |
| code_plan_1 | 基础加密模块（AES + RSA）         | ✅ 已完成 |
| code_plan_2 | 通信协议与服务端架构              | ✅ 已完成 |
| code_plan_3 | 桌面 GUI 客户端与端到端加密集成   | ✅ 已完成 |
| code_plan_4 | 交付收口与验收包装                | ✅ 已完成 |
| code_plan_5 | 报告撰写、代码注释、打包脚本      | ✅ 已完成 |
| code_plan_6 | 自我拓展 — Web 端开发与跨平台互通 | ✅ 已完成 |
| code_plan_7 | 最终收尾 — 截图、报告定稿、提交   | 🔄 当前   |

项目的技术成果：

- 8 个核心 Python 模块，57 项自动化测试全部通过
- 桌面端（Tkinter）+ Web 端（原生 HTML/CSS/JS）双平台客户端
- RSA-2048 OAEP + AES-256-GCM 混合加密，跨平台参数完全一致
- 盲转发中继服务端，服务端零知识，传输链路全程密文
- Web Crypto API 与 Python cryptography 的互通已验证

---

## 8. 最后结论

从当前项目状态看，所有功能开发和文档准备已经完成。七阶段是纯粹的收尾阶段。

七阶段唯一需要人工完成的高价值工作是：

1. **截图采集** — 实际运行程序并截取各场景截图。
2. **报告定稿** — 将 Markdown 报告转换为 Word/PDF，插入截图，调整格式。
3. **提交打包** — 按命名规范打包并发送邮件。

这些工作不涉及代码开发，主要是文档整理和人工操作。按 `document/submission_checklist.md` 逐条勾选即可确保不遗漏。

完成七阶段后，课题任务结束。
