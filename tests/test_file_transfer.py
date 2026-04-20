"""
文件传输功能测试。

覆盖：
  - AES-GCM 字节加密/解密（encrypt_bytes / decrypt_bytes）
  - 混合加密文件数据（encrypt_file_data / decrypt_file_data）
  - 文件消息协议构造/解析
  - 分块逻辑
"""

from __future__ import annotations

import json
import os
import unittest

import aes_core
import chat_protocol
import message_crypto
import rsa_core


# ── AES-GCM 字节加密 ───────────────────────────────────

class TestAesBytesEncryption(unittest.TestCase):
    """AES-GCM 字节加密/解密。"""

    def setUp(self) -> None:
        self.key = aes_core.generate_aes_key(256)

    def test_encrypt_decrypt_roundtrip(self) -> None:
        data = b"Hello, this is binary data \x00\x01\x02\xff"
        result = aes_core.encrypt_bytes(data, self.key)
        self.assertIn("nonce", result)
        self.assertIn("ciphertext", result)
        decrypted = aes_core.decrypt_bytes(result, self.key)
        self.assertEqual(decrypted, data)

    def test_encrypt_empty_bytes(self) -> None:
        data = b""
        result = aes_core.encrypt_bytes(data, self.key)
        decrypted = aes_core.decrypt_bytes(result, self.key)
        self.assertEqual(decrypted, data)

    def test_encrypt_large_bytes(self) -> None:
        data = os.urandom(5 * 1024 * 1024)  # 5 MB
        result = aes_core.encrypt_bytes(data, self.key)
        decrypted = aes_core.decrypt_bytes(result, self.key)
        self.assertEqual(decrypted, data)

    def test_decrypt_tampered_ciphertext(self) -> None:
        data = b"sensitive data"
        result = aes_core.encrypt_bytes(data, self.key)
        # 篡改密文
        import base64
        ct_bytes = bytearray(base64.b64decode(result["ciphertext"]))
        ct_bytes[0] ^= 0xFF
        result["ciphertext"] = base64.b64encode(bytes(ct_bytes)).decode()
        with self.assertRaises(Exception):  # InvalidTag
            aes_core.decrypt_bytes(result, self.key)

    def test_type_error_for_non_bytes(self) -> None:
        with self.assertRaises(TypeError):
            aes_core.encrypt_bytes("not bytes", self.key)  # type: ignore[arg-type]

    def test_different_nonce_each_call(self) -> None:
        data = b"same data"
        r1 = aes_core.encrypt_bytes(data, self.key)
        r2 = aes_core.encrypt_bytes(data, self.key)
        self.assertNotEqual(r1["nonce"], r2["nonce"])


# ── 混合加密文件数据 ────────────────────────────────────

class TestFileDataCrypto(unittest.TestCase):
    """混合加密文件数据（RSA + AES-GCM）。"""

    def setUp(self) -> None:
        self.km = rsa_core.RSAKeyManager()
        self.km.generate_keys(2048)

    def test_encrypt_decrypt_roundtrip(self) -> None:
        data = b"test file content \x00\xff"
        encrypted = message_crypto.encrypt_file_data(
            data, self.km.public_key, self.km
        )
        self.assertIn("wrapped_key", encrypted)
        self.assertIn("nonce", encrypted)
        self.assertIn("ciphertext", encrypted)
        self.assertIn("debug", encrypted)

        result = message_crypto.decrypt_file_data(encrypted, self.km.private_key)
        self.assertEqual(result["file_bytes"], data)

    def test_encrypt_image_bytes(self) -> None:
        # 模拟 PNG 文件头
        png_header = b"\x89PNG\r\n\x1a\n" + os.urandom(1024)
        encrypted = message_crypto.encrypt_file_data(
            png_header, self.km.public_key
        )
        result = message_crypto.decrypt_file_data(encrypted, self.km.private_key)
        self.assertEqual(result["file_bytes"], png_header)

    def test_empty_file(self) -> None:
        data = b""
        encrypted = message_crypto.encrypt_file_data(data, self.km.public_key)
        result = message_crypto.decrypt_file_data(encrypted, self.km.private_key)
        self.assertEqual(result["file_bytes"], data)

    def test_large_file(self) -> None:
        data = os.urandom(2 * 1024 * 1024)  # 2 MB
        encrypted = message_crypto.encrypt_file_data(data, self.km.public_key)
        result = message_crypto.decrypt_file_data(encrypted, self.km.private_key)
        self.assertEqual(result["file_bytes"], data)

    def test_type_error_for_non_bytes(self) -> None:
        with self.assertRaises(TypeError):
            message_crypto.encrypt_file_data("not bytes", self.km.public_key)  # type: ignore[arg-type]


