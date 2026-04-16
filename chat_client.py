"""
聊天客户端网络层。

本模块为 GUI 提供"同步外观"的网络接口，内部使用后台线程运行 asyncio 事件循环：
  - GUI 线程调用 connect() / disconnect() / send_chat_message() 等同步方法。
  - 后台线程维护 WebSocket 连接，接收到的消息以事件字典写入线程安全的 queue.Queue。
  - GUI 通过 poll_event() 以定时器方式（tkinter after()）从队列取出事件并处理。

这种架构确保：
  - tkinter 主线程永远不会被网络 I/O 阻塞。
  - 后台线程永远不会直接操作 tkinter 组件。
  - 两者之间仅通过 queue.Queue 进行通信。
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Any

import websockets

import chat_protocol

logger = logging.getLogger("ChatClient")


class ChatClient:
    """
    GUI 可调用的聊天客户端。

    公开接口（同步，由 GUI 线程调用）：
      - connect()          建立连接并注册
      - disconnect()       断开连接
      - send_chat_message() 发送聊天密文
      - send_public_key()  向对方发送公钥
      - poll_event()       从事件队列取出一个事件

    事件结构（由 poll_event 返回的字典）：
      - {"event": "connected"}
      - {"event": "disconnected"}
      - {"event": "chat_message", "data": {...}}
      - {"event": "public_key", "data": {...}}
      - {"event": "user_list", "data": {...}}
      - {"event": "error", "message": "..."}
    """

    def __init__(self) -> None:
        self._event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._send_queue: queue.Queue[str] = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws: Any = None  # websockets client connection
        self._user_id: str = ""
        self._connected = False
        self._stop_event = threading.Event()

    @property
    def connected(self) -> bool:
        """当前是否已连接。"""
        return self._connected

    # -------------------- 公开同步接口 --------------------

    def connect(self, server_url: str, user_id: str, public_key_pem: str) -> None:
        """
        连接到服务端并注册。

        :param server_url: WebSocket 地址，如 ws://127.0.0.1:8765
        :param user_id: 用户 ID。
        :param public_key_pem: 本地公钥 PEM 文本。
        """
        if self._connected:
            return
        self._user_id = user_id
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(server_url, user_id, public_key_pem),
            daemon=True,
        )
        self._thread.start()

    def disconnect(self) -> None:
        """断开与服务端的连接。"""
        self._stop_event.set()
        if self._loop and self._ws:
            asyncio.run_coroutine_threadsafe(self._close_ws(), self._loop)
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def send_chat_message(self, receiver_id: str, payload: dict[str, object]) -> None:
        """
        发送聊天密文消息。

        :param receiver_id: 接收方用户 ID。
        :param payload: message_crypto.encrypt_chat_message 的输出。
        """
        raw = chat_protocol.make_chat_message(self._user_id, receiver_id, payload)
        self._enqueue_send(raw)

    def send_public_key(self, receiver_id: str, public_key_pem: str) -> None:
        """
        向指定用户发送自己的公钥。

        :param receiver_id: 接收方用户 ID。
        :param public_key_pem: 公钥 PEM 文本。
        """
        raw = chat_protocol.make_public_key_message(self._user_id, receiver_id, public_key_pem)
        self._enqueue_send(raw)

    def poll_event(self, timeout: float = 0.0) -> dict[str, Any] | None:
        """
        从事件队列中取出一个事件。GUI 应在 tkinter after() 回调中周期性调用。

        :param timeout: 阻塞等待时间（秒），0 表示非阻塞。
        :return: 事件字典，或队列为空时返回 None。
        """
        try:
            return self._event_queue.get(timeout=timeout) if timeout > 0 else self._event_queue.get_nowait()
        except queue.Empty:
            return None

    # -------------------- 后台线程入口 --------------------

    def _run_loop(self, server_url: str, user_id: str, public_key_pem: str) -> None:
        """在后台线程中启动独立的 asyncio 事件循环。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(
                self._async_main(server_url, user_id, public_key_pem)
            )
        except Exception as e:
            logger.error("网络线程异常: %s", e)
            self._put_event({"event": "error", "message": str(e)})
        finally:
            self._connected = False
            self._loop.close()
            self._loop = None

    async def _async_main(self, server_url: str, user_id: str, public_key_pem: str) -> None:
        """异步主函数：连接、注册、然后并发收发消息。"""
        try:
            async with websockets.connect(server_url) as ws:
                self._ws = ws
                self._connected = True
                self._put_event({"event": "connected"})

                # 发送注册消息
                register_msg = chat_protocol.make_register_message(user_id, public_key_pem)
                await ws.send(register_msg)
                logger.info("已注册: %s", user_id)

                # 并发运行：接收消息 + 发送队列消息
                recv_task = asyncio.ensure_future(self._recv_loop(ws))
                send_task = asyncio.ensure_future(self._send_loop(ws))

                # 等待任一任务结束（通常是 recv_loop 因连接关闭而结束）
                done, pending = await asyncio.wait(
                    [recv_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()

        except Exception as e:
            logger.error("连接失败: %s", e)
            self._put_event({"event": "error", "message": f"连接失败: {e}"})
        finally:
            self._connected = False
            self._ws = None
            self._put_event({"event": "disconnected"})

    async def _recv_loop(self, ws: Any) -> None:
        """持续接收服务端消息并写入事件队列。"""
        try:
            async for raw in ws:
                if self._stop_event.is_set():
                    break
                try:
                    msg = chat_protocol.parse_message(str(raw))
                except ValueError as e:
                    logger.warning("收到非法消息: %s", e)
                    continue

                msg_type = msg["type"]
                if msg_type == chat_protocol.MSG_CHAT_MESSAGE:
                    self._put_event({"event": "chat_message", "data": msg})
                elif msg_type == chat_protocol.MSG_PUBLIC_KEY:
                    self._put_event({"event": "public_key", "data": msg})
                elif msg_type == chat_protocol.MSG_USER_LIST:
                    self._put_event({"event": "user_list", "data": msg})
                elif msg_type == chat_protocol.MSG_ERROR:
                    payload = msg.get("payload", {})
                    err_msg = payload["message"] if isinstance(payload, dict) and "message" in payload else "未知错误"
                    self._put_event({"event": "error", "message": str(err_msg)})
                elif msg_type == chat_protocol.MSG_ACK:
                    self._put_event({"event": "ack", "data": msg})
                # heartbeat 不产生事件
        except websockets.exceptions.ConnectionClosed:
            logger.info("接收循环结束：连接已关闭。")

    async def _send_loop(self, ws: Any) -> None:
        """从发送队列取消息并通过 WebSocket 发出。"""
        while not self._stop_event.is_set():
            try:
                # 非阻塞尝试取消息，避免长时间阻塞导致无法检测 stop_event
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._send_queue.get(timeout=0.1)
                )
                await ws.send(raw)
            except queue.Empty:
                continue
            except websockets.exceptions.ConnectionClosed:
                break

    async def _close_ws(self) -> None:
        """安全关闭 WebSocket 连接。"""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    # -------------------- 内部辅助 --------------------

    def _enqueue_send(self, raw_message: str) -> None:
        """将待发送消息放入发送队列。"""
        if not self._connected:
            self._put_event({"event": "error", "message": "尚未连接到服务端。"})
            return
        self._send_queue.put(raw_message)

    def _put_event(self, event: dict[str, Any]) -> None:
        """向事件队列写入事件（线程安全）。"""
        self._event_queue.put(event)
