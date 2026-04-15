"""
聊天协议定义模块。

本模块定义了客户端与服务端之间所有 WebSocket 消息的结构和序列化规则。
所有消息均为 JSON 格式，统一包含以下字段：
  - type:        消息类型（见下方常量）
  - sender_id:   发送方用户 ID
  - receiver_id: 接收方用户 ID（部分类型可为空字符串）
  - timestamp:   消息创建时的 ISO 8601 时间戳
  - payload:     消息体（具体内容因 type 而异）

设计目的：
  - 将协议格式与业务逻辑解耦，所有网络层只需调用本模块即可构造 / 解析消息。
  - 服务端只看 type / sender_id / receiver_id 做路由，不解析 payload 内容，确保盲转发。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

# -------------------- 消息类型常量 --------------------

MSG_REGISTER = "register"
"""客户端上线注册，payload 中携带公钥 PEM。"""

MSG_PUBLIC_KEY = "public_key"
"""主动向特定用户发送自己的公钥（用于初始密钥交换）。"""

MSG_CHAT_MESSAGE = "chat_message"
"""聊天密文消息，payload 包含 wrapped_key / nonce / ciphertext。"""

MSG_ACK = "ack"
"""确认回执（可选使用）。"""

MSG_ERROR = "error"
"""错误通知。"""

MSG_HEARTBEAT = "heartbeat"
"""心跳保活包。"""

MSG_USER_LIST = "user_list"
"""服务端广播当前在线用户列表（附带公钥）。"""

# 所有合法消息类型集合，便于校验
VALID_TYPES = {
    MSG_REGISTER, MSG_PUBLIC_KEY, MSG_CHAT_MESSAGE,
    MSG_ACK, MSG_ERROR, MSG_HEARTBEAT, MSG_USER_LIST,
}


# -------------------- 消息构造函数 --------------------

def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _build(msg_type: str, sender_id: str, receiver_id: str, payload: dict) -> str:
    """
    内部通用消息构造器。
    将各字段打包为 JSON 字符串，确保输出格式统一。
    """
    return json.dumps({
        "type": msg_type,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "timestamp": _now_iso(),
        "payload": payload,
    }, ensure_ascii=False)


def make_register_message(sender_id: str, public_key_pem: str) -> str:
    """
    构造注册消息。客户端连接服务端后第一件事就是发送此消息。

    :param sender_id: 用户 ID。
    :param public_key_pem: 本地公钥的 PEM 文本。
    """
    return _build(MSG_REGISTER, sender_id, "", {"public_key": public_key_pem})


def make_public_key_message(sender_id: str, receiver_id: str, public_key_pem: str) -> str:
    """
    构造公钥发送消息，用于主动将自己的公钥发送给指定用户。

    :param sender_id: 发送方 ID。
    :param receiver_id: 接收方 ID。
    :param public_key_pem: 发送方的公钥 PEM 文本。
    """
    return _build(MSG_PUBLIC_KEY, sender_id, receiver_id, {"public_key": public_key_pem})


def make_chat_message(sender_id: str, receiver_id: str, payload: dict[str, object]) -> str:
    """
    构造聊天密文消息。

    :param sender_id: 发送方 ID。
    :param receiver_id: 接收方 ID。
    :param payload: 由 message_crypto.encrypt_chat_message 生成的密文字典。
    """
    return _build(MSG_CHAT_MESSAGE, sender_id, receiver_id, payload)


def make_ack_message(sender_id: str, receiver_id: str, ack_for: str) -> str:
    """
    构造确认回执消息。

    :param ack_for: 被确认的消息类型或标识。
    """
    return _build(MSG_ACK, sender_id, receiver_id, {"ack_for": ack_for})


def make_error_message(message: str, sender_id: str | None = None) -> str:
    """
    构造错误通知消息（一般由服务端发出）。

    :param message: 错误描述文本。
    :param sender_id: 发送方 ID，服务端发送时可设为 "server"。
    """
    return _build(MSG_ERROR, sender_id or "server", "", {"message": message})


def make_heartbeat_message(sender_id: str) -> str:
    """构造心跳包，用于保持 WebSocket 连接活跃。"""
    return _build(MSG_HEARTBEAT, sender_id, "", {})


def make_user_list_message(users: dict[str, str]) -> str:
    """
    构造在线用户列表广播消息（由服务端向所有客户端发送）。

    :param users: {user_id: public_key_pem} 字典。
    """
    return _build(MSG_USER_LIST, "server", "", {"users": users})


# -------------------- 消息解析 --------------------

def parse_message(raw_message: str) -> dict[str, object]:
    """
    将接收到的 JSON 字符串解析为消息字典。

    校验规则：
      - 必须是合法 JSON。
      - 必须包含 type / sender_id / payload 字段。
      - type 必须在 VALID_TYPES 中。

    :param raw_message: 原始 JSON 字符串。
    :return: 解析后的消息字典。
    :raises ValueError: JSON 非法或缺少必要字段时抛出。
    """
    try:
        msg = json.loads(raw_message)
    except json.JSONDecodeError as e:
        raise ValueError(f"消息 JSON 解析失败: {e}") from e

    if not isinstance(msg, dict):
        raise ValueError("消息必须是 JSON 对象。")

    for field in ("type", "sender_id", "payload"):
        if field not in msg:
            raise ValueError(f"消息缺少必要字段: {field}")

    if msg["type"] not in VALID_TYPES:
        raise ValueError(f"未知消息类型: {msg['type']}")

    # 补全可选字段默认值
    msg.setdefault("receiver_id", "")
    msg.setdefault("timestamp", "")

    return msg
