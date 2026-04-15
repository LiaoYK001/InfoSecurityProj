"""
AES-GCM 对称加密模块。

本模块提供基于 AES-GCM（Galois/Counter Mode）的对称加密能力。
在本项目的混合加密体系中，AES-GCM 负责聊天消息正文的加密与解密：
  - 相比 RSA，AES 加解密速度快、适合处理任意长度的消息正文。
  - GCM 模式自带完整性校验（AEAD），无需额外 HMAC，能同时保证机密性和完整性。
  - RSA 仅用于安全地传递 AES 会话密钥（密钥交换），不直接加密正文。

所有输入输出的密文和 nonce 统一使用 Base64 编码，方便 JSON 序列化与网络传输。
"""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# AES-GCM 推荐的 nonce 长度（字节），12 字节 = 96 位，是 GCM 规范推荐值
_NONCE_BYTES = 12


def generate_aes_key(key_size_bits: int = 256) -> bytes:
    """
    生成一个随机的 AES 密钥。

    :param key_size_bits: 密钥长度（位），支持 128、192、256，默认 256。
    :return: 随机密钥字节串。
    :raises ValueError: 如果 key_size_bits 不在支持范围内。
    """
    if key_size_bits not in (128, 192, 256):
        raise ValueError(f"不支持的 AES 密钥长度: {key_size_bits}，仅支持 128/192/256。")
    return os.urandom(key_size_bits // 8)


def encrypt_text(plaintext: str, key: bytes) -> dict[str, str]:
    """
    使用 AES-GCM 加密一段明文字符串。

    加密流程：
      1. 随机生成 12 字节 nonce（保证每次加密结果不同）。
      2. 使用 AES-GCM 对 UTF-8 编码的明文进行加密。
      3. 将 nonce 和密文分别用 Base64 编码后返回。

    :param plaintext: 要加密的明文字符串（不能为空）。
    :param key: AES 密钥（16/24/32 字节）。
    :return: 包含 "nonce" 和 "ciphertext" 两个 Base64 字符串的字典。
    :raises ValueError: 明文为空或密钥长度非法时抛出。
    """
    if not plaintext:
        raise ValueError("明文不能为空。")
    _validate_key(key)

    nonce = os.urandom(_NONCE_BYTES)
    aesgcm = AESGCM(key)
    # AES-GCM encrypt 返回的密文已包含认证标签（tag），解密时自动校验
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    return {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ct).decode("ascii"),
    }


def decrypt_text(cipher_payload: dict[str, str], key: bytes) -> str:
    """
    使用 AES-GCM 解密密文并还原为明文字符串。

    解密流程：
      1. 从字典中取出 Base64 编码的 nonce 和 ciphertext。
      2. 使用相同的 AES 密钥和 nonce 进行解密。
      3. GCM 会自动校验认证标签，若密文被篡改则抛出异常。

    :param cipher_payload: 包含 "nonce" 和 "ciphertext" 的字典（Base64 编码）。
    :param key: 与加密时相同的 AES 密钥。
    :return: 解密后的明文字符串。
    :raises ValueError: 字典缺少必要字段或密钥非法时抛出。
    :raises cryptography.exceptions.InvalidTag: 密文被篡改或密钥不匹配时抛出。
    """
    _validate_key(key)
    if "nonce" not in cipher_payload or "ciphertext" not in cipher_payload:
        raise ValueError("cipher_payload 缺少 'nonce' 或 'ciphertext' 字段。")

    nonce = base64.b64decode(cipher_payload["nonce"])
    ct = base64.b64decode(cipher_payload["ciphertext"])

    aesgcm = AESGCM(key)
    plaintext_bytes = aesgcm.decrypt(nonce, ct, None)
    return plaintext_bytes.decode("utf-8")


def _validate_key(key: bytes) -> None:
    """内部辅助：校验 AES 密钥长度是否合法。"""
    if not isinstance(key, bytes) or len(key) not in (16, 24, 32):
        raise ValueError(f"AES 密钥长度必须为 16/24/32 字节，当前为 {len(key) if isinstance(key, bytes) else type(key)}。")
