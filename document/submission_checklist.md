# 最终提交检查单

## 提交信息

| 项目     | 内容                                                     |
| -------- | -------------------------------------------------------- |
| 提交邮箱 | `xiongf@bjtu.edu.cn`                                     |
| 命名规范 | 第X组+题目（如：第1组+端到端加密即时通讯软件设计与实现） |
| 提交方式 | 压缩包发送至邮箱                                         |
| 截止时间 | 第 9 周周日                                              |
| 提交人   | 组长提交（个人项目则本人提交）                           |

---

## 一、程序源码检查

- [ ] 所有 `.py` 源文件包含充分的中文/英文注释（**红线要求：无注释视为抄袭**）
- [ ] 核心文件列表完整：
  - [ ] `chat_server.py` — 中继服务端
  - [ ] `desktop_chat_gui.py` — 桌面客户端（主程序入口）
  - [ ] `chat_client.py` — 客户端网络层
  - [ ] `chat_protocol.py` — 消息协议
  - [ ] `session_manager.py` — 会话管理
  - [ ] `message_crypto.py` — 混合加密
  - [ ] `aes_core.py` — AES-GCM 加密
  - [ ] `rsa_core.py` — RSA 密钥管理
- [ ] `requirements.txt` 包含全部依赖
- [ ] `pyproject.toml` 版本和描述正确
- [ ] `README.md` 含完整的安装和运行说明

## 二、可运行程序检查

- [ ] `dist/SecureChat.exe` 存在且双击可启动
- [ ] `dist/SecureChatServer.exe` 存在且控制台可运行
- [ ] 打包命令已记录在 `README.md` 中
- [ ] 明确标注 `dist/RSA_Encrypt_Decrypt_Tool.exe` 为历史工具，非主交付物

## 三、自动化测试检查

- [ ] `python -m unittest discover -s tests -v` 全部通过
- [ ] 测试文件列表完整：
  - [ ] `tests/test_crypto.py`（15 项）
  - [ ] `tests/test_protocol.py`（14 项）
  - [ ] `tests/test_protocol_v2.py`（17 项）
  - [ ] `tests/test_integration.py`（11 项）

## 四、文档材料检查

- [ ] `document/report_outline.md` — 报告骨架
- [ ] `document/result_note.md` — 实验结果说明
- [ ] `document/design_decisions.md` — 设计决策与原创性说明
- [ ] `document/team_division.md` — 团队分工（已选择正确的方案）
- [ ] `document/week8_demo_script.md` — 汇报脚本 + 截图清单 + Wireshark 步骤
- [ ] `tests/manual_acceptance.md` — 人工验收手册

## 五、最终报告检查

- [ ] 按 `document/report_outline.md` 骨架撰写完毕
- [ ] 包含以下必需章节：
  - [ ] 任务分析
  - [ ] 相关理论及技术基础
  - [ ] 解决思路与设计（概要设计 + 详细设计）
  - [ ] 实现与测试
  - [ ] 任务结果说明与结果分析
  - [ ] 运行截图
  - [ ] 程序使用说明
  - [ ] 团队分工情况
- [ ] 运行截图已插入（参照截图清单）
- [ ] 抓包截图已插入

## 六、演示准备检查

- [ ] 15 分钟汇报脚本已熟悉
- [ ] 演示环境已测试（服务端 + 双客户端可正常运行）
- [ ] Wireshark 抓包已完成并截图
- [ ] 所有截图已保存

## 七、打包提交检查

- [ ] 压缩包命名符合"第X组+题目"规范
- [ ] 压缩包内容：
  - [ ] 最终报告（Word/PDF）
  - [ ] 程序源码（完整项目目录）
  - [ ] 可运行程序（`dist/` 目录下的 exe）
  - [ ] 实验结果说明（`document/result_note.md` 或报告中已包含）
- [ ] 已发送至 `xiongf@bjtu.edu.cn`
