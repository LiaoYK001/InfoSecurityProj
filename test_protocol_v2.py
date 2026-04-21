"""
协议增强校验单元测试。

覆盖二阶段新增的 parse_message 校验规则：
  - payload 必须是 dict
  - payload 必须包含各消息类型所要求的必要字段
  - 需要 receiver_id 的消息类型不能为空
"""

from __future__ import annotations

import json
import unittest

import chat_protocol


class TestPayloadValidation(unittest.TestCase):
    """payload 字段校验测试。"""

    def test_payload_not_dict_raises(self):
        """payload 如果不是 dict 应抛出 ValueError。"""
        raw = json.dumps({
            "type": "register",
            "sender_id": "alice",
            "payload": "not_a_dict",
        })
        with self.assertRaises(ValueError, msg="payload 必须是 JSON 对象"):
            chat_protocol.parse_message(raw)

    def test_payload_is_list_raises(self):
        """payload 如果是 list 应抛出 ValueError。"""
        raw = json.dumps({
            "type": "register",
            "sender_id": "alice",
            "payload": [1, 2, 3],
        })
        with self.assertRaises(ValueError):
            chat_protocol.parse_message(raw)

    def test_register_missing_public_key(self):
        """register 消息 payload 缺少 public_key 应抛出。"""
        raw = json.dumps({
            "type": "register",
            "sender_id": "alice",
            "payload": {},
        })
        with self.assertRaises(ValueError, msg="payload 缺少字段: public_key"):
            chat_protocol.parse_message(raw)

    def test_chat_message_missing_fields(self):
        """chat_message 缺少 wrapped_key/nonce/ciphertext 应抛出。"""
        # 缺少 ciphertext
        raw = json.dumps({
            "type": "chat_message",
            "sender_id": "alice",
            "receiver_id": "bob",
            "payload": {"wrapped_key": "abc", "nonce": "def"},
        })
        with self.assertRaises(ValueError, msg="payload 缺少字段: ciphertext"):
            chat_protocol.parse_message(raw)

    def test_error_missing_message(self):
        """error 消息 payload 缺少 message 应抛出。"""
        raw = json.dumps({
            "type": "error",
            "sender_id": "server",
            "payload": {},
        })
        with self.assertRaises(ValueError, msg="payload 缺少字段: message"):
            chat_protocol.parse_message(raw)

    def test_ack_missing_ack_for(self):
        """ack 消息 payload 缺少 ack_for 应抛出。"""
        raw = json.dumps({
            "type": "ack",
            "sender_id": "alice",
            "receiver_id": "bob",
            "payload": {},
        })
        with self.assertRaises(ValueError, msg="payload 缺少字段: ack_for"):
            chat_protocol.parse_message(raw)

    def test_user_list_missing_users(self):
        """user_list 消息 payload 缺少 users 应抛出。"""
        raw = json.dumps({
            "type": "user_list",
            "sender_id": "server",
            "payload": {},
        })
        with self.assertRaises(ValueError):
            chat_protocol.parse_message(raw)

    def test_heartbeat_empty_payload_ok(self):
        """heartbeat 空 payload 应正常通过。"""
        raw = json.dumps({
            "type": "heartbeat",
            "sender_id": "alice",
            "payload": {},
        })
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["type"], "heartbeat")

    def test_strict_payload_false_skips_validation(self):
        """strict_payload=False 时不校验 payload 字段。"""
        raw = json.dumps({
            "type": "register",
            "sender_id": "alice",
            "payload": {},
        })
        # 不应抛出
        msg = chat_protocol.parse_message(raw, strict_payload=False)
        self.assertEqual(msg["type"], "register")

    def test_valid_chat_message_passes(self):
        """合法的 chat_message 应正常解析。"""
        raw = json.dumps({
            "type": "chat_message",
            "sender_id": "alice",
            "receiver_id": "bob",
            "payload": {"wrapped_key": "a", "nonce": "b", "ciphertext": "c"},
        })
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["type"], "chat_message")


class TestReceiverIdValidation(unittest.TestCase):
    """receiver_id 必填校验测试。"""

    def test_chat_message_missing_receiver_raises(self):
        """chat_message 缺少 receiver_id 应抛出。"""
        raw = json.dumps({
            "type": "chat_message",
            "sender_id": "alice",
            "payload": {"wrapped_key": "a", "nonce": "b", "ciphertext": "c"},
        })
        with self.assertRaises(ValueError, msg="需要提供 receiver_id"):
            chat_protocol.parse_message(raw)

    def test_public_key_missing_receiver_raises(self):
        """public_key 缺少 receiver_id 应抛出。"""
        raw = json.dumps({
            "type": "public_key",
            "sender_id": "alice",
            "payload": {"public_key": "PEM"},
        })
        with self.assertRaises(ValueError, msg="需要提供 receiver_id"):
            chat_protocol.parse_message(raw)

    def test_ack_missing_receiver_raises(self):
        """ack 缺少 receiver_id 应抛出。"""
        raw = json.dumps({
            "type": "ack",
            "sender_id": "alice",
            "payload": {"ack_for": "chat_message"},
        })
        with self.assertRaises(ValueError, msg="需要提供 receiver_id"):
            chat_protocol.parse_message(raw)

    def test_register_no_receiver_ok(self):
        """register 不需要 receiver_id，应正常通过。"""
        raw = json.dumps({
            "type": "register",
            "sender_id": "alice",
            "payload": {"public_key": "PEM"},
        })
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["receiver_id"], "")

    def test_heartbeat_no_receiver_ok(self):
        """heartbeat 不需要 receiver_id，应正常通过。"""
        raw = json.dumps({
            "type": "heartbeat",
            "sender_id": "alice",
            "payload": {},
        })
        msg = chat_protocol.parse_message(raw)
        self.assertEqual(msg["receiver_id"], "")


class TestProtocolConstants(unittest.TestCase):
    """协议常量与辅助数据结构测试。"""

    def test_all_types_have_payload_rules(self):
        """所有合法消息类型都应在 _PAYLOAD_REQUIRED_FIELDS 中有条目。"""
        for msg_type in chat_protocol.VALID_TYPES:
            self.assertIn(
                msg_type,
                chat_protocol._PAYLOAD_REQUIRED_FIELDS,
                f"消息类型 {msg_type} 缺少 payload 字段规则",
            )

    def test_requires_receiver_subset_of_valid_types(self):
        """_REQUIRES_RECEIVER 应是 VALID_TYPES 的子集。"""
        self.assertTrue(
            chat_protocol._REQUIRES_RECEIVER.issubset(chat_protocol.VALID_TYPES)
        )


if __name__ == "__main__":
    unittest.main()
