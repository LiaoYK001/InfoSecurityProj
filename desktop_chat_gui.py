"""
加密聊天桌面客户端 GUI。

本模块使用 tkinter 实现完整的加密即时通讯桌面界面，包含以下区域：
  - 登录区：服务器地址、用户 ID、连接/断开按钮。
  - 密钥区：生成密钥、加载私钥、导出公钥。
  - 联系人区：在线用户列表（自动从服务端获取）。
  - 聊天区：消息显示列表和消息输入框。
  - Crypto Console 区：实时显示加解密过程的调试日志，用于教学演示。

线程模型说明：
  - tkinter 只能在主线程中更新控件（这是 tkinter 的底层限制）。
  - 网络 I/O 在后台线程中运行（由 chat_client.ChatClient 管理）。
  - 两者之间通过 queue.Queue 通信：后台线程写入事件，GUI 定时轮询读取。
  - GUI 使用 tkinter 的 after() 方法每 100ms 轮询一次事件队列。

启动方式：
    python desktop_chat_gui.py
"""

from __future__ import annotations

import io
import mimetypes
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from datetime import datetime

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

import chat_client
import session_manager as sm

# 轮询间隔（毫秒）
_POLL_INTERVAL_MS = 100

# 文件大小限制
FILE_SIZE_LIMIT = 50 * 1024 * 1024    # 50 MB
SMALL_FILE_LIMIT = 5 * 1024 * 1024    # 5 MB

# 图片 MIME 类型集合
IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}

# 缩略图最大尺寸
THUMBNAIL_MAX = (300, 300)


