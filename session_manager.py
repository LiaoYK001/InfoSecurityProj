"""
会话管理器。

本模块统一封装密钥生命周期和聊天消息的加解密行为，为 GUI 提供简单的入口：
  - 管理本地 RSA 密钥对。
  - 管理多个对端（peer）的公钥。
  - 对消息调用 message_crypto 进行混合加密 / 解密。

设计目的：
  - GUI 不需要直接接触 rsa_core / aes_core / message_crypto，只需调用本模块。
  - 支持多联系人场景（每个 peer_id 对应一把公钥）。
"""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import rsa

import message_crypto
import rsa_core


class SessionManager:
    """
    密钥与加解密会话的统一管理器。

    典型使用流程：
      1. generate_local_keys() 或 load_local_private_key() 初始化本地密钥。
      2. set_peer_public_key(peer_id, pem) 导入对方公钥。
      3. encrypt_for_peer(peer_id, plaintext) 加密消息。
      4. decrypt_from_message(payload) 解密收到的消息。
    """

    def __init__(self) -> None:
        self._key_manager = rsa_core.RSAKeyManager()
        # peer_id → RSA 公钥对象
        self._peer_keys: dict[str, rsa.RSAPublicKey] = {}

    # -------------------- 本地密钥管理 --------------------

    def generate_local_keys(self, key_size: int = 2048) -> None:
        """
        生成本地 RSA 密钥对。

        :param key_size: 密钥长度（位），默认 2048。
        """
        self._key_manager.generate_keys(key_size)

    def load_local_private_key(self, file_path: str) -> None:
        """
        从文件加载本地私钥（会自动推导公钥）。

        :param file_path: 私钥 PEM 文件路径。
        """
        self._key_manager.load_private_key(file_path)

    def has_local_keys(self) -> bool:
        """本地是否已拥有密钥对。"""
        return self._key_manager.has_private_key() and self._key_manager.has_public_key()

    def export_local_public_key(self) -> str:
        """
        导出本地公钥的 PEM 文本。

        :return: PEM 格式的公钥字符串。
        """
        return self._key_manager.export_public_key_string()

    def get_local_fingerprint(self) -> str:
        """获取本地公钥的 SHA-256 短指纹。"""
        return self._key_manager.get_local_public_key_fingerprint()

    # -------------------- 对端公钥管理 --------------------

    def set_peer_public_key(self, peer_id: str, public_key_pem: str) -> None:
        """
        导入指定对端用户的公钥。

        :param peer_id: 对方用户 ID。
        :param public_key_pem: 对方公钥 PEM 文本。
        """
        pub_key = rsa_core.load_public_key_from_pem_text(public_key_pem)
        self._peer_keys[peer_id] = pub_key

    def get_peer_public_key(self, peer_id: str) -> rsa.RSAPublicKey | None:
        """获取指定对端的公钥对象，未导入则返回 None。"""
        return self._peer_keys.get(peer_id)

    def has_peer_public_key(self, peer_id: str) -> bool:
        """是否已导入指定对端的公钥。"""
        return peer_id in self._peer_keys

    def get_peer_fingerprint(self, peer_id: str) -> str | None:
        """获取指定对端公钥的 SHA-256 短指纹，未导入则返回 None。"""
        pub_key = self._peer_keys.get(peer_id)
        if pub_key is None:
            return None
        return rsa_core.get_public_key_fingerprint(pub_key)

    def get_all_peer_ids(self) -> list[str]:
        """返回所有已知对端用户 ID 列表。"""
        return list(self._peer_keys.keys())

    # -------------------- 加密 / 解密 --------------------

    def encrypt_for_peer(self, peer_id: str, plaintext: str) -> dict[str, object]:
        """
        使用混合加密为指定对端加密一条消息。

        :param peer_id: 接收方用户 ID。
        :param plaintext: 消息明文。
        :return: 密文字典（wrapped_key / nonce / ciphertext / debug）。
        :raises ValueError: 对端公钥未导入时抛出。
        """
        peer_pub = self._peer_keys.get(peer_id)
        if peer_pub is None:
            raise ValueError(f"尚未导入用户 {peer_id} 的公钥，无法加密。")

        return message_crypto.encrypt_chat_message(
            plaintext, peer_pub, self._key_manager
        )

    def decrypt_from_message(self, message_payload: dict[str, object]) -> dict[str, object]:
        """
        解密收到的混合加密消息。

        :param message_payload: 包含 wrapped_key / nonce / ciphertext 的字典。
        :return: 包含 plaintext 和 debug 的字典。
        """
        return message_crypto.decrypt_chat_message(
            message_payload,
            self._key_manager.require_private_key(),
        )

    # -------------------- 文件数据加密 / 解密 --------------------

    def encrypt_file_for_peer(self, peer_id: str, file_bytes: bytes) -> dict[str, object]:
        """
        使用混合加密为指定对端加密文件数据。

        :param peer_id: 接收方用户 ID。
        :param file_bytes: 文件原始字节。
        :return: 密文字典（wrapped_key / nonce / ciphertext / debug）。
        :raises ValueError: 对端公钥未导入时抛出。
        """
        peer_pub = self._peer_keys.get(peer_id)
        if peer_pub is None:
            raise ValueError(f"尚未导入用户 {peer_id} 的公钥，无法加密。")

        return message_crypto.encrypt_file_data(
            file_bytes, peer_pub, self._key_manager
        )

    def decrypt_file_from_message(self, message_payload: dict[str, object]) -> dict[str, object]:
        """
        解密收到的混合加密文件数据。

        :param message_payload: 包含 wrapped_key / nonce / ciphertext 的字典。
        :return: 包含 file_bytes(bytes) 和 debug 的字典。
        """
        return message_crypto.decrypt_file_data(
            message_payload,
            self._key_manager.require_private_key(),
        )
