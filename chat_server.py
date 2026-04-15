"""
聊天中继服务端（盲转发模式）。

本服务端基于 WebSocket 实现，核心设计原则：
  - 服务端**只做消息路由和转发**，绝不解密任何 payload 内容。
  - 服务端不持有任何用户的私钥，也不存储聊天历史。
  - 日志只记录消息类型、发送方、接收方和 payload 长度，不打印明文。
  - 当有用户上线/下线时，向所有在线用户广播最新的用户列表（含公钥），
    以便客户端自动获取对方公钥进行加密。

启动方式：
    python chat_server.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

import websockets
from websockets.asyncio.server import Server, ServerConnection

import chat_protocol

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ChatServer")


class ChatRelayServer:
    """
    最小可运行的 WebSocket 聊天中继服务端。

    职责：
      1. 接收客户端的 register 消息，记录 user_id ↔ WebSocket 映射和公钥。
      2. 收到 chat_message 后直接按 receiver_id 转发，不解密 payload。
      3. 收到 public_key 消息后转发给目标用户。
      4. 维护在线用户列表，上下线时广播更新。
    """

    def __init__(self) -> None:
        # user_id → WebSocket 连接对象
        self.clients: dict[str, ServerConnection] = {}
        # user_id → 公钥 PEM 文本
        self.public_keys: dict[str, str] = {}

    async def start(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """启动 WebSocket 服务端并持续监听。"""
        logger.info("服务端启动: ws://%s:%d", host, port)
        async with websockets.serve(self.handle_connection, host, port) as server:
            await server.serve_forever()

    async def handle_connection(self, websocket: ServerConnection) -> None:
        """
        处理单个客户端连接的完整生命周期。
        连接建立后等待消息，连接断开后清理资源。
        """
        user_id: str | None = None
        try:
            async for raw_message in websocket:
                try:
                    msg = chat_protocol.parse_message(str(raw_message))
                except ValueError as e:
                    logger.warning("收到非法消息: %s", e)
                    await self._safe_send_ws(websocket, chat_protocol.make_error_message(str(e)))
                    continue

                msg_type = msg["type"]
                sender_id = str(msg["sender_id"])

                # 日志只记录元信息，不记录 payload 内容
                payload_len = len(json.dumps(msg.get("payload", {})))
                logger.info(
                    "收到消息: type=%s sender=%s receiver=%s payload_len=%d",
                    msg_type, sender_id, msg.get("receiver_id", ""), payload_len,
                )

                if msg_type == chat_protocol.MSG_REGISTER:
                    user_id = sender_id
                    await self._handle_register(msg, websocket)
                elif msg_type == chat_protocol.MSG_CHAT_MESSAGE:
                    await self._handle_chat_message(msg)
                elif msg_type == chat_protocol.MSG_PUBLIC_KEY:
                    await self._handle_public_key_message(msg)
                elif msg_type == chat_protocol.MSG_HEARTBEAT:
                    pass  # 心跳包不需要处理
                else:
                    logger.info("忽略无需服务端处理的消息类型: %s", msg_type)

        except websockets.exceptions.ConnectionClosed:
            logger.info("连接关闭: user=%s", user_id or "unknown")
        finally:
            if user_id:
                self._cleanup_disconnected_client(user_id)
                await self._broadcast_user_list()

    async def _handle_register(self, msg: dict, websocket: ServerConnection) -> None:
        """
        处理客户端注册消息。
        记录用户 ID、WebSocket 连接和公钥，然后向所有客户端广播更新的用户列表。
        """
        sender_id = str(msg["sender_id"])
        payload = msg.get("payload", {})
        public_key_pem = payload.get("public_key", "")

        self.clients[sender_id] = websocket
        if public_key_pem:
            self.public_keys[sender_id] = public_key_pem

        logger.info("用户注册成功: %s (在线人数: %d)", sender_id, len(self.clients))
        await self._broadcast_user_list()

    async def _handle_chat_message(self, msg: dict) -> None:
        """
        处理聊天消息：直接盲转发给目标用户。
        服务端不解密 payload，只读取 receiver_id 进行路由。
        """
        receiver_id = str(msg.get("receiver_id", ""))
        sender_id = str(msg["sender_id"])

        if not receiver_id:
            logger.warning("聊天消息缺少 receiver_id, sender=%s", sender_id)
            return

        # 将完整消息原样转发
        raw = json.dumps(msg, ensure_ascii=False)
        await self._safe_send(receiver_id, raw)

    async def _handle_public_key_message(self, msg: dict) -> None:
        """处理公钥交换消息：转发给目标用户。"""
        receiver_id = str(msg.get("receiver_id", ""))
        if receiver_id:
            raw = json.dumps(msg, ensure_ascii=False)
            await self._safe_send(receiver_id, raw)

    async def _safe_send(self, receiver_id: str, raw_message: str) -> None:
        """安全地向指定用户发送消息，连接不存在或已断开时忽略。"""
        ws = self.clients.get(receiver_id)
        if ws is None:
            logger.warning("目标用户不在线: %s", receiver_id)
            return
        await self._safe_send_ws(ws, raw_message)

    async def _safe_send_ws(self, ws: ServerConnection, raw_message: str) -> None:
        """安全地通过 WebSocket 连接发送消息。"""
        try:
            await ws.send(raw_message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("发送失败：连接已关闭。")

    def _cleanup_disconnected_client(self, user_id: str) -> None:
        """清理断开连接的客户端资源。"""
        self.clients.pop(user_id, None)
        self.public_keys.pop(user_id, None)
        logger.info("用户下线: %s (在线人数: %d)", user_id, len(self.clients))

    async def _broadcast_user_list(self) -> None:
        """向所有在线用户广播当前在线用户列表（含公钥）。"""
        msg = chat_protocol.make_user_list_message(self.public_keys)
        # 并发发送给所有客户端
        tasks = [self._safe_send(uid, msg) for uid in list(self.clients.keys())]
        if tasks:
            await asyncio.gather(*tasks)


def main() -> None:
    """命令行入口：解析参数并启动服务端。"""
    parser = argparse.ArgumentParser(description="加密聊天中继服务端")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="监听端口 (默认: 8765)")
    args = parser.parse_args()

    server = ChatRelayServer()
    asyncio.run(server.start(args.host, args.port))


if __name__ == "__main__":
    main()