class DesktopChatApp(tk.Tk):
    """加密聊天桌面主程序。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("加密即时通讯 — Encrypted Chat")
        self.geometry("960x720")
        self.minsize(800, 600)

        # 核心组件
        self._session = sm.SessionManager()
        self._client = chat_client.ChatClient()
        self._current_peer: str = ""  # 当前聊天对象

        # 文件传输状态
        self._chunk_buffers: dict[str, dict] = {}
        self._image_refs: list = []  # 保持图片引用防止 GC

        self._build_layout()
        self._poll_network_events()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================
    #  界面构建
    # ================================================================

    def _build_layout(self) -> None:
        """构建整个界面布局。"""
        # 顶部工具栏（登录 + 密钥）
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=6, pady=(6, 0))
        self._build_login_area(top_frame)
        self._build_key_area(top_frame)

        # 中间主体区域（联系人 + 聊天 + Crypto Console）
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # 左侧联系人列表
        left = ttk.Frame(body, width=180)
        body.add(left, weight=0)
        self._build_contact_area(left)

        # 右侧：聊天 + Crypto Console
        right = ttk.PanedWindow(body, orient=tk.VERTICAL)
        body.add(right, weight=1)

        chat_frame = ttk.Frame(right)
        right.add(chat_frame, weight=3)
        self._build_chat_area(chat_frame)

        crypto_frame = ttk.LabelFrame(right, text="Crypto Console")
        right.add(crypto_frame, weight=1)
        self._build_crypto_console(crypto_frame)

        # 底部状态栏
        self._status_var = tk.StringVar(value="未连接")
        ttk.Label(self, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, side=tk.BOTTOM, padx=6, pady=(0, 6)
        )

    def _build_login_area(self, parent: ttk.Frame) -> None:
        """登录区控件：服务器地址、用户 ID、连接/断开按钮。"""
        grp = ttk.LabelFrame(parent, text="连接")
        grp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        ttk.Label(grp, text="服务器:").grid(row=0, column=0, padx=2, pady=2, sticky=tk.W)
        self._server_var = tk.StringVar(value="ws://127.0.0.1:8765")
        self._entry_server = ttk.Entry(grp, textvariable=self._server_var, width=24)
        self._entry_server.grid(row=0, column=1, padx=2)

        ttk.Label(grp, text="用户 ID:").grid(row=0, column=2, padx=2)
        self._uid_var = tk.StringVar()
        self._entry_uid = ttk.Entry(grp, textvariable=self._uid_var, width=12)
        self._entry_uid.grid(row=0, column=3, padx=2)

        self._btn_connect = ttk.Button(grp, text="连接", command=self._connect_to_server)
        self._btn_connect.grid(row=0, column=4, padx=2)
        self._btn_disconnect = ttk.Button(grp, text="断开", command=self._disconnect_from_server, state=tk.DISABLED)
        self._btn_disconnect.grid(row=0, column=5, padx=2)

    def _build_key_area(self, parent: ttk.Frame) -> None:
        """密钥区控件：连接后禁用，防止会话中途更换密钥。"""
        grp = ttk.LabelFrame(parent, text="密钥")
        grp.pack(side=tk.LEFT, padx=(4, 0))

        self._btn_gen_key = ttk.Button(grp, text="生成密钥", command=self._generate_keys)
        self._btn_gen_key.grid(row=0, column=0, padx=2, pady=2)
        self._btn_load_key = ttk.Button(grp, text="加载私钥", command=self._load_local_key)
        self._btn_load_key.grid(row=0, column=1, padx=2)
        self._btn_export_key = ttk.Button(grp, text="导出公钥", command=self._export_public_key)
        self._btn_export_key.grid(row=0, column=2, padx=2)

    def _build_contact_area(self, parent: ttk.Frame) -> None:
        """联系人区控件：在线用户列表 + 选中联系人的公钥指纹。"""
        ttk.Label(parent, text="在线用户").pack(anchor=tk.W, padx=4, pady=(4, 0))
        self._contact_list = tk.Listbox(parent, width=22)
        self._contact_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._contact_list.bind("<<ListboxSelect>>", self._on_contact_select)

        # 联系人公钥指纹信息
        self._contact_fp_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self._contact_fp_var, font=("Consolas", 8),
                  foreground="#666666", wraplength=160).pack(anchor=tk.W, padx=4, pady=(0, 4))

    def _build_chat_area(self, parent: ttk.Frame) -> None:
        """聊天消息区控件。"""
        # 当前聊天对象标签
        self._peer_label_var = tk.StringVar(value="选择一个联系人开始聊天")
        ttk.Label(parent, textvariable=self._peer_label_var, font=("", 10, "bold")).pack(
            anchor=tk.W, padx=4, pady=(4, 0)
        )

        # 消息显示区
        self._chat_display = scrolledtext.ScrolledText(parent, state=tk.DISABLED, wrap=tk.WORD, height=12)
        self._chat_display.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._chat_display.tag_configure("me", foreground="#0066cc")
        self._chat_display.tag_configure("peer", foreground="#009933")
        self._chat_display.tag_configure("system", foreground="#999999")

        # 输入区
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
        self._msg_var = tk.StringVar()
        self._msg_entry = ttk.Entry(input_frame, textvariable=self._msg_var)
        self._msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._msg_entry.bind("<Return>", lambda _: self._send_message())
        self._btn_file = ttk.Button(input_frame, text="📎", command=self._send_file, width=3)
        self._btn_file.pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(input_frame, text="发送", command=self._send_message).pack(side=tk.RIGHT, padx=(4, 0))

    def _build_crypto_console(self, parent: ttk.LabelFrame) -> None:
        """Crypto Console 日志区：分类着色显示加解密过程。"""
        self._crypto_log = scrolledtext.ScrolledText(
            parent, state=tk.DISABLED, wrap=tk.WORD, height=6,
            font=("Consolas", 9),
        )
        self._crypto_log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        # 不同类别日志使用不同颜色，便于演示截图区分
        self._crypto_log.tag_configure("log_encrypt", foreground="#0066cc")
        self._crypto_log.tag_configure("log_decrypt", foreground="#009933")
        self._crypto_log.tag_configure("log_key", foreground="#996600")
        self._crypto_log.tag_configure("log_send", foreground="#0066cc")
        self._crypto_log.tag_configure("log_recv", foreground="#009933")
        self._crypto_log.tag_configure("log_conn", foreground="#666666")
        self._crypto_log.tag_configure("log_error", foreground="#cc0000")
        self._crypto_log.tag_configure("log_warn", foreground="#cc6600")

    # ================================================================
    #  连接 / 断开
    # ================================================================

    def _connect_to_server(self) -> None:
        """
        连接到服务端。
        流程：校验输入 → 校验密钥 → 锁定界面输入 → 发起异步连接。
        连接结果通过 EVT_CONNECTED / EVT_DISCONNECTED 事件回调处理。
        """
        server = self._server_var.get().strip()
        uid = self._uid_var.get().strip()
        if not server or not uid:
            messagebox.showwarning("提示", "请输入服务器地址和用户 ID。")
            return
        if not self._session.has_local_keys():
            messagebox.showwarning("提示", "请先生成或加载密钥，再连接服务端。")
            return

        pub_pem = self._session.export_local_public_key()
        self._client.connect(server, uid, pub_pem)

        # 锁定界面：连接期间不允许修改服务器地址、用户 ID 和密钥
        self._set_connection_ui_state(connecting=True)
        self._status_var.set(f"正在连接 {server} ...")

    def _disconnect_from_server(self) -> None:
        """
        主动断开连接。
        解锁界面输入，清空当前联系人状态。
        """
        self._client.disconnect()
        self._set_connection_ui_state(connecting=False)
        self._current_peer = ""
        self._peer_label_var.set("选择一个联系人开始聊天")
        self._contact_fp_var.set("")
        self._contact_list.delete(0, tk.END)
        self._status_var.set("已断开")

    def _set_connection_ui_state(self, *, connecting: bool) -> None:
        """
        统一切换界面控件的启用/禁用状态。
        connecting=True 时锁定输入区和密钥区；False 时解锁。
        确保按钮状态始终与实际连接状态一致。
        """
        if connecting:
            self._entry_server.config(state=tk.DISABLED)
            self._entry_uid.config(state=tk.DISABLED)
            self._btn_connect.config(state=tk.DISABLED)
            self._btn_disconnect.config(state=tk.NORMAL)
            self._btn_gen_key.config(state=tk.DISABLED)
            self._btn_load_key.config(state=tk.DISABLED)
        else:
            self._entry_server.config(state=tk.NORMAL)
            self._entry_uid.config(state=tk.NORMAL)
            self._btn_connect.config(state=tk.NORMAL)
            self._btn_disconnect.config(state=tk.DISABLED)
            self._btn_gen_key.config(state=tk.NORMAL)
            self._btn_load_key.config(state=tk.NORMAL)

    # ================================================================
    #  密钥操作
    # ================================================================

    def _generate_keys(self) -> None:
        """生成 RSA-2048 密钥对，并在 Crypto Console 中记录指纹。"""
        if self._client.connected:
            messagebox.showwarning("提示", "连接期间不可更换密钥，请先断开。")
            return
        self._session.generate_local_keys(2048)
        fp = self._session.get_local_fingerprint()
        self._append_crypto_log(f"[密钥] 已生成 RSA-2048 密钥对，本地公钥指纹: {fp}", "log_key")
        self._status_var.set(f"密钥已生成 (指纹: {fp})")

    def _load_local_key(self) -> None:
        """从 PEM 文件加载已有私钥（自动推导公钥）。"""
        if self._client.connected:
            messagebox.showwarning("提示", "连接期间不可更换密钥，请先断开。")
            return
        path = filedialog.askopenfilename(
            title="选择私钥文件",
            filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self._session.load_local_private_key(path)
            fp = self._session.get_local_fingerprint()
            self._append_crypto_log(f"[密钥] 已加载私钥，公钥指纹: {fp}", "log_key")
            self._status_var.set(f"私钥已加载 (指纹: {fp})")
        except Exception as e:
            messagebox.showerror("错误", f"加载私钥失败: {e}")

    def _export_public_key(self) -> None:
        """导出公钥到文件。"""
        if not self._session.has_local_keys():
            messagebox.showwarning("提示", "请先生成或加载密钥。")
            return
        path = filedialog.asksaveasfilename(
            title="保存公钥",
            defaultextension=".pem",
            filetypes=[("PEM 文件", "*.pem")],
        )
        if not path:
            return
        try:
            pem = self._session.export_local_public_key()
            with open(path, "w", encoding="utf-8") as f:
                f.write(pem)
            self._append_crypto_log(f"[密钥] 公钥已导出到: {path}", "log_key")
        except Exception as e:
            messagebox.showerror("错误", f"导出公钥失败: {e}")

    # ================================================================
    #  联系人选择
    # ================================================================

    def _on_contact_select(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        """
        用户在联系人列表中选择了一个联系人。
        更新当前聊天对象、显示公钥指纹、切换会话提示。
        若对方公钥尚未获取，在状态栏和指纹区给出提示。
        """
        sel = self._contact_list.curselection()
        if not sel:
            return
        peer_id = self._contact_list.get(sel[0])
        if peer_id == self._uid_var.get().strip():
            return  # 不和自己聊天
        self._current_peer = peer_id
        fp = self._session.get_peer_fingerprint(peer_id)
        if fp:
            self._peer_label_var.set(f"与 {peer_id} 聊天  (公钥指纹: {fp})")
            self._contact_fp_var.set(f"指纹: {fp}")
        else:
            self._peer_label_var.set(f"与 {peer_id} 聊天  (等待公钥...)")
            self._contact_fp_var.set("公钥未获取，暂不可发送")
        self._append_chat_message("system", f"--- 已切换到与 {peer_id} 的对话 ---")

    # ================================================================
    #  消息发送
    # ================================================================

    def _send_message(self) -> None:
        """
        加密并发送消息。
        发送前校验：空消息、未连接、未选联系人、缺少对方公钥。
        发送成功后在聊天区显示本地消息，在 Crypto Console 记录完整加密链路。
        """
        plaintext = self._msg_var.get().strip()
        if not plaintext:
            return
        if not self._current_peer:
            messagebox.showwarning("提示", "请先选择一个联系人。")
            return
        if not self._client.connected:
            messagebox.showwarning("提示", "尚未连接到服务端。")
            return
        if not self._session.has_peer_public_key(self._current_peer):
            messagebox.showwarning("提示", f"尚未获取 {self._current_peer} 的公钥，无法加密。")
            return

        try:
            # ---- 加密流程（在 Crypto Console 中逐步展示） ----
            self._append_crypto_log(
                f"[加密] ① 准备发送消息 (明文长度: {len(plaintext)} 字符)", "log_encrypt")
            encrypted = self._session.encrypt_for_peer(self._current_peer, plaintext)
            debug_raw = encrypted.get("debug", {})
            debug = debug_raw if isinstance(debug_raw, dict) else {}
            self._append_crypto_log(
                f"[加密] ② 生成一次性 AES-{debug.get('session_key_bits', 256)} 会话密钥", "log_encrypt")
            self._append_crypto_log(
                f"[加密] ③ AES-GCM 加密完成 → 密文长度: {debug.get('ciphertext_length', '?')}"
                f", nonce 长度: {debug.get('nonce_length', '?')}", "log_encrypt")
            self._append_crypto_log(
                f"[加密] ④ RSA 公钥加密会话密钥 → wrapped_key 长度: {debug.get('wrapped_key_length', '?')}"
                f" (对方指纹: {debug.get('peer_key_fingerprint', '?')})", "log_encrypt")

            # ---- 发送 ----
            self._client.send_chat_message(self._current_peer, encrypted)
            self._append_crypto_log(
                f"[发送] ⑤ 密文消息包已发送给 {self._current_peer} "
                f"(服务端仅可见密文，无法还原明文)", "log_send")

            # ---- 本地显示明文 ----
            self._append_chat_message("me", plaintext)
            self._msg_var.set("")

        except Exception as e:
            messagebox.showerror("发送失败", str(e))
            self._append_crypto_log(f"[错误] 加密/发送失败: {e}", "log_error")

    # ================================================================
    #  文件发送
    # ================================================================

    def _send_file(self) -> None:
        """选择文件并加密发送。"""
        if not self._client.connected:
            messagebox.showwarning("提示", "尚未连接到服务端。")
            return
        if not self._current_peer:
            messagebox.showwarning("提示", "请先选择一个联系人。")
            return
        if not self._session.has_peer_public_key(self._current_peer):
            messagebox.showwarning("提示", f"尚未获取 {self._current_peer} 的公钥，无法加密。")
            return

        filepath = filedialog.askopenfilename(
            title="选择要发送的文件",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if not filepath:
            return

        filesize = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"

        if filesize > FILE_SIZE_LIMIT:
            messagebox.showwarning("提示", f"文件过大: {filesize / 1024 / 1024:.1f} MB，上限 50 MB")
            return

        with open(filepath, "rb") as f:
            file_bytes = f.read()

        peer_id = self._current_peer
        self._append_crypto_log(
            f"[加密] 开始加密文件: {filename} ({self._format_size(filesize)})", "log_encrypt")

        try:
            if filesize <= SMALL_FILE_LIMIT:
                encrypted = self._session.encrypt_file_for_peer(peer_id, file_bytes)
                self._client.send_file_message(
                    peer_id, encrypted, filename, filesize, mime_type,
                )
                self._append_crypto_log(f"[发送] 已发送文件: {filename}", "log_send")
            else:
                encrypt_fn = lambda chunk: self._session.encrypt_file_for_peer(peer_id, chunk)
                self._client.send_file_chunks(
                    peer_id, file_bytes, encrypt_fn, filename, filesize, mime_type,
                )
                total = (filesize + chat_client.FILE_CHUNK_SIZE - 1) // chat_client.FILE_CHUNK_SIZE
                self._append_crypto_log(
                    f"[发送] 已分块发送文件: {filename} ({total} 块)", "log_send")

            self._append_file_message("me", filename, filesize, mime_type, file_bytes)
        except Exception as e:
            messagebox.showerror("发送失败", str(e))
            self._append_crypto_log(f"[错误] 文件加密/发送失败: {e}", "log_error")

    # ================================================================
    #  网络事件轮询
    # ================================================================

    def _poll_network_events(self) -> None:
        """
        定时轮询网络事件队列。
        使用 tkinter 的 after() 机制确保在主线程中执行 UI 更新。
        """
        # 每次最多处理 20 个事件，避免界面卡顿
        for _ in range(20):
            event = self._client.poll_event()
            if event is None:
                break
            self._handle_network_event(event)
        self.after(_POLL_INTERVAL_MS, self._poll_network_events)

    def _handle_network_event(self, event: dict[str, object]) -> None:
        """
        根据事件类型分发处理。
        所有 UI 更新都在此处（主线程）执行，保证线程安全。
        """
        evt_type = event.get("event", "")

        if evt_type == chat_client.EVT_CONNECTED:
            uid = self._uid_var.get().strip()
            fp = self._session.get_local_fingerprint()
            self._status_var.set(f"已连接 | 用户: {uid} | 本地指纹: {fp}")
            self._append_crypto_log("[连接] 已成功连接到服务端并完成注册。", "log_conn")

        elif evt_type == chat_client.EVT_DISCONNECTED:
            reason = event.get("reason", "")
            # 解锁界面，恢复到未连接状态
            self._set_connection_ui_state(connecting=False)
            self._current_peer = ""
            self._peer_label_var.set("选择一个联系人开始聊天")
            self._contact_fp_var.set("")
            self._contact_list.delete(0, tk.END)
            self._status_var.set("已断开")
            self._append_crypto_log(
                f"[连接] 与服务端的连接已断开{' (' + str(reason) + ')' if reason else ''}。",
                "log_conn",
            )

        elif evt_type == chat_client.EVT_USER_LIST:
            self._handle_user_list(event)

        elif evt_type == chat_client.EVT_CHAT_MESSAGE:
            self._handle_incoming_chat(event)

        elif evt_type == chat_client.EVT_PUBLIC_KEY:
            self._handle_incoming_public_key(event)

        elif evt_type == chat_client.EVT_FILE_TRANSFER:
            self._handle_incoming_file(event)

        elif evt_type == chat_client.EVT_FILE_CHUNK:
            self._handle_incoming_file_chunk(event)

        elif evt_type == chat_client.EVT_ERROR:
            err = event.get("message", "未知错误")
            self._append_crypto_log(f"[错误] {err}", "log_error")

    def _handle_user_list(self, event: dict) -> None:
        """
        处理服务端广播的在线用户列表。
        - 刷新联系人列表。
        - 自动导入/更新对方公钥。
        - 检测当前聊天对象是否已下线并提示。
        """
        data = event.get("data", {})
        payload = data.get("payload", {})
        users: dict = payload.get("users", {})

        my_id = self._uid_var.get().strip()
        self._contact_list.delete(0, tk.END)

        for uid, pub_pem in users.items():
            if uid == my_id:
                continue
            self._contact_list.insert(tk.END, uid)
            # 自动导入或更新对方公钥
            if pub_pem:
                if not self._session.has_peer_public_key(uid):
                    try:
                        self._session.set_peer_public_key(uid, pub_pem)
                        fp = self._session.get_peer_fingerprint(uid)
                        self._append_crypto_log(
                            f"[密钥] 自动导入 {uid} 的公钥 (指纹: {fp})", "log_key")
                    except Exception as e:
                        self._append_crypto_log(
                            f"[警告] 导入 {uid} 公钥失败: {e}", "log_warn")

        # 检测当前聊天对象是否已下线
        if self._current_peer and self._current_peer not in users:
            self._append_chat_message("system", f"--- {self._current_peer} 已下线 ---")
            self._peer_label_var.set(f"与 {self._current_peer} 聊天  (对方已离线)")
            self._contact_fp_var.set("对方已离线")

    def _handle_incoming_chat(self, event: dict) -> None:
        """
        处理收到的聊天密文消息：在 Crypto Console 中展示完整解密链路，
        解密成功后在聊天区显示明文，解密失败时在两处均给出提示。
        """
        data = event.get("data", {})
        sender_id = str(data.get("sender_id", "?"))
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        # ---- 解密流程（在 Crypto Console 中逐步展示） ----
        wk_len = len(str(payload.get("wrapped_key", "")))
        ct_len = len(str(payload.get("ciphertext", "")))
        self._append_crypto_log(
            f"[接收] ① 收到来自 {sender_id} 的密文消息包", "log_recv")
        self._append_crypto_log(
            f"[接收] ② wrapped_key 长度: {wk_len}, 密文长度: {ct_len}", "log_recv")

        try:
            result = self._session.decrypt_from_message(payload)
            plaintext = str(result["plaintext"])
            debug_raw = result.get("debug", {})
            debug = debug_raw if isinstance(debug_raw, dict) else {}
            self._append_crypto_log(
                f"[解密] ③ RSA 私钥解包 wrapped_key → 恢复 AES 会话密钥成功", "log_decrypt")
            self._append_crypto_log(
                f"[解密] ④ AES-GCM 解密成功 → 明文长度: {debug.get('plaintext_length', '?')} 字符",
                "log_decrypt")

            # 在聊天区显示解密后的明文
            self._append_chat_message("peer", plaintext, sender_id)

        except Exception as e:
            self._append_crypto_log(f"[错误] 解密失败: {e}", "log_error")
            self._append_chat_message(
                "system", f"[解密失败] 来自 {sender_id} 的消息无法解密: {e}")

    def _handle_incoming_public_key(self, event: dict) -> None:
        """处理收到的公钥消息：导入对方公钥并在 Crypto Console 中记录。"""
        data = event.get("data", {})
        sender_id = str(data.get("sender_id", "?"))
        payload_raw = data.get("payload", {})
        pub_pem = payload_raw.get("public_key", "") if isinstance(payload_raw, dict) else ""
        if pub_pem:
            try:
                self._session.set_peer_public_key(sender_id, str(pub_pem))
                fp = self._session.get_peer_fingerprint(sender_id)
                self._append_crypto_log(
                    f"[密钥] 收到 {sender_id} 的公钥 (指纹: {fp})", "log_key")
                # 若当前正在和该用户聊天，更新指纹显示
                if self._current_peer == sender_id and fp:
                    self._peer_label_var.set(f"与 {sender_id} 聊天  (公钥指纹: {fp})")
                    self._contact_fp_var.set(f"指纹: {fp}")
            except Exception as e:
                self._append_crypto_log(
                    f"[警告] 导入 {sender_id} 公钥失败: {e}", "log_warn")

    # ================================================================
    #  文件接收处理
    # ================================================================

    def _handle_incoming_file(self, event: dict) -> None:
        """处理收到的小文件整体传输消息。"""
        data = event.get("data", {})
        sender_id = str(data.get("sender_id", "?"))
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            return

        filename = str(payload.get("filename", "unnamed"))
        filesize = int(payload.get("filesize", 0))
        mime_type = str(payload.get("mime_type", "application/octet-stream"))

        self._append_crypto_log(f"[接收] 收到来自 {sender_id} 的文件: {filename}", "log_recv")

        try:
            result = self._session.decrypt_file_from_message(payload)
            file_bytes = result["file_bytes"]
            self._append_crypto_log(
                f"[解密] 文件解密成功: {self._format_size(len(file_bytes))}", "log_decrypt")
            self._append_file_message("peer", filename, filesize, mime_type, file_bytes, sender_id)
        except Exception as e:
            self._append_crypto_log(f"[错误] 文件解密失败: {e}", "log_error")
            self._append_chat_message(
                "system", f"[文件解密失败] 来自 {sender_id} 的 {filename}: {e}")

    def _handle_incoming_file_chunk(self, event: dict) -> None:
        """处理分块文件的单个块。"""
        data = event.get("data", {})
        sender_id = str(data.get("sender_id", "?"))
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            return

        transfer_id = str(payload.get("transfer_id", ""))
        chunk_index = int(payload.get("chunk_index", 0))
        total_chunks = int(payload.get("total_chunks", 1))
        filename = str(payload.get("filename", "unnamed"))
        filesize = int(payload.get("filesize", 0))
        mime_type = str(payload.get("mime_type", "application/octet-stream"))

        try:
            result = self._session.decrypt_file_from_message(payload)
            chunk_bytes = result["file_bytes"]
        except Exception as e:
            self._append_crypto_log(
                f"[错误] 文件块 {chunk_index + 1}/{total_chunks} 解密失败: {e}", "log_error")
            return

        if transfer_id not in self._chunk_buffers:
            self._chunk_buffers[transfer_id] = {
                "chunks": {}, "total": total_chunks,
                "filename": filename, "filesize": filesize,
                "mime_type": mime_type, "sender_id": sender_id,
            }
            self._append_crypto_log(
                f"[接收] 开始接收分块文件: {filename} ({total_chunks} 块)", "log_recv")

        buf = self._chunk_buffers[transfer_id]
        buf["chunks"][chunk_index] = chunk_bytes
        self._append_crypto_log(f"[接收] 收到块 {chunk_index + 1}/{total_chunks}", "log_recv")

        if len(buf["chunks"]) == total_chunks:
            file_bytes = b"".join(buf["chunks"][i] for i in range(total_chunks))
            self._append_crypto_log(
                f"[解密] 文件拼装完成: {filename} ({self._format_size(len(file_bytes))})",
                "log_decrypt")
            self._append_file_message(
                "peer", filename, filesize, mime_type, file_bytes, sender_id)
            del self._chunk_buffers[transfer_id]

    # ================================================================
    #  文件/图片渲染
    # ================================================================

    def _append_file_message(self, role: str, filename: str, filesize: int,
                              mime_type: str, file_bytes: bytes,
                              sender_id: str = "") -> None:
        """在聊天区显示文件消息，图片自动预览。"""
        tag = "me" if role == "me" else "peer"
        prefix = "我" if role == "me" else (sender_id or self._current_peer or "对方")
        now = datetime.now().strftime("%H:%M:%S")
        size_str = self._format_size(filesize)

        self._chat_display.config(state=tk.NORMAL)
        self._chat_display.insert(tk.END, f"[{now}] {prefix}: ", tag)
        self._chat_display.insert(tk.END, f"📎 {filename} ({size_str})\n", tag)

        # 图片预览
        if mime_type in IMAGE_MIMES and _HAS_PIL:
            try:
                img = Image.open(io.BytesIO(file_bytes))
                img.thumbnail(THUMBNAIL_MAX, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._image_refs.append(photo)
                self._chat_display.image_create(tk.END, image=photo)
                self._chat_display.insert(tk.END, "\n")
            except Exception:
                self._chat_display.insert(tk.END, "[图片预览失败]\n", "system")
        elif mime_type in IMAGE_MIMES:
            self._chat_display.insert(tk.END, "[需安装 Pillow 才能预览图片]\n", "system")

        # 保存链接
        save_tag = f"save_{id(file_bytes)}_{time.time_ns()}"
        self._chat_display.tag_config(save_tag, foreground="#4fc3f7", underline=True)
        self._chat_display.tag_bind(
            save_tag, "<Button-1>",
            lambda e, fb=file_bytes, fn=filename: self._save_received_file(fb, fn))
        self._chat_display.insert(tk.END, "[点击保存文件]", save_tag)
        self._chat_display.insert(tk.END, "\n\n")

        self._chat_display.see(tk.END)
        self._chat_display.config(state=tk.DISABLED)

    def _save_received_file(self, file_bytes: bytes, default_name: str) -> None:
        """弹出保存对话框，将解密的文件保存到本地。"""
        filepath = filedialog.asksaveasfilename(
            initialfile=default_name,
            title="保存文件",
        )
        if filepath:
            with open(filepath, "wb") as f:
                f.write(file_bytes)
            self._append_crypto_log(f"[接收] 文件已保存: {filepath}", "log_recv")

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小。"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / 1024 / 1024:.1f} MB"

    # ================================================================
    #  UI 辅助
    # ================================================================

    def _append_chat_message(self, role: str, text: str, sender_id: str = "") -> None:
        """向聊天显示区追加一条消息。"""
        self._chat_display.config(state=tk.NORMAL)
        now = datetime.now().strftime("%H:%M:%S")
        if role == "me":
            prefix = f"[{now}] 我: "
            tag = "me"
        elif role == "peer":
            name = sender_id or self._current_peer or "对方"
            prefix = f"[{now}] {name}: "
            tag = "peer"
        else:
            prefix = f"[{now}] "
            tag = "system"
        self._chat_display.insert(tk.END, prefix + text + "\n", tag)
        self._chat_display.see(tk.END)
        self._chat_display.config(state=tk.DISABLED)

    def _append_crypto_log(self, text: str, tag: str = "") -> None:
        """
        向 Crypto Console 追加一条日志。
        tag 参数控制日志颜色分类（如 log_encrypt / log_decrypt / log_error 等）。
        """
        self._crypto_log.config(state=tk.NORMAL)
        now = datetime.now().strftime("%H:%M:%S")
        line = f"[{now}] {text}\n"
        if tag:
            self._crypto_log.insert(tk.END, line, tag)
        else:
            self._crypto_log.insert(tk.END, line)
        self._crypto_log.see(tk.END)
        self._crypto_log.config(state=tk.DISABLED)

    def _on_close(self) -> None:
        """
        窗口关闭时的清理逻辑：
        先断开网络连接（触发后台线程退出），再销毁窗口。
        避免后台线程或 WebSocket 连接残留。
        """
        if self._client.connected:
            self._client.disconnect()
        self.destroy()


def main() -> None:
    app = DesktopChatApp()
    app.mainloop()


if __name__ == "__main__":
    main()
