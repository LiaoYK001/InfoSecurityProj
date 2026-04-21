"""
协议与服务端联调集成测试。

覆盖范围（二阶段任务 E）：
  - 注册流程：客户端注册后服务端正确维护在线状态。
  - 盲转发：服务端正确按 receiver_id 转发密文消息。
  - 公钥同步：公钥消息可在客户端之间传递。
  - 非法消息拒绝：服务端对非法输入返回 error。
  - 断线清理：客户端断开后服务端更新在线列表。
  - 未注册拒绝：未注册客户端发送业务消息被拒绝。
  - 心跳：心跳消息不产生错误。
  - 用户列表广播：用户上下线时所有客户端收到更新。

注意：这些测试直接操作 WebSocket 连接和 ChatRelayServer，
      不依赖 ChatClient 的线程封装，以隔离服务端行为。
"""

from __future__ import annotations

import asyncio
import json
import unittest

import websockets
from websockets.asyncio.server import serve as ws_serve

import chat_protocol
from chat_server import ChatRelayServer

# 测试端口，避免和生产冲突
TEST_HOST = "127.0.0.1"
TEST_PORT = 0  # 0 = 系统自动分配空闲端口


class IntegrationTestBase(unittest.TestCase):
    """集成测试基类：在每个测试方法内通过 asyncio.run 启停服务端。"""

    def run_async(self, coro):  # type: ignore[no-untyped-def]
        """包装 asyncio.run，自动启停事件循环。"""
        return asyncio.run(coro)

    async def _start_server(self) -> tuple[ChatRelayServer, object, int]:
        """启动 WebSocket 服务端，返回 (server_instance, ws_server, port)。"""
        server = ChatRelayServer(inactive_timeout=600)
        ws_server = await ws_serve(server.handle_connection, TEST_HOST, TEST_PORT)
        sock = list(ws_server.sockets)[0]
        port = sock.getsockname()[1]
        return server, ws_server, port

    async def _connect_and_register(
        self, url: str, user_id: str, public_key: str = "PK"
    ) -> websockets.ClientConnection:
        """连接并注册一个用户，返回 WebSocket 连接。"""
        ws = await websockets.connect(url)
        reg = chat_protocol.make_register_message(user_id, public_key)
        await ws.send(reg)
        return ws

    async def _recv_msg(self, ws: websockets.ClientConnection, timeout: float = 3.0) -> dict[str, object]:
        """从连接中接收并解析一条消息。"""
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        return chat_protocol.parse_message(str(raw), strict_payload=False)

    async def _drain_user_list(self, ws: websockets.ClientConnection) -> dict[str, object]:
        """接收直到拿到一条 user_list 消息。"""
        for _ in range(10):
            msg = await self._recv_msg(ws)
            if msg["type"] == chat_protocol.MSG_USER_LIST:
                return msg
        raise AssertionError("未收到 user_list 消息")


class TestRegistration(IntegrationTestBase):
    """注册流程测试。"""

    def test_single_register(self):
        """单用户注册后服务端维护在线状态，并广播 user_list。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws = await self._connect_and_register(url, "alice", "PEM_ALICE")
                try:
                    msg = await self._drain_user_list(ws)
                    payload = msg.get("payload", {})
                    assert isinstance(payload, dict)
                    users = payload.get("users", {})
                    assert isinstance(users, dict)
                    self.assertIn("alice", users)
                    self.assertEqual(users["alice"], "PEM_ALICE")
                finally:
                    await ws.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())

    def test_two_users_register(self):
        """两个用户注册后，双方都能收到包含彼此的 user_list。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws_a = await self._connect_and_register(url, "alice", "PEM_A")
                _ = await self._drain_user_list(ws_a)

                ws_b = await self._connect_and_register(url, "bob", "PEM_B")
                try:
                    msg_b = await self._drain_user_list(ws_b)
                    payload_b = msg_b.get("payload", {})
                    assert isinstance(payload_b, dict)
                    users_b = payload_b.get("users", {})
                    assert isinstance(users_b, dict)
                    self.assertIn("alice", users_b)
                    self.assertIn("bob", users_b)

                    msg_a = await self._drain_user_list(ws_a)
                    payload_a = msg_a.get("payload", {})
                    assert isinstance(payload_a, dict)
                    users_a = payload_a.get("users", {})
                    assert isinstance(users_a, dict)
                    self.assertIn("alice", users_a)
                    self.assertIn("bob", users_a)
                finally:
                    await ws_a.close()
                    await ws_b.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())

    def test_duplicate_register_replaces(self):
        """同一 user_id 重复注册，旧连接应被替换。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws_old = await self._connect_and_register(url, "alice", "PK1")
                _ = await self._drain_user_list(ws_old)

                ws_new = await self._connect_and_register(url, "alice", "PK2")
                _ = await self._drain_user_list(ws_new)

                self.assertEqual(len(server.clients), 1)
                self.assertEqual(server.public_keys.get("alice"), "PK2")

                await ws_new.close()
                try:
                    await ws_old.close()
                except Exception:
                    pass
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())


class TestBlindRelay(IntegrationTestBase):
    """盲转发测试。"""

    def test_chat_message_forwarded(self):
        """alice 发送密文给 bob，bob 应原样收到。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws_a = await self._connect_and_register(url, "alice")
                _ = await self._drain_user_list(ws_a)
                ws_b = await self._connect_and_register(url, "bob")
                _ = await self._drain_user_list(ws_b)
                _ = await self._drain_user_list(ws_a)

                payload = {"wrapped_key": "wk", "nonce": "nc", "ciphertext": "ct"}
                chat_msg = chat_protocol.make_chat_message("alice", "bob", payload)
                await ws_a.send(chat_msg)

                msg = await self._recv_msg(ws_b)
                self.assertEqual(msg["type"], chat_protocol.MSG_CHAT_MESSAGE)
                self.assertEqual(msg["sender_id"], "alice")
                p = msg.get("payload", {})
                assert isinstance(p, dict)
                self.assertEqual(p["wrapped_key"], "wk")
                self.assertEqual(p["nonce"], "nc")
                self.assertEqual(p["ciphertext"], "ct")

                await ws_a.close()
                await ws_b.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())

    def test_message_to_offline_user(self):
        """发送消息给不在线用户，发送方应收到 error。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws_a = await self._connect_and_register(url, "alice")
                _ = await self._drain_user_list(ws_a)

                payload = {"wrapped_key": "wk", "nonce": "nc", "ciphertext": "ct"}
                chat_msg = chat_protocol.make_chat_message("alice", "nobody", payload)
                await ws_a.send(chat_msg)

                msg = await self._recv_msg(ws_a)
                self.assertEqual(msg["type"], chat_protocol.MSG_ERROR)
                p = msg.get("payload", {})
                assert isinstance(p, dict)
                self.assertIn("不在线", str(p.get("message", "")))

                await ws_a.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())


class TestPublicKeySync(IntegrationTestBase):
    """公钥同步测试。"""

    def test_public_key_forwarded(self):
        """alice 向 bob 发送公钥，bob 应收到。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws_a = await self._connect_and_register(url, "alice")
                _ = await self._drain_user_list(ws_a)
                ws_b = await self._connect_and_register(url, "bob")
                _ = await self._drain_user_list(ws_b)
                _ = await self._drain_user_list(ws_a)

                pk_msg = chat_protocol.make_public_key_message("alice", "bob", "ALICE_PEM")
                await ws_a.send(pk_msg)

                msg = await self._recv_msg(ws_b)
                self.assertEqual(msg["type"], chat_protocol.MSG_PUBLIC_KEY)
                p = msg.get("payload", {})
                assert isinstance(p, dict)
                self.assertEqual(p["public_key"], "ALICE_PEM")

                await ws_a.close()
                await ws_b.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())