# ── 文件消息协议 ────────────────────────────────────────

class TestFileProtocol(unittest.TestCase):
    """文件传输协议消息构造/解析。"""

    def _dummy_encrypted(self) -> dict:
        return {
            "wrapped_key": "dW1teXdyYXBwZWQ=",
            "nonce": "bm9uY2VfMTIzNA==",
            "ciphertext": "Y2lwaGVydGV4dA==",
        }

    def test_make_parse_file_transfer(self) -> None:
        raw = chat_protocol.make_file_transfer_message(
            "alice", "bob", self._dummy_encrypted(),
            "photo.png", 12345, "image/png",
        )
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_FILE_TRANSFER)
        self.assertEqual(msg["sender_id"], "alice")
        self.assertEqual(msg["receiver_id"], "bob")
        p = msg["payload"]
        self.assertEqual(p["filename"], "photo.png")
        self.assertEqual(p["filesize"], 12345)
        self.assertEqual(p["mime_type"], "image/png")
        self.assertEqual(p["wrapped_key"], "dW1teXdyYXBwZWQ=")

    def test_make_parse_file_chunk(self) -> None:
        raw = chat_protocol.make_file_chunk_message(
            "alice", "bob", self._dummy_encrypted(),
            "uuid-123", 2, 10, "doc.pdf", 50000, "application/pdf",
        )
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_FILE_CHUNK)
        p = msg["payload"]
        self.assertEqual(p["transfer_id"], "uuid-123")
        self.assertEqual(p["chunk_index"], 2)
        self.assertEqual(p["total_chunks"], 10)
        self.assertEqual(p["filename"], "doc.pdf")

    def test_file_transfer_requires_receiver_id(self) -> None:
        payload = {
            **self._dummy_encrypted(),
            "filename": "f.txt", "filesize": 1, "mime_type": "text/plain",
        }
        raw = json.dumps({
            "type": "file_transfer",
            "sender_id": "alice",
            "receiver_id": "",
            "timestamp": "2024-01-01T00:00:00Z",
            "payload": payload,
        })
        with self.assertRaises(ValueError):
            chat_protocol.parse_message(raw)

    def test_file_chunk_payload_validation(self) -> None:
        # Missing transfer_id
        payload = {
            **self._dummy_encrypted(),
            "filename": "f.txt", "filesize": 1, "mime_type": "text/plain",
            "chunk_index": 0, "total_chunks": 1,
            # "transfer_id" missing
        }
        raw = json.dumps({
            "type": "file_chunk",
            "sender_id": "alice",
            "receiver_id": "bob",
            "timestamp": "2024-01-01T00:00:00Z",
            "payload": payload,
        })
        with self.assertRaises(ValueError):
            chat_protocol.parse_message(raw, strict_payload=True)


# ── 分块逻辑 ───────────────────────────────────────────

class TestChunking(unittest.TestCase):
    """分块加密/解密 → 拼装还原。"""

    CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB

    def setUp(self) -> None:
        self.km = rsa_core.RSAKeyManager()
        self.km.generate_keys(2048)

    def test_chunk_reassembly(self) -> None:
        """拆分 → 逐块加密 → 逐块解密 → 拼装 → 比对原文件。"""
        original = os.urandom(3 * 1024 * 1024 + 500)  # 3 MB + 500 bytes
        total_chunks = (len(original) + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
        self.assertEqual(total_chunks, 4)

        chunks_encrypted = []
        for i in range(total_chunks):
            chunk = original[i * self.CHUNK_SIZE : (i + 1) * self.CHUNK_SIZE]
            enc = message_crypto.encrypt_file_data(chunk, self.km.public_key)
            chunks_encrypted.append(enc)

        # 逐块解密
        chunks_decrypted = []
        for enc in chunks_encrypted:
            result = message_crypto.decrypt_file_data(enc, self.km.private_key)
            chunks_decrypted.append(result["file_bytes"])

        reassembled = b"".join(chunks_decrypted)
        self.assertEqual(reassembled, original)

    def test_chunk_count(self) -> None:
        for size, expected in [(0, 0), (1, 1), (self.CHUNK_SIZE, 1),
                               (self.CHUNK_SIZE + 1, 2), (5 * self.CHUNK_SIZE, 5)]:
            if size == 0:
                count = 0
            else:
                count = (size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
            self.assertEqual(count, expected, f"size={size}")


if __name__ == "__main__":
    unittest.main()
