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

各消息类型 payload 结构说明：
  register:
      {"public_key": str}          — 客户端公钥 PEM。
  public_key:
      {"public_key": str}          — 发送方公钥 PEM。
  chat_message:
      {"wrapped_key": str, "nonce": str, "ciphertext": str, ...}
                                    — 混合加密密文。
  ack:
      {"ack_for": str}             — 被确认的消息类型或标识。
  error:
      {"message": str}             — 错误描述。
  heartbeat:
      {}                           — 空载荷。
  user_list:
      {"users": {uid: public_key_pem, ...}}
                                    — 在线用户及其公钥。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
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

MSG_FILE_TRANSFER = "file_transfer"
"""小文件整体传输（≤ 5 MB），payload 包含加密文件内容和元信息。"""

MSG_FILE_CHUNK = "file_chunk"
"""大文件分块传输（单块），payload 包含加密块内容、传输 ID 和序号。"""

# 所有合法消息类型集合，便于校验
VALID_TYPES = {
    MSG_REGISTER, MSG_PUBLIC_KEY, MSG_CHAT_MESSAGE,
    MSG_ACK, MSG_ERROR, MSG_HEARTBEAT, MSG_USER_LIST,
    MSG_FILE_TRANSFER, MSG_FILE_CHUNK,
}

# 各消息类型在 payload 中必须包含的字段
_PAYLOAD_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    MSG_REGISTER:      ("public_key",),
    MSG_PUBLIC_KEY:    ("public_key",),
    MSG_CHAT_MESSAGE:  ("wrapped_key", "nonce", "ciphertext"),
    MSG_ACK:           ("ack_for",),
    MSG_ERROR:         ("message",),
    MSG_HEARTBEAT:     (),
    MSG_USER_LIST:     ("users",),
    MSG_FILE_TRANSFER: ("wrapped_key", "nonce", "ciphertext", "filename", "filesize", "mime_type"),
    MSG_FILE_CHUNK:    ("wrapped_key", "nonce", "ciphertext", "transfer_id", "chunk_index", "total_chunks", "filename", "filesize", "mime_type"),
}

# 必须提供非空 receiver_id 的消息类型
_REQUIRES_RECEIVER: set[str] = {
    MSG_PUBLIC_KEY, MSG_CHAT_MESSAGE, MSG_ACK,
    MSG_FILE_TRANSFER, MSG_FILE_CHUNK,
}


# -------------------- 消息构造函数 --------------------

def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _build(msg_type: str, sender_id: str, receiver_id: str, payload: Mapping[str, object]) -> str:
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


def make_chat_message(sender_id: str, receiver_id: str, payload: Mapping[str, object]) -> str:
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


def make_file_transfer_message(
    sender_id: str,
    receiver_id: str,
    encrypted_payload: Mapping[str, object],
    filename: str,
    filesize: int,
    mime_type: str,
) -> str:
    """
    构造小文件整体传输消息（≤ 5 MB）。

    :param encrypted_payload: message_crypto.encrypt_file_data 的输出。
    :param filename: 原始文件名。
    :param filesize: 原始文件大小（字节）。
    :param mime_type: MIME 类型（如 image/png）。
    """
    payload = {
        "wrapped_key": encrypted_payload["wrapped_key"],
        "nonce": encrypted_payload["nonce"],
        "ciphertext": encrypted_payload["ciphertext"],
        "filename": filename,
        "filesize": filesize,
        "mime_type": mime_type,
    }
    return _build(MSG_FILE_TRANSFER, sender_id, receiver_id, payload)


def make_file_chunk_message(
    sender_id: str,
    receiver_id: str,
    encrypted_payload: Mapping[str, object],
    transfer_id: str,
    chunk_index: int,
    total_chunks: int,
    filename: str,
    filesize: int,
    mime_type: str,
) -> str:
    """
    构造大文件分块传输消息（单块）。

    :param transfer_id: 传输 ID（UUID，标识同一文件的所有块）。
    :param chunk_index: 当前块索引（从 0 开始）。
    :param total_chunks: 总块数。
    """
    payload = {
        "wrapped_key": encrypted_payload["wrapped_key"],
        "nonce": encrypted_payload["nonce"],
        "ciphertext": encrypted_payload["ciphertext"],
        "transfer_id": transfer_id,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "filename": filename,
        "filesize": filesize,
        "mime_type": mime_type,
    }
    return _build(MSG_FILE_CHUNK, sender_id, receiver_id, payload)


# -------------------- 消息解析 --------------------

def parse_message(raw_message: str, *, strict_payload: bool = True) -> dict[str, object]:
    """
    将接收到的 JSON 字符串解析为消息字典。

    校验规则：
      - 必须是合法 JSON。
      - 必须包含 type / sender_id / payload 字段。
      - type 必须在 VALID_TYPES 中。
      - payload 必须是 dict。
      - 当 strict_payload=True 时，payload 必须包含该消息类型所要求的必要字段。
      - 需要 receiver_id 的消息类型（public_key / chat_message / ack），
        receiver_id 不能为空。

    :param raw_message: 原始 JSON 字符串。
    :param strict_payload: 是否校验 payload 必要字段，默认 True。
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

    msg_type = msg["type"]
    if msg_type not in VALID_TYPES:
        raise ValueError(f"未知消息类型: {msg_type}")

    # 补全可选字段默认值
    msg.setdefault("receiver_id", "")
    msg.setdefault("timestamp", "")

    # payload 必须是 dict
    payload = msg["payload"]
    if not isinstance(payload, dict):
        raise ValueError("payload 必须是 JSON 对象。")

    # 需要 receiver_id 的消息类型不能为空
    if msg_type in _REQUIRES_RECEIVER and not msg.get("receiver_id"):
        raise ValueError(f"消息类型 {msg_type} 需要提供 receiver_id。")

    # 校验 payload 必要字段
    if strict_payload:
        required = _PAYLOAD_REQUIRED_FIELDS.get(msg_type, ())
        for field in required:
            if field not in payload:
                raise ValueError(f"消息类型 {msg_type} 的 payload 缺少字段: {field}")

    return msg
