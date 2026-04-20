# 人工操作待办清单

> 本文件汇总了项目中所有需要人工完成的操作。  
> 代码开发和自动化测试已全部完成（74/74 tests OK），以下均为非代码工作。

---

## 一、截图采集

### 桌面端截图

| #   | 截图内容                                  | 保存为                                           | 状态 |
| --- | ----------------------------------------- | ------------------------------------------------ | ---- |
| 1   | 服务端启动日志（`python chat_server.py`） | `document/screenshots/01_server_start.png`       | ☐    |
| 2   | 客户端 A (Alice) 密钥生成后界面（含指纹） | `document/screenshots/02_alice_keygen.png`       | ☐    |
| 3   | Alice 连接成功（状态栏显示"已连接"）      | `document/screenshots/03_alice_connected.png`    | ☐    |
| 4   | Bob 连接后联系人列表（显示 Alice）        | `document/screenshots/04_bob_contact_list.png`   | ☐    |
| 5   | Alice 发送消息后聊天界面                  | `document/screenshots/05_alice_send_msg.png`     | ☐    |
| 6   | Alice 端 Crypto Console 加密日志          | `document/screenshots/06_alice_crypto_log.png`   | ☐    |
| 7   | Bob 收到消息后聊天界面                    | `document/screenshots/07_bob_recv_msg.png`       | ☐    |
| 8   | Bob 端 Crypto Console 解密日志            | `document/screenshots/08_bob_crypto_log.png`     | ☐    |
| 9   | 服务端日志（只有类型和长度，无明文）      | `document/screenshots/09_server_log_noclear.png` | ☐    |

### 文件传输截图（新增功能）

| #   | 截图内容                                  | 保存为                                  | 状态 |
| --- | ----------------------------------------- | --------------------------------------- | ---- |
| 10  | Alice 发送图片文件后界面（含缩略图预览）  | `document/screenshots/10_file_send.png` | ☐    |
| 11  | Bob 收到图片后界面（含缩略图 + 保存链接） | `document/screenshots/11_file_recv.png` | ☐    |

### Wireshark 抓包截图

| #   | 截图内容                                      | 保存为                                          | 状态 |
| --- | --------------------------------------------- | ----------------------------------------------- | ---- |
| 12  | 捕获列表概览（过滤 `tcp.port == 8765`）       | `document/screenshots/12_wireshark_list.png`    | ☐    |
| 13  | 展开 WebSocket 帧 payload（显示 Base64 密文） | `document/screenshots/13_wireshark_payload.png` | ☐    |

### Web 端截图

| #   | 截图内容                            | 保存为                                 | 状态 |
| --- | ----------------------------------- | -------------------------------------- | ---- |
| 14  | Web 端双向聊天界面 + Crypto Console | `document/screenshots/14_web_chat.png` | ☐    |
| 15  | Web 端文件传输/图片预览             | `document/screenshots/15_web_file.png` | ☐    |

### 异常场景截图（可选加分）

| #   | 截图内容                   | 保存为                                       | 状态 |
| --- | -------------------------- | -------------------------------------------- | ---- |
| 16  | 未生成密钥时发送消息的提示 | `document/screenshots/16_no_key_warning.png` | ☐    |
| 17  | 一方断连后联系人列表变化   | `document/screenshots/17_disconnect.png`     | ☐    |

---

## 二、Wireshark 抓包

### 操作步骤

1. 安装 Wireshark（https://www.wireshark.org/）
2. 启动 Wireshark → 选择 **Loopback / Npcap Loopback** 接口
3. 过滤条件：`tcp.port == 8765`
4. 点击"开始捕获"
5. 启动服务端 + 双客户端，完成一次聊天
6. 停止捕获
7. 找到 WebSocket 帧 → 展开 payload
8. 确认 `wrapped_key`、`nonce`、`ciphertext` 为 Base64 编码，无可识别明文
9. 截图保存（见上方截图表 #12、#13）

---

## 三、报告导出

### 操作步骤

1. 将截图插入 `document/final_report.md` 对应章节（第六章运行截图）
2. **方法 A（Pandoc 推荐）**：
   ```powershell
   cd document
   pandoc final_report.md -o final_report.docx --toc
   ```
   然后用 Word 打开，调整格式（宋体/小四）、添加封面页
3. **方法 B（手动）**：在 Word 中按 `report_outline.md` 结构逐章粘贴
4. 另存为 PDF 备份

### 报告格式要求

- 字体：正文宋体/小四，标题黑体
- 封面页：课程名称、题目、姓名、学号、日期
- 图注格式："图 X-X 描述"

---

## 四、PPT 制作

### 操作步骤

1. 按 `document/ppt_outline.md` 大纲制作 PPT
2. 时间控制：12 分钟展示 + 3 分钟现场演示
3. 关键幻灯片中插入对应截图
4. 演示部分提前准备好 3 个终端窗口

---

## 五、打包提交

### 操作步骤

1. 确认组号（第X组）
2. 打包命令（排除 `.git/`、`__pycache__/`、`.vscode/` 等）：
   ```powershell
   cd C:\Users\czl1\Desktop\Project
   $dest = "第X组+端到端加密即时通讯软件设计与实现"
   robocopy InfoSecurityProj $dest /E /XD .git __pycache__ .vscode .mypy_cache .pytest_cache others Assistance .specstory /XF *.pyc
   Compress-Archive -Path $dest -DestinationPath "$dest.zip" -Force
   ```
3. 检查压缩包大小 ≤ 50 MB
4. 确认包含：源码、dist/exe、document/报告(Word/PDF)、web/ 目录、README.md

### 打包内容检查

- [ ] `.git/` 未包含
- [ ] `__pycache__/` 未包含
- [ ] `.vscode/` 未包含
- [ ] `dist/SecureChat.exe` 已包含
- [ ] `dist/SecureChatServer.exe` 已包含
- [ ] `web/` 目录完整
- [ ] `document/final_report.docx` 或 `.pdf` 已包含
- [ ] 所有 `.py` 源文件已包含
- [ ] `requirements.txt` 已包含

---

## 六、邮件提交

| 项目     | 内容                                   |
| -------- | -------------------------------------- |
| 收件邮箱 | `xiongf@bjtu.edu.cn`                   |
| 邮件标题 | 第X组+端到端加密即时通讯软件设计与实现 |
| 附件     | 上述压缩包                             |
| 截止时间 | 第 9 周周日                            |

- [ ] 邮件已发送
- [ ] 收到送达确认

---

## 七、答辩准备

- [ ] 通读 `document/ppt_outline.md` 和 `document/week8_demo_script.md`
- [ ] PPT 制作完成
- [ ] 完整演练一次（12 min PPT + 3 min 实操）
- [ ] 演示环境测试通过（服务端 + 双客户端 + Web 端正常运行）
- [ ] 准备常见提问的回答（见 `document/week8_demo_script.md` 末尾 Q&A 表格）

---

## 执行顺序建议

```
1. 截图采集 + Wireshark 抓包  ← 最先做，后面都依赖截图
2. 报告插入截图 → 导出 Word/PDF
3. PPT 制作
4. 完整演练一次
5. 打包 → 邮件提交
```
