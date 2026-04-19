# 截图采集说明

本目录用于存放最终报告所需的运行截图和抓包截图。

## 截图命名规范

按以下编号命名，便于报告引用：

| 编号 | 文件名                      | 内容                              | 状态 |
| ---- | --------------------------- | --------------------------------- | ---- |
| 01   | `01_server_start.png`       | 服务端启动日志                    | [ ]  |
| 02   | `02_alice_keygen.png`       | 客户端 A 生成密钥后界面（含指纹） | [ ]  |
| 03   | `03_alice_connected.png`    | 客户端 A 连接成功后界面           | [ ]  |
| 04   | `04_bob_contact_list.png`   | 客户端 B 联系人列表（显示 Alice） | [ ]  |
| 05   | `05_alice_send_msg.png`     | Alice 发送消息后的聊天界面        | [ ]  |
| 06   | `06_alice_crypto_log.png`   | Alice 端 Crypto Console 加密日志  | [ ]  |
| 07   | `07_bob_recv_msg.png`       | Bob 收到消息后的聊天界面          | [ ]  |
| 08   | `08_bob_crypto_log.png`     | Bob 端 Crypto Console 解密日志    | [ ]  |
| 09   | `09_server_log_noclear.png` | 服务端日志（不含明文）            | [ ]  |
| 10   | `10_wireshark_list.png`     | Wireshark 捕获列表                | [ ]  |
| 11   | `11_wireshark_payload.png`  | Wireshark 展开帧 payload（密文）  | [ ]  |

## 采集步骤

1. 按 `tests/manual_acceptance.md` 完成一次完整双客户端演示
2. 按上表编号逐项截图并保存到本目录
3. 抓包截图需提前启动 Wireshark，过滤条件 `tcp.port == 8765`
4. 截图完成后更新上表状态为 `[x]`
