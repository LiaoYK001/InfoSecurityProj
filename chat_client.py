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

事件类型常量：
  EVT_CONNECTED      连接已建立并完成注册
  EVT_DISCONNECTED   连接已断开（含主动断开和异常断开）
  EVT_CHAT_MESSAGE   收到聊天密文消息
  EVT_PUBLIC_KEY     收到对方公钥
  EVT_USER_LIST      收到在线用户列表更新
  EVT_ACK            收到确认回执
  EVT_ERROR          错误通知
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

# -------------------- 客户端事件类型常量 --------------------

EVT_CONNECTED = "connected"
"""连接已建立并注册成功。"""

EVT_DISCONNECTED = "disconnected"
"""连接已断开。"""

EVT_CHAT_MESSAGE = "chat_message"
"""收到聊天密文消息。事件字典额外包含 "data" 键。"""

EVT_PUBLIC_KEY = "public_key"
"""收到对方公钥。事件字典额外包含 "data" 键。"""

EVT_USER_LIST = "user_list"
"""收到在线用户列表更新。事件字典额外包含 "data" 键。"""

EVT_ACK = "ack"
"""收到确认回执。事件字典额外包含 "data" 键。"""

EVT_ERROR = "error"
"""错误通知。事件字典额外包含 "message" 键。"""

EVT_FILE_TRANSFER = "file_transfer"
"""收到小文件整体传输。事件字典额外包含 "data" 键。"""

EVT_FILE_CHUNK = "file_chunk"
"""收到大文件分块。事件字典额外包含 "data" 键。"""

# 心跳发送间隔（秒）
HEARTBEAT_INTERVAL = 30

# 文件分块大小（字节）
FILE_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB

# 事件队列最大长度，防止内存泄漏
_MAX_EVENT_QUEUE_SIZE = 1000


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
      - {"event": EVT_CONNECTED}
      - {"event": EVT_DISCONNECTED, "reason": "..."}
      - {"event": EVT_CHAT_MESSAGE, "data": {...}}
      - {"event": EVT_PUBLIC_KEY, "data": {...}}
      - {"event": EVT_USER_LIST, "data": {...}}
      - {"event": EVT_ACK, "data": {...}}
      - {"event": EVT_ERROR, "message": "..."}
    """

    def __init__(self) -> None:
        self._event_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=_MAX_EVENT_QUEUE_SIZE)
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

    def send_file_message(
        self, receiver_id: str, encrypted_payload: dict[str, object],
        filename: str, filesize: int, mime_type: str,
    ) -> None:
        """
        发送小文件（≤ 5 MB，单条消息）。

        :param encrypted_payload: message_crypto.encrypt_file_data 的输出。
        :param filename: 原始文件名。
        :param filesize: 原始文件大小（字节）。
        :param mime_type: MIME 类型。
        """
        raw = chat_protocol.make_file_transfer_message(
            self._user_id, receiver_id, encrypted_payload,
            filename, filesize, mime_type,
        )
        self._enqueue_send(raw)

    def send_file_chunks(
        self, receiver_id: str, file_bytes: bytes,
        encrypt_func,
        filename: str, filesize: int, mime_type: str,
    ) -> None:
        """
        发送大文件（> 5 MB，分块）。每块独立加密后逐条发送。

        :param encrypt_func: 加密单块的回调 Callable[[bytes], dict]。
        :param filename: 原始文件名。
        :param filesize: 原始文件大小（字节）。
        :param mime_type: MIME 类型。
        """
        import uuid
        transfer_id = str(uuid.uuid4())
        total_chunks = (len(file_bytes) + FILE_CHUNK_SIZE - 1) // FILE_CHUNK_SIZE

        for i in range(total_chunks):
            chunk = file_bytes[i * FILE_CHUNK_SIZE : (i + 1) * FILE_CHUNK_SIZE]
            encrypted = encrypt_func(chunk)
            raw = chat_protocol.make_file_chunk_message(
                self._user_id, receiver_id, encrypted,
                transfer_id, i, total_chunks,
                filename, filesize, mime_type,
            )
            self._enqueue_send(raw)

    def send_heartbeat(self) -> None:
        """手动发送一次心跳包（通常由自动心跳任务处理，无需手动调用）。"""
        if self._connected and self._user_id:
            raw = chat_protocol.make_heartbeat_message(self._user_id)
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
            self._put_event({"event": EVT_ERROR, "message": str(e)})
        finally:
            self._connected = False
            self._loop.close()
            self._loop = None

    async def _async_main(self, server_url: str, user_id: str, public_key_pem: str) -> None:
        """异步主函数：连接、注册、然后并发收发消息和心跳。"""
        try:
            async with websockets.connect(server_url) as ws:
                self._ws = ws
                self._connected = True
                self._put_event({"event": EVT_CONNECTED})

                # 发送注册消息
                register_msg = chat_protocol.make_register_message(user_id, public_key_pem)
                await ws.send(register_msg)
                logger.info("已注册: %s", user_id)

                # 并发运行：接收消息 + 发送队列消息 + 心跳
                recv_task = asyncio.ensure_future(self._recv_loop(ws))
                send_task = asyncio.ensure_future(self._send_loop(ws))
                heartbeat_task = asyncio.ensure_future(self._heartbeat_loop(ws))

                # 等待任一任务结束（通常是 recv_loop 因连接关闭而结束）
                done, pending = await asyncio.wait(
                    [recv_task, send_task, heartbeat_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()

        except Exception as e:
            logger.error("连接失败: %s", e)
            self._put_event({"event": EVT_ERROR, "message": f"连接失败: {e}"})
        finally:
            self._connected = False
            self._ws = None
            self._put_event({"event": EVT_DISCONNECTED, "reason": "连接已关闭"})

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
                    self._put_event({"event": EVT_CHAT_MESSAGE, "data": msg})
                elif msg_type == chat_protocol.MSG_PUBLIC_KEY:
                    self._put_event({"event": EVT_PUBLIC_KEY, "data": msg})
                elif msg_type == chat_protocol.MSG_USER_LIST:
                    self._put_event({"event": EVT_USER_LIST, "data": msg})
                elif msg_type == chat_protocol.MSG_FILE_TRANSFER:
                    self._put_event({"event": EVT_FILE_TRANSFER, "data": msg})
                elif msg_type == chat_protocol.MSG_FILE_CHUNK:
                    self._put_event({"event": EVT_FILE_CHUNK, "data": msg})
                elif msg_type == chat_protocol.MSG_ERROR:
                    payload = msg.get("payload", {})
                    err_msg = payload["message"] if isinstance(payload, dict) and "message" in payload else "未知错误"
                    self._put_event({"event": EVT_ERROR, "message": str(err_msg)})
                elif msg_type == chat_protocol.MSG_ACK:
                    self._put_event({"event": EVT_ACK, "data": msg})
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

    async def _heartbeat_loop(self, ws: Any) -> None:
        """定期向服务端发送心跳包，保持连接活跃。"""
        while not self._stop_event.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if self._stop_event.is_set():
                break
            try:
                hb = chat_protocol.make_heartbeat_message(self._user_id)
                await ws.send(hb)
                logger.debug("心跳已发送")
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
            self._put_event({"event": EVT_ERROR, "message": "尚未连接到服务端。"})
            return
        self._send_queue.put(raw_message)

    def _put_event(self, event: dict[str, Any]) -> None:
        """向事件队列写入事件（线程安全）。队列满时丢弃最旧事件。"""
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            # 丢弃最旧事件，腾出空间
            try:
                self._event_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._event_queue.put_nowait(event)
            except queue.Full:
                pass
