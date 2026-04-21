"""
聊天协议模块单元测试。

覆盖范围：
  - 各类型消息的构造与解析闭环
  - 非法消息的校验与拒绝
"""

from __future__ import annotations

import json
import unittest

import chat_protocol


class TestProtocolBuild(unittest.TestCase):
    """消息构造测试。"""

    def test_register_message(self):
        """注册消息应包含正确的 type 和公钥。"""
        raw = chat_protocol.make_register_message("alice", "-----BEGIN PUBLIC KEY-----")
        msg = json.loads(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_REGISTER)
        self.assertEqual(msg["sender_id"], "alice")
        self.assertEqual(msg["payload"]["public_key"], "-----BEGIN PUBLIC KEY-----")
        self.assertIn("timestamp", msg)

    def test_chat_message(self):
        """聊天消息应包含 sender_id、receiver_id 和 payload。"""
        payload = {"wrapped_key": "abc", "nonce": "def", "ciphertext": "ghi"}
        raw = chat_protocol.make_chat_message("alice", "bob", payload)
        msg = json.loads(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_CHAT_MESSAGE)
        self.assertEqual(msg["sender_id"], "alice")
        self.assertEqual(msg["receiver_id"], "bob")
        self.assertEqual(msg["payload"]["wrapped_key"], "abc")

    def test_public_key_message(self):
        """公钥消息应正确设置发送方和接收方。"""
        raw = chat_protocol.make_public_key_message("alice", "bob", "PUBKEY")
        msg = json.loads(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_PUBLIC_KEY)
        self.assertEqual(msg["receiver_id"], "bob")
        self.assertEqual(msg["payload"]["public_key"], "PUBKEY")

    def test_ack_message(self):
        raw = chat_protocol.make_ack_message("bob", "alice", "chat_message")
        msg = json.loads(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_ACK)
        self.assertEqual(msg["payload"]["ack_for"], "chat_message")

    def test_error_message(self):
        raw = chat_protocol.make_error_message("something broke")
        msg = json.loads(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_ERROR)
        self.assertEqual(msg["sender_id"], "server")
        self.assertEqual(msg["payload"]["message"], "something broke")

    def test_heartbeat_message(self):
        raw = chat_protocol.make_heartbeat_message("alice")
        msg = json.loads(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_HEARTBEAT)
        self.assertEqual(msg["sender_id"], "alice")

    def test_user_list_message(self):
        users = {"alice": "PEM_A", "bob": "PEM_B"}
        raw = chat_protocol.make_user_list_message(users)
        msg = json.loads(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_USER_LIST)
        self.assertEqual(msg["payload"]["users"], users)


class TestProtocolParse(unittest.TestCase):
    """消息解析测试。"""

    def test_roundtrip(self):
        """构造后解析应还原原始字段。"""
        raw = chat_protocol.make_register_message("alice", "PK")
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["type"], chat_protocol.MSG_REGISTER)
        self.assertEqual(msg["sender_id"], "alice")

    def test_invalid_json_raises(self):
        """非法 JSON 应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            chat_protocol.parse_message("not json")

    def test_missing_type_raises(self):
        """缺少 type 字段应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            chat_protocol.parse_message('{"sender_id": "a", "payload": {}}')

    def test_missing_sender_id_raises(self):
        """缺少 sender_id 字段应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            chat_protocol.parse_message('{"type": "register", "payload": {}}')

    def test_unknown_type_raises(self):
        """未知消息类型应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            chat_protocol.parse_message(
                '{"type": "unknown_type", "sender_id": "a", "payload": {}}'
            )

    def test_not_object_raises(self):
        """非字典 JSON 应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            chat_protocol.parse_message("[1, 2, 3]")

    def test_receiver_id_defaults(self):
        """缺少 receiver_id 时应默认为空字符串。"""
        raw = '{"type": "heartbeat", "sender_id": "alice", "payload": {}}'
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["receiver_id"], "")


if __name__ == "__main__":
    unittest.main()