class TestInvalidMessages(IntegrationTestBase):
    """非法消息处理测试。"""

    def test_invalid_json_returns_error(self):
        """发送非法 JSON 应收到 error。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws = await websockets.connect(url)
                await ws.send("this is not json{{{")
                msg = await self._recv_msg(ws)
                self.assertEqual(msg["type"], chat_protocol.MSG_ERROR)
                await ws.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())

    def test_unknown_type_returns_error(self):
        """发送未知消息类型应收到 error。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws = await websockets.connect(url)
                await ws.send(json.dumps({
                    "type": "unknown_hack",
                    "sender_id": "evil",
                    "payload": {},
                }))
                msg = await self._recv_msg(ws)
                self.assertEqual(msg["type"], chat_protocol.MSG_ERROR)
                await ws.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())

    def test_unregistered_send_chat_rejected(self):
        """未注册客户端发送 chat_message 应被拒绝。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws = await websockets.connect(url)
                payload = {"wrapped_key": "a", "nonce": "b", "ciphertext": "c"}
                chat_msg = chat_protocol.make_chat_message("ghost", "bob", payload)
                await ws.send(chat_msg)
                msg = await self._recv_msg(ws)
                self.assertEqual(msg["type"], chat_protocol.MSG_ERROR)
                p = msg.get("payload", {})
                assert isinstance(p, dict)
                self.assertIn("注册", str(p.get("message", "")))
                await ws.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())


class TestDisconnectCleanup(IntegrationTestBase):
    """断线清理测试。"""

    def test_disconnect_removes_user(self):
        """客户端断开后，服务端应从在线列表中移除。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws_a = await self._connect_and_register(url, "alice")
                _ = await self._drain_user_list(ws_a)
                ws_b = await self._connect_and_register(url, "bob")
                _ = await self._drain_user_list(ws_b)
                _ = await self._drain_user_list(ws_a)

                # bob 断开
                await ws_b.close()
                await asyncio.sleep(0.3)

                # alice 应收到更新后的 user_list（不含 bob）
                msg = await self._drain_user_list(ws_a)
                payload = msg.get("payload", {})
                assert isinstance(payload, dict)
                users = payload.get("users", {})
                assert isinstance(users, dict)
                self.assertIn("alice", users)
                self.assertNotIn("bob", users)

                self.assertNotIn("bob", server.clients)
                self.assertNotIn("bob", server.public_keys)

                await ws_a.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())


class TestHeartbeat(IntegrationTestBase):
    """心跳消息测试。"""

    def test_heartbeat_no_error(self):
        """已注册客户端发送心跳不应收到错误。"""
        async def _test() -> None:
            server, ws_server, port = await self._start_server()
            url = f"ws://{TEST_HOST}:{port}"
            try:
                ws = await self._connect_and_register(url, "alice")
                _ = await self._drain_user_list(ws)

                hb = chat_protocol.make_heartbeat_message("alice")
                await ws.send(hb)
                await ws.send(hb)
                await asyncio.sleep(0.2)

                # 连接应仍然活跃
                self.assertIn("alice", server.clients)
                await ws.close()
            finally:
                ws_server.close()
                await ws_server.wait_closed()

        self.run_async(_test())


if __name__ == "__main__":
    unittest.main()
