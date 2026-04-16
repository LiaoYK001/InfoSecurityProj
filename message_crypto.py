"""
混合加密消息模块（RSA + AES-GCM）。

本模块封装了聊天消息的完整加密与解密链路：
  - 发送方：生成一次性 AES 会话密钥 → AES-GCM 加密明文 → RSA 加密会话密钥 → 打包为密文消息。
  - 接收方：RSA 解密会话密钥 → AES-GCM 解密正文 → 返回明文和调试信息。

设计理由：
  - RSA（非对称加密）运算慢但可以安全地传递密钥，因此仅用于"锁住"AES 会话密钥。
  - AES-GCM（对称加密）运算快、支持任意长度消息，因此用于加密实际的聊天正文。
  - 每条消息使用独立的一次性 AES 密钥，即使某条消息的密钥泄露也不影响其他消息。
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import rsa

import aes_core
import rsa_core


def encrypt_chat_message(
    plaintext: str,
    peer_public_key: rsa.RSAPublicKey,
    local_key_manager: rsa_core.RSAKeyManager | None = None,
) -> dict[str, object]:
    """
    对一条聊天消息执行混合加密。

    流程：
      1. 生成 256 位一次性 AES 会话密钥。
      2. 使用 AES-GCM 加密明文。
      3. 使用对方的 RSA 公钥加密 AES 会话密钥（wrapped_key）。
      4. 将 wrapped_key、nonce、ciphertext 打包为字典，附带 debug 信息。

    :param plaintext: 要发送的明文消息。
    :param peer_public_key: 接收方的 RSA 公钥对象。
    :param local_key_manager: 可选，用于获取本地公钥指纹写入 debug。
    :return: 包含 wrapped_key / nonce / ciphertext / debug 的字典。
    """
    if not plaintext:
        raise ValueError("消息明文不能为空。")

    # 步骤 1：生成一次性 AES-256 会话密钥
    session_key = aes_core.generate_aes_key(256)

    # 步骤 2：用 AES-GCM 加密明文
    aes_result = aes_core.encrypt_text(plaintext, session_key)

    # 步骤 3：用接收方 RSA 公钥加密 AES 会话密钥
    wrapped_key_bytes = rsa_core.encrypt_bytes(session_key, peer_public_key)
    wrapped_key_b64 = base64.b64encode(wrapped_key_bytes).decode("ascii")

    # 步骤 4：组装输出
    peer_fp = rsa_core.get_public_key_fingerprint(peer_public_key)
    sender_fp = ""
    if local_key_manager and local_key_manager.has_public_key():
        sender_fp = local_key_manager.get_local_public_key_fingerprint()

    return {
        "wrapped_key": wrapped_key_b64,
        "nonce": aes_result["nonce"],
        "ciphertext": aes_result["ciphertext"],
        "debug": {
            "plaintext_length": len(plaintext),
            "ciphertext_length": len(aes_result["ciphertext"]),
            "wrapped_key_length": len(wrapped_key_b64),
            "nonce_length": len(aes_result["nonce"]),
            "session_key_bits": 256,
            "peer_key_fingerprint": peer_fp,
            "sender_key_fingerprint": sender_fp,
        },
    }


def decrypt_chat_message(
    message_payload: dict[str, object],
    local_private_key: rsa.RSAPrivateKey,
) -> dict[str, object]:
    """
    对接收到的混合加密消息执行解密。

    流程：
      1. 使用本地 RSA 私钥解密 wrapped_key，得到 AES 会话密钥。
      2. 使用 AES-GCM 和还原的会话密钥解密正文。
      3. 返回明文和调试信息。

    :param message_payload: 包含 wrapped_key / nonce / ciphertext 的字典。
    :param local_private_key: 接收方的 RSA 私钥对象。
    :return: 包含 plaintext 和 debug 信息的字典。
    :raises ValueError: 缺少必要字段时抛出。
    :raises cryptography.exceptions.InvalidTag: 密文被篡改时抛出。
    """
    for field in ("wrapped_key", "nonce", "ciphertext"):
        if field not in message_payload:
            raise ValueError(f"消息缺少必要字段: {field}")

    wrapped_key_b64 = str(message_payload["wrapped_key"])
    nonce_b64 = str(message_payload["nonce"])
    ciphertext_b64 = str(message_payload["ciphertext"])

    # 步骤 1：RSA 解密 AES 会话密钥
    wrapped_key_bytes = base64.b64decode(wrapped_key_b64)
    session_key = rsa_core.decrypt_bytes(wrapped_key_bytes, local_private_key)

    # 步骤 2：AES-GCM 解密正文
    cipher_payload = {"nonce": nonce_b64, "ciphertext": ciphertext_b64}
    plaintext = aes_core.decrypt_text(cipher_payload, session_key)

    return {
        "plaintext": plaintext,
        "debug": {
            "plaintext_length": len(plaintext),
            "ciphertext_length": len(ciphertext_b64),
            "wrapped_key_length": len(wrapped_key_b64),
            "nonce_length": len(nonce_b64),
        },
    }
