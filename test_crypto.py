"""
密码模块单元测试。

覆盖范围：
  - AES-GCM 加解密闭环（aes_core）
  - RSA 公钥指纹（rsa_core.get_public_key_fingerprint）
  - 混合加密闭环（message_crypto）
"""

from __future__ import annotations

import unittest

import aes_core
import message_crypto
import rsa_core


class TestAESCore(unittest.TestCase):
    """AES-GCM 加解密测试。"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密后解密应还原为原始明文。"""
        key = aes_core.generate_aes_key(256)
        plaintext = "你好，世界！Hello AES-GCM 🔐"
        payload = aes_core.encrypt_text(plaintext, key)
        result = aes_core.decrypt_text(payload, key)
        self.assertEqual(result, plaintext)

    def test_different_nonce_each_time(self):
        """对相同明文加密两次，nonce 应不同。"""
        key = aes_core.generate_aes_key(256)
        p1 = aes_core.encrypt_text("test", key)
        p2 = aes_core.encrypt_text("test", key)
        self.assertNotEqual(p1["nonce"], p2["nonce"])

    def test_empty_plaintext_raises(self):
        """空明文应抛出 ValueError。"""
        key = aes_core.generate_aes_key(256)
        with self.assertRaises(ValueError):
            aes_core.encrypt_text("", key)

    def test_invalid_key_length_raises(self):
        """非法密钥长度应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            aes_core.generate_aes_key(64)

    def test_wrong_key_raises(self):
        """用错误密钥解密应抛出异常（密文完整性校验失败）。"""
        key1 = aes_core.generate_aes_key(256)
        key2 = aes_core.generate_aes_key(256)
        payload = aes_core.encrypt_text("secret", key1)
        with self.assertRaises(Exception):
            aes_core.decrypt_text(payload, key2)

    def test_tampered_ciphertext_raises(self):
        """篡改密文应导致解密失败。"""
        key = aes_core.generate_aes_key(256)
        payload = aes_core.encrypt_text("secret", key)
        # 篡改密文的最后一个字符
        ct = payload["ciphertext"]
        payload["ciphertext"] = ct[:-1] + ("A" if ct[-1] != "A" else "B")
        with self.assertRaises(Exception):
            aes_core.decrypt_text(payload, key)

    def test_key_sizes(self):
        """128/192/256 位密钥均应正常工作。"""
        for bits in (128, 192, 256):
            key = aes_core.generate_aes_key(bits)
            self.assertEqual(len(key), bits // 8)
            payload = aes_core.encrypt_text("test", key)
            self.assertEqual(aes_core.decrypt_text(payload, key), "test")


class TestRSAFingerprint(unittest.TestCase):
    """RSA 公钥指纹测试。"""

    def test_fingerprint_format(self):
        """指纹应为 16 位十六进制字符串。"""
        _, pub = rsa_core.generate_rsa_key_pair(1024)
        fp = rsa_core.get_public_key_fingerprint(pub)
        self.assertEqual(len(fp), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))

    def test_different_keys_different_fingerprints(self):
        """不同密钥对的公钥指纹应不同。"""
        _, pub1 = rsa_core.generate_rsa_key_pair(1024)
        _, pub2 = rsa_core.generate_rsa_key_pair(1024)
        fp1 = rsa_core.get_public_key_fingerprint(pub1)
        fp2 = rsa_core.get_public_key_fingerprint(pub2)
        self.assertNotEqual(fp1, fp2)

    def test_key_manager_fingerprints(self):
        """RSAKeyManager 上的指纹方法应正常返回。"""
        km = rsa_core.RSAKeyManager()
        km.generate_keys(1024)
        self.assertEqual(len(km.get_local_public_key_fingerprint()), 16)
        self.assertIsNone(km.get_peer_public_key_fingerprint())

        # 导入对方公钥后应能获取指纹
        _, peer_pub = rsa_core.generate_rsa_key_pair(1024)
        km.peer_public_key = peer_pub
        self.assertIsNotNone(km.get_peer_public_key_fingerprint())


class TestMessageCrypto(unittest.TestCase):
    """混合加密（RSA + AES-GCM）闭环测试。"""

    def setUp(self):
        """模拟 Alice 和 Bob 各自生成密钥对。"""
        self.alice_km = rsa_core.RSAKeyManager()
        self.alice_km.generate_keys(2048)
        self.bob_km = rsa_core.RSAKeyManager()
        self.bob_km.generate_keys(2048)
        # 互换公钥
        self.alice_km.peer_public_key = self.bob_km.public_key
        self.bob_km.peer_public_key = self.alice_km.public_key

    def test_encrypt_decrypt_roundtrip(self):
        """Alice 用 Bob 公钥加密，Bob 用自己私钥解密，应还原明文。"""
        plaintext = "Hello Bob! 这是一条加密消息。"
        encrypted = message_crypto.encrypt_chat_message(
            plaintext,
            self.bob_km.require_public_key(),
            self.alice_km,
        )
        # 验证输出结构
        for field in ("wrapped_key", "nonce", "ciphertext", "debug"):
            self.assertIn(field, encrypted)

        decrypted = message_crypto.decrypt_chat_message(
            encrypted,
            self.bob_km.require_private_key(),
        )
        self.assertEqual(decrypted["plaintext"], plaintext)

    def test_wrong_private_key_fails(self):
        """用 Alice 的私钥尝试解密发给 Bob 的消息应失败。"""
        encrypted = message_crypto.encrypt_chat_message(
            "secret",
            self.bob_km.require_public_key(),
        )
        with self.assertRaises(Exception):
            message_crypto.decrypt_chat_message(
                encrypted,
                self.alice_km.require_private_key(),
            )

    def test_empty_message_raises(self):
        """空消息应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            message_crypto.encrypt_chat_message(
                "",
                self.bob_km.require_public_key(),
            )

    def test_debug_info_present(self):
        """加密和解密结果都应包含 debug 字段。"""
        plaintext = "debug test"
        enc = message_crypto.encrypt_chat_message(
            plaintext,
            self.bob_km.require_public_key(),
            self.alice_km,
        )
        enc_debug = enc["debug"]
        assert isinstance(enc_debug, dict)
        self.assertIn("peer_key_fingerprint", enc_debug)
        self.assertIn("sender_key_fingerprint", enc_debug)

        dec = message_crypto.decrypt_chat_message(
            enc,
            self.bob_km.require_private_key(),
        )
        dec_debug = dec["debug"]
        assert isinstance(dec_debug, dict)
        self.assertEqual(dec_debug["plaintext_length"], len(plaintext))

    def test_long_message(self):
        """长消息应正常加解密（AES-GCM 无长度限制）。"""
        plaintext = "A" * 10000
        enc = message_crypto.encrypt_chat_message(
            plaintext,
            self.bob_km.require_public_key(),
        )
        dec = message_crypto.decrypt_chat_message(
            enc,
            self.bob_km.require_private_key(),
        )
        self.assertEqual(dec["plaintext"], plaintext)


if __name__ == "__main__":
    unittest.main()
