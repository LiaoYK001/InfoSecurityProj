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

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from datetime import datetime

import chat_client
import session_manager as sm

# 轮询间隔（毫秒）
_POLL_INTERVAL_MS = 100


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
        """登录区控件。"""
        grp = ttk.LabelFrame(parent, text="连接")
        grp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        ttk.Label(grp, text="服务器:").grid(row=0, column=0, padx=2, pady=2, sticky=tk.W)
        self._server_var = tk.StringVar(value="ws://127.0.0.1:8765")
        ttk.Entry(grp, textvariable=self._server_var, width=24).grid(row=0, column=1, padx=2)

        ttk.Label(grp, text="用户 ID:").grid(row=0, column=2, padx=2)
        self._uid_var = tk.StringVar()
        ttk.Entry(grp, textvariable=self._uid_var, width=12).grid(row=0, column=3, padx=2)

        self._btn_connect = ttk.Button(grp, text="连接", command=self._connect_to_server)
        self._btn_connect.grid(row=0, column=4, padx=2)
        self._btn_disconnect = ttk.Button(grp, text="断开", command=self._disconnect_from_server, state=tk.DISABLED)
        self._btn_disconnect.grid(row=0, column=5, padx=2)

    def _build_key_area(self, parent: ttk.Frame) -> None:
        """密钥区控件。"""
        grp = ttk.LabelFrame(parent, text="密钥")
        grp.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Button(grp, text="生成密钥", command=self._generate_keys).grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(grp, text="加载私钥", command=self._load_local_key).grid(row=0, column=1, padx=2)
        ttk.Button(grp, text="导出公钥", command=self._export_public_key).grid(row=0, column=2, padx=2)

    def _build_contact_area(self, parent: ttk.Frame) -> None:
        """联系人区控件。"""
        ttk.Label(parent, text="在线用户").pack(anchor=tk.W, padx=4, pady=(4, 0))
        self._contact_list = tk.Listbox(parent, width=22)
        self._contact_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._contact_list.bind("<<ListboxSelect>>", self._on_contact_select)

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
        ttk.Button(input_frame, text="发送", command=self._send_message).pack(side=tk.RIGHT, padx=(4, 0))

    def _build_crypto_console(self, parent: ttk.LabelFrame) -> None:
        """Crypto Console 日志区。"""
        self._crypto_log = scrolledtext.ScrolledText(parent, state=tk.DISABLED, wrap=tk.WORD, height=6, font=("Consolas", 9))
        self._crypto_log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    # ================================================================
    #  连接 / 断开
    # ================================================================

    def _connect_to_server(self) -> None:
        """连接到服务端。"""
        server = self._server_var.get().strip()
        uid = self._uid_var.get().strip()
        if not server or not uid:
            messagebox.showwarning("提示", "请输入服务器地址和用户 ID。")
            return
        if not self._session.has_local_keys():
            messagebox.showwarning("提示", "请先生成或加载密钥。")
            return

        pub_pem = self._session.export_local_public_key()
        self._client.connect(server, uid, pub_pem)
        self._btn_connect.config(state=tk.DISABLED)
        self._btn_disconnect.config(state=tk.NORMAL)
        self._status_var.set(f"正在连接 {server} ...")

    def _disconnect_from_server(self) -> None:
        """断开连接。"""
        self._client.disconnect()
        self._btn_connect.config(state=tk.NORMAL)
        self._btn_disconnect.config(state=tk.DISABLED)
        self._status_var.set("已断开")

    # ================================================================
    #  密钥操作
    # ================================================================

    def _generate_keys(self) -> None:
        """生成 RSA 2048 密钥对。"""
        self._session.generate_local_keys(2048)
        fp = self._session.get_local_fingerprint()
        self._append_crypto_log(f"[密钥] 已生成 RSA-2048 密钥对，公钥指纹: {fp}")
        self._status_var.set(f"密钥已生成 (指纹: {fp})")

    def _load_local_key(self) -> None:
        """从文件加载私钥。"""
        path = filedialog.askopenfilename(
            title="选择私钥文件",
            filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self._session.load_local_private_key(path)
            fp = self._session.get_local_fingerprint()
            self._append_crypto_log(f"[密钥] 已加载私钥，公钥指纹: {fp}")
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
            self._append_crypto_log(f"[密钥] 公钥已导出到: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出公钥失败: {e}")

    # ================================================================
    #  联系人选择
    # ================================================================

    def _on_contact_select(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        """用户在联系人列表中选择了一个联系人。"""
        sel = self._contact_list.curselection()
        if not sel:
            return
        peer_id = self._contact_list.get(sel[0])
        if peer_id == self._uid_var.get().strip():
            return  # 不和自己聊天
        self._current_peer = peer_id
        fp = self._session.get_peer_fingerprint(peer_id) or "未知"
        self._peer_label_var.set(f"与 {peer_id} 聊天  (公钥指纹: {fp})")
        self._append_chat_message("system", f"--- 已切换到与 {peer_id} 的对话 ---")

    # ================================================================
    #  消息发送
    # ================================================================

    def _send_message(self) -> None:
        """加密并发送消息。"""
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
            messagebox.showwarning("提示", f"尚未获取 {self._current_peer} 的公钥。")
            return

        try:
            # 加密
            self._append_crypto_log(f"[加密] 原文: \"{plaintext}\" (长度 {len(plaintext)})")
            encrypted = self._session.encrypt_for_peer(self._current_peer, plaintext)
            debug = encrypted.get("debug", {})
            self._append_crypto_log(f"[加密] AES 会话密钥已生成")
            self._append_crypto_log(f"[加密] wrapped_key 已生成 (对方指纹: {debug.get('peer_key_fingerprint', '?')})")
            self._append_crypto_log(f"[加密] 密文长度: {debug.get('ciphertext_length', '?')}")

            # 发送
            self._client.send_chat_message(self._current_peer, encrypted)
            self._append_crypto_log(f"[发送] 密文已发送给 {self._current_peer}")

            # 本地显示
            self._append_chat_message("me", plaintext)
            self._msg_var.set("")

        except Exception as e:
            messagebox.showerror("发送失败", str(e))
            self._append_crypto_log(f"[错误] 加密/发送失败: {e}")

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
        """根据事件类型分发处理。"""
        evt_type = event.get("event", "")

        if evt_type == "connected":
            self._status_var.set(f"已连接 (用户: {self._uid_var.get().strip()})")
            self._append_crypto_log("[连接] 已成功连接到服务端。")

        elif evt_type == "disconnected":
            self._status_var.set("已断开")
            self._btn_connect.config(state=tk.NORMAL)
            self._btn_disconnect.config(state=tk.DISABLED)
            self._append_crypto_log("[连接] 与服务端的连接已断开。")

        elif evt_type == "user_list":
            self._handle_user_list(event)

        elif evt_type == "chat_message":
            self._handle_incoming_chat(event)

        elif evt_type == "public_key":
            self._handle_incoming_public_key(event)

        elif evt_type == "error":
            err = event.get("message", "未知错误")
            self._append_crypto_log(f"[错误] {err}")

    def _handle_user_list(self, event: dict) -> None:
        """处理服务端广播的在线用户列表，自动导入公钥。"""
        data = event.get("data", {})
        payload = data.get("payload", {})
        users: dict = payload.get("users", {})

        my_id = self._uid_var.get().strip()
        self._contact_list.delete(0, tk.END)

        for uid, pub_pem in users.items():
            if uid == my_id:
                continue
            self._contact_list.insert(tk.END, uid)
            # 自动导入对方公钥
            if pub_pem and not self._session.has_peer_public_key(uid):
                try:
                    self._session.set_peer_public_key(uid, pub_pem)
                    fp = self._session.get_peer_fingerprint(uid)
                    self._append_crypto_log(f"[密钥] 自动导入 {uid} 的公钥 (指纹: {fp})")
                except Exception as e:
                    self._append_crypto_log(f"[警告] 导入 {uid} 公钥失败: {e}")

    def _handle_incoming_chat(self, event: dict) -> None:
        """处理收到的聊天密文消息：解密并显示。"""
        data = event.get("data", {})
        sender_id = str(data.get("sender_id", "?"))
        payload = data.get("payload", {})

        self._append_crypto_log(f"[接收] 收到来自 {sender_id} 的密文消息")
        self._append_crypto_log(f"[接收] wrapped_key 长度: {len(str(payload.get('wrapped_key', '')))}")

        try:
            result = self._session.decrypt_from_message(payload)
            plaintext = result["plaintext"]
            debug = result.get("debug", {})
            self._append_crypto_log(f"[解密] 解密成功，明文长度: {debug.get('plaintext_length', '?')}")

            # 如果当前正在和这个发送方聊天，直接显示
            # 否则也写入（可改进为分会话管理）
            self._append_chat_message("peer", plaintext, sender_id)

        except Exception as e:
            self._append_crypto_log(f"[错误] 解密失败: {e}")
            self._append_chat_message("system", f"[解密失败] 来自 {sender_id} 的消息无法解密。")

    def _handle_incoming_public_key(self, event: dict) -> None:
        """处理收到的公钥消息。"""
        data = event.get("data", {})
        sender_id = str(data.get("sender_id", "?"))
        pub_pem = data.get("payload", {}).get("public_key", "")
        if pub_pem:
            try:
                self._session.set_peer_public_key(sender_id, pub_pem)
                fp = self._session.get_peer_fingerprint(sender_id)
                self._append_crypto_log(f"[密钥] 收到 {sender_id} 的公钥 (指纹: {fp})")
            except Exception as e:
                self._append_crypto_log(f"[警告] 导入 {sender_id} 公钥失败: {e}")

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

    def _append_crypto_log(self, text: str) -> None:
        """向 Crypto Console 追加一条日志。"""
        self._crypto_log.config(state=tk.NORMAL)
        now = datetime.now().strftime("%H:%M:%S")
        self._crypto_log.insert(tk.END, f"[{now}] {text}\n")
        self._crypto_log.see(tk.END)
        self._crypto_log.config(state=tk.DISABLED)

    def _on_close(self) -> None:
        """窗口关闭前断开连接。"""
        if self._client.connected:
            self._client.disconnect()
        self.destroy()


def main() -> None:
    app = DesktopChatApp()
    app.mainloop()


if __name__ == "__main__":
    main()
