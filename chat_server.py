"""
聊天中继服务端（盲转发模式）。

本服务端基于 WebSocket 实现，核心设计原则：
  - 服务端**只做消息路由和转发**，绝不解密任何 payload 内容。
  - 服务端不持有任何用户的私钥，也不存储聊天历史。
  - 日志只记录消息类型、发送方、接收方和 payload 长度，不打印明文。
  - 当有用户上线/下线时，向所有在线用户广播最新的用户列表（含公钥），
    以便客户端自动获取对方公钥进行加密。
  - 服务端跟踪每个用户的最后活跃时间，超时未活动则视为掉线并清理。

启动方式：
    python chat_server.py [--host HOST] [--port PORT] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time

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

# 默认不活跃超时（秒）。客户端应在此间隔内发送心跳。
DEFAULT_INACTIVE_TIMEOUT = 120


class ChatRelayServer:
    """
    最小可运行的 WebSocket 聊天中继服务端。

    职责：
      1. 接收客户端的 register 消息，记录 user_id ↔ WebSocket 映射和公钥。
      2. 收到 chat_message 后直接按 receiver_id 转发，不解密 payload。
      3. 收到 public_key 消息后转发给目标用户。
      4. 维护在线用户列表，上下线时广播更新。
      5. 拒绝未注册客户端发送 chat/public_key 等业务消息。
      6. 跟踪客户端最后活跃时间，定期清理超时连接。
    """

    def __init__(self, inactive_timeout: float = DEFAULT_INACTIVE_TIMEOUT) -> None:
        # user_id → WebSocket 连接对象
        self.clients: dict[str, ServerConnection] = {}
        # user_id → 公钥 PEM 文本
        self.public_keys: dict[str, str] = {}
        # user_id → 最后活跃时间（time.monotonic）
        self._last_active: dict[str, float] = {}
        # 不活跃超时阈值
        self._inactive_timeout = inactive_timeout

    async def start(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """启动 WebSocket 服务端并持续监听。"""
        logger.info("服务端启动: ws://%s:%d (不活跃超时: %ds)", host, port, int(self._inactive_timeout))
        async with websockets.serve(self.handle_connection, host, port) as server:
            # 同时启动超时巡检任务
            asyncio.ensure_future(self._inactive_checker())
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

                msg_type = str(msg["type"])
                sender_id = str(msg["sender_id"])

                # 日志只记录元信息，不记录 payload 内容
                payload = msg.get("payload", {})
                payload_len = len(json.dumps(payload, ensure_ascii=False)) if isinstance(payload, dict) else 0
                logger.info(
                    "收到消息: type=%s sender=%s receiver=%s payload_len=%d",
                    msg_type, sender_id, msg.get("receiver_id", ""), payload_len,
                )

                if msg_type == chat_protocol.MSG_REGISTER:
                    user_id = sender_id
                    await self._handle_register(msg, websocket)
                elif msg_type == chat_protocol.MSG_HEARTBEAT:
                    # 心跳包：刷新活跃时间即可
                    if user_id:
                        self._touch(user_id)
                elif not user_id or user_id not in self.clients:
                    # 未注册的客户端不允许发送业务消息
                    logger.warning("未注册客户端尝试发送 %s, sender=%s", msg_type, sender_id)
                    await self._safe_send_ws(
                        websocket,
                        chat_protocol.make_error_message("请先发送 register 消息完成注册。"),
                    )
                elif msg_type == chat_protocol.MSG_CHAT_MESSAGE:
                    await self._handle_chat_message(msg, sender_id)
                elif msg_type in (chat_protocol.MSG_FILE_TRANSFER,
                                  chat_protocol.MSG_FILE_CHUNK):
                    await self._handle_chat_message(msg, sender_id)
                elif msg_type == chat_protocol.MSG_PUBLIC_KEY:
                    await self._handle_public_key_message(msg)
                else:
                    logger.info("忽略无需服务端处理的消息类型: %s", msg_type)

        except websockets.exceptions.ConnectionClosed:
            logger.info("连接关闭: user=%s", user_id or "unknown")
        finally:
            if user_id:
                self._cleanup_disconnected_client(user_id)
                await self._broadcast_user_list()

    # -------------------- 消息处理器 --------------------

    async def _handle_register(self, msg: dict[str, object], websocket: ServerConnection) -> None:
        """
        处理客户端注册消息。
        记录用户 ID、WebSocket 连接和公钥，然后向所有客户端广播更新的用户列表。
        如果用户已注册，旧连接会被替换。
        """
        sender_id = str(msg["sender_id"])
        payload = msg.get("payload", {})
        public_key_pem = ""
        if isinstance(payload, dict):
            public_key_pem = str(payload.get("public_key", ""))

        # 若同一 user_id 重复注册，关闭旧连接
        old_ws = self.clients.get(sender_id)
        if old_ws is not None and old_ws is not websocket:
            logger.info("用户 %s 重复注册，关闭旧连接。", sender_id)
            try:
                await old_ws.close()
            except Exception:
                pass

        self.clients[sender_id] = websocket
        self._touch(sender_id)
        if public_key_pem:
            self.public_keys[sender_id] = public_key_pem

        logger.info("用户注册成功: %s (在线人数: %d)", sender_id, len(self.clients))
        await self._broadcast_user_list()

    async def _handle_chat_message(self, msg: dict[str, object], sender_id: str) -> None:
        """
        处理聊天消息：直接盲转发给目标用户。
        服务端不解密 payload，只读取 receiver_id 进行路由。
        如果目标用户不在线，向发送方返回错误消息。
        """
        receiver_id = str(msg.get("receiver_id", ""))

        if not receiver_id:
            logger.warning("聊天消息缺少 receiver_id, sender=%s", sender_id)
            return

        self._touch(sender_id)

        if receiver_id not in self.clients:
            # 目标用户不在线，通知发送方
            await self._safe_send(
                sender_id,
                chat_protocol.make_error_message(f"用户 {receiver_id} 不在线。"),
            )
            return

        # 将完整消息原样转发
        raw = json.dumps(msg, ensure_ascii=False)
        await self._safe_send(receiver_id, raw)

    async def _handle_public_key_message(self, msg: dict[str, object]) -> None:
        """处理公钥交换消息：转发给目标用户。"""
        receiver_id = str(msg.get("receiver_id", ""))
        sender_id = str(msg.get("sender_id", ""))
        self._touch(sender_id)
        if receiver_id:
            raw = json.dumps(msg, ensure_ascii=False)
            await self._safe_send(receiver_id, raw)

    # -------------------- 活跃时间跟踪 --------------------

    def _touch(self, user_id: str) -> None:
        """刷新指定用户的最后活跃时间。"""
        self._last_active[user_id] = time.monotonic()

    async def _inactive_checker(self) -> None:
        """
        定期检查不活跃连接并清理。
        每 30 秒巡检一次。
        """
        while True:
            await asyncio.sleep(30)
            now = time.monotonic()
            to_remove: list[str] = []
            for uid, last in list(self._last_active.items()):
                if now - last > self._inactive_timeout and uid in self.clients:
                    to_remove.append(uid)
            for uid in to_remove:
                logger.info("用户 %s 超时未活动，强制清理。", uid)
                ws = self.clients.get(uid)
                self._cleanup_disconnected_client(uid)
                if ws:
                    try:
                        await ws.close()
                    except Exception:
                        pass
            if to_remove:
                await self._broadcast_user_list()

    # -------------------- 发送 / 清理辅助 --------------------

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
        self._last_active.pop(user_id, None)
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
    parser.add_argument("--timeout", type=int, default=DEFAULT_INACTIVE_TIMEOUT,
                        help=f"不活跃超时秒数 (默认: {DEFAULT_INACTIVE_TIMEOUT})")
    args = parser.parse_args()

    server = ChatRelayServer(inactive_timeout=args.timeout)
    asyncio.run(server.start(args.host, args.port))


if __name__ == "__main__":
    main()
