# 文件传输功能改造清单 (File Transfer Implementation Plan)

<!-- markdownlint-disable MD047 -->

## 0. 背景与范围

### 需求

在现有端到端加密聊天系统上增加文件传输功能：

- 支持发送照片、小文件（≤ 50 MB）
- 照片在聊天框内直接预览（缩略图）
- 文件使用与文本消息相同的混合加密方案（RSA-OAEP 包裹 AES-256-GCM 密钥）
- 桌面端与 Web 端均支持，且互通

### 设计策略

**小文件直传（≤ 5 MB）**：文件内容 Base64 编码后直接放入 JSON payload，走现有 WebSocket 通道，一条消息搞定。

**大文件分块传输（5 MB ~ 50 MB）**：将文件拆分为多个 chunk（每块 1 MB），每块独立加密后作为一条消息发送，接收方按序拼装还原。

> **为什么分 5 MB 界限？** Base64 膨胀约 33%，5 MB 文件 → ~6.7 MB JSON 文本，WebSocket 单帧可承受。50 MB 文件 → ~67 MB JSON，一次性发送会导致内存暴涨和 WebSocket 阻塞。

### 改动层级概览

```
aes_core.py              ← 新增 encrypt_bytes / decrypt_bytes
message_crypto.py        ← 新增 encrypt_file_data / decrypt_file_data
chat_protocol.py         ← 新增 MSG_FILE_TRANSFER / MSG_FILE_CHUNK 消息类型
session_manager.py       ← 新增 encrypt_file_for_peer / decrypt_file_from_message
chat_client.py           ← 新增 send_file_message / send_file_chunks
chat_server.py           ← 无代码改动（盲转发天然支持新消息类型）
desktop_chat_gui.py      ← 新增文件发送按钮 + 文件/图片渲染
web/crypto.js            ← 新增 encryptBytes / decryptBytes
web/protocol.js          ← 新增 MSG_FILE_TRANSFER / MSG_FILE_CHUNK
web/app.js               ← 新增文件发送 + 文件/图片渲染
tests/test_file_transfer.py ← 新增文件传输测试
```

---

## 1. aes_core.py — 新增字节加密

### 改动

新增两个函数，与 `encrypt_text` / `decrypt_text` 平行，但操作原始 `bytes`：

```python
def encrypt_bytes(data: bytes, key: bytes) -> dict[str, str]:
    """
    AES-256-GCM 加密原始字节数据。

    :param data: 待加密的原始字节（可以为空但不建议）。
    :param key: 32 字节 AES 密钥。
    :return: {"nonce": base64_str, "ciphertext": base64_str}
    """
    if not isinstance(data, bytes):
        raise TypeError("data 必须是 bytes 类型")
    _check_key(key)
    nonce = os.urandom(_NONCE_BYTES)       # 12 bytes
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, data, None)  # ciphertext + tag
    return {
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ct).decode(),
    }


def decrypt_bytes(cipher_payload: dict[str, str], key: bytes) -> bytes:
    """
    AES-256-GCM 解密原始字节数据。

    :return: 解密后的原始 bytes。
    """
    _check_key(key)
    nonce = base64.b64decode(cipher_payload["nonce"])
    ct = base64.b64decode(cipher_payload["ciphertext"])
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)
```

### 不改动

`encrypt_text` / `decrypt_text` 保持不变，现有文本聊天不受影响。

---

## 2. message_crypto.py — 新增文件混合加密

### 新增函数

```python
def encrypt_file_data(
    file_bytes: bytes,
    peer_public_key: rsa.RSAPublicKey,
    local_key_manager: rsa_core.RSAKeyManager | None = None,
) -> dict[str, object]:
    """
    混合加密文件数据：AES-256-GCM 加密文件内容 + RSA-OAEP 包裹 AES 密钥。

    :param file_bytes: 文件原始字节。
    :return: {"wrapped_key": b64, "nonce": b64, "ciphertext": b64, "debug": {...}}
    """
    session_key = aes_core.generate_aes_key(256)
    aes_result = aes_core.encrypt_bytes(file_bytes, session_key)
    wrapped_key_bytes = rsa_core.encrypt_bytes(session_key, peer_public_key)
    return {
        "wrapped_key": base64.b64encode(wrapped_key_bytes).decode(),
        "nonce": aes_result["nonce"],
        "ciphertext": aes_result["ciphertext"],
        "debug": {
            "plaintext_length": len(file_bytes),
            "session_key_bits": 256,
            "peer_key_fingerprint": _fingerprint(peer_public_key),
        },
    }


def decrypt_file_data(
    message_payload: dict[str, object],
    local_private_key: rsa.RSAPrivateKey,
) -> dict[str, object]:
    """
    混合解密文件数据。

    :return: {"file_bytes": bytes, "debug": {...}}
    """
    wrapped_key = base64.b64decode(str(message_payload["wrapped_key"]))
    session_key = rsa_core.decrypt_bytes(wrapped_key, local_private_key)
    file_bytes = aes_core.decrypt_bytes(
        {"nonce": str(message_payload["nonce"]),
         "ciphertext": str(message_payload["ciphertext"])},
        session_key,
    )
    return {
        "file_bytes": file_bytes,
        "debug": {"decrypted_length": len(file_bytes), "session_key_bits": 256},
    }
```

---

## 3. chat_protocol.py — 新增文件消息类型

### 新增常量

```python
MSG_FILE_TRANSFER = "file_transfer"   # 小文件整体传输（≤ 5MB）
MSG_FILE_CHUNK    = "file_chunk"      # 大文件分块传输（单块）
```

### 新增 payload 必填字段

```python
_PAYLOAD_REQUIRED_FIELDS[MSG_FILE_TRANSFER] = (
    "wrapped_key", "nonce", "ciphertext",  # 加密的文件内容
    "filename",                             # 原始文件名
    "filesize",                             # 原始文件大小（字节）
    "mime_type",                            # MIME 类型（如 image/png）
)

_PAYLOAD_REQUIRED_FIELDS[MSG_FILE_CHUNK] = (
    "wrapped_key", "nonce", "ciphertext",  # 加密的当前块
    "transfer_id",                          # 传输 ID（UUID，标识同一文件的所有块）
    "chunk_index",                          # 当前块索引（从 0 开始）
    "total_chunks",                         # 总块数
    "filename",                             # 原始文件名（首块和末块携带）
    "filesize",                             # 原始文件大小
    "mime_type",                            # MIME 类型
)
```

### 新增 receiver_id 要求

```python
_NEEDS_RECEIVER = {MSG_PUBLIC_KEY, MSG_CHAT_MESSAGE, MSG_ACK,
                   MSG_FILE_TRANSFER, MSG_FILE_CHUNK}   # ← 追加两项
```

### 新增构造函数

```python
def make_file_transfer_message(
    sender_id: str,
    receiver_id: str,
    encrypted_payload: dict[str, object],
    filename: str,
    filesize: int,
    mime_type: str,
) -> str:
    """构造小文件整体传输消息。"""
    payload = {
        "wrapped_key": encrypted_payload["wrapped_key"],
        "nonce": encrypted_payload["nonce"],
        "ciphertext": encrypted_payload["ciphertext"],
        "filename": filename,
        "filesize": filesize,
        "mime_type": mime_type,
    }
    return _build(MSG_FILE_TRANSFER, sender_id, receiver_id, payload)


def make_file_chunk_message(
    sender_id: str,
    receiver_id: str,
    encrypted_payload: dict[str, object],
    transfer_id: str,
    chunk_index: int,
    total_chunks: int,
    filename: str,
    filesize: int,
    mime_type: str,
) -> str:
    """构造大文件分块传输消息。"""
    payload = {
        "wrapped_key": encrypted_payload["wrapped_key"],
        "nonce": encrypted_payload["nonce"],
        "ciphertext": encrypted_payload["ciphertext"],
        "transfer_id": transfer_id,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "filename": filename,
        "filesize": filesize,
        "mime_type": mime_type,
    }
    return _build(MSG_FILE_CHUNK, sender_id, receiver_id, payload)
```

---

## 4. session_manager.py — 新增文件加解密封装

### 新增方法

```python
def encrypt_file_for_peer(self, peer_id: str, file_bytes: bytes) -> dict[str, object]:
    """使用对方公钥混合加密文件数据。"""
    peer_pub = self.get_peer_public_key(peer_id)
    return message_crypto.encrypt_file_data(
        file_bytes, peer_pub, self._key_manager,
    )

def decrypt_file_from_message(self, payload: dict[str, object]) -> dict[str, object]:
    """使用本地私钥混合解密文件数据。"""
    return message_crypto.decrypt_file_data(payload, self._key_manager.private_key)
```

---

## 5. chat_client.py — 新增文件发送方法

### 新增方法

```python
CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB 分块大小

def send_file_message(
    self, receiver_id: str, encrypted_payload: dict,
    filename: str, filesize: int, mime_type: str,
) -> None:
    """发送小文件（≤ 5MB，单条消息）。"""
    raw = chat_protocol.make_file_transfer_message(
        self._user_id, receiver_id, encrypted_payload,
        filename, filesize, mime_type,
    )
    self._enqueue_send(raw)

def send_file_chunks(
    self, receiver_id: str, file_bytes: bytes,
    encrypt_func,  # Callable[[bytes], dict] — 加密单块的函数
    filename: str, filesize: int, mime_type: str,
) -> None:
    """发送大文件（> 5MB，分块）。每块独立加密。"""
    import uuid
    transfer_id = str(uuid.uuid4())
    total_chunks = (len(file_bytes) + CHUNK_SIZE - 1) // CHUNK_SIZE

    for i in range(total_chunks):
        chunk = file_bytes[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        encrypted = encrypt_func(chunk)
        raw = chat_protocol.make_file_chunk_message(
            self._user_id, receiver_id, encrypted,
            transfer_id, i, total_chunks,
            filename, filesize, mime_type,
        )
        self._enqueue_send(raw)
```

---

## 6. chat_server.py — 无代码改动

**服务端不需要任何改动。** 原因：

1. `handle_connection` 中的消息分发：`MSG_FILE_TRANSFER` 和 `MSG_FILE_CHUNK` 不在已知处理分支中，会进入 `else` → `"忽略无需服务端处理的消息类型"`

   **⚠️ 但这意味着不会被转发！** 需要修正。

### 实际需要的最小改动

在 `handle_connection` 的消息分发中，将文件消息也路由到 `_handle_chat_message`：

```python
elif msg_type in (chat_protocol.MSG_CHAT_MESSAGE,
                  chat_protocol.MSG_FILE_TRANSFER,
                  chat_protocol.MSG_FILE_CHUNK):
    await self._handle_chat_message(msg, sender_id)
```

这是唯一的服务端改动 — `_handle_chat_message` 本身是盲转发，不解析 payload 内容，新消息类型可直接复用。

---

## 7. desktop_chat_gui.py — 桌面端 GUI 改造

### 7.1 新增文件发送按钮

在消息输入框旁新增一个"📎"按钮：

```python
# 在 _build_chat_input_area() 中，self._btn_send 旁边新增：
self._btn_file = tk.Button(input_frame, text="📎", command=self._send_file,
                           font=("Segoe UI Emoji", 12), width=3)
self._btn_file.pack(side=tk.RIGHT, padx=(0, 4))
```

### 7.2 新增 `_send_file()` 方法

```python
import mimetypes
from tkinter import filedialog

FILE_SIZE_LIMIT = 50 * 1024 * 1024    # 50 MB
SMALL_FILE_LIMIT = 5 * 1024 * 1024    # 5 MB

def _send_file(self) -> None:
    """选择文件并发送。"""
    if not self._client or not self._client.is_connected():
        self._crypto_log("error", "未连接服务器，无法发送文件")
        return
    peer_id = self._current_peer
    if not peer_id:
        self._crypto_log("error", "请先选择联系人")
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

    import os
    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)
    mime_type, _ = mimetypes.guess_type(filename)
    mime_type = mime_type or "application/octet-stream"

    if filesize > FILE_SIZE_LIMIT:
        self._crypto_log("error", f"文件过大: {filesize/1024/1024:.1f} MB，上限 50 MB")
        return

    with open(filepath, "rb") as f:
        file_bytes = f.read()

    self._crypto_log("encrypt", f"开始加密文件: {filename} ({filesize} bytes)")

    if filesize <= SMALL_FILE_LIMIT:
        # 小文件：单条消息
        encrypted = self._session.encrypt_file_for_peer(peer_id, file_bytes)
        self._client.send_file_message(
            peer_id, encrypted, filename, filesize, mime_type,
        )
        self._crypto_log("send", f"已发送文件: {filename}")
    else:
        # 大文件：分块
        encrypt_fn = lambda chunk: self._session.encrypt_file_for_peer(peer_id, chunk)
        self._client.send_file_chunks(
            peer_id, file_bytes, encrypt_fn, filename, filesize, mime_type,
        )
        self._crypto_log("send", f"已分块发送文件: {filename} ({(filesize-1)//chat_client.CHUNK_SIZE+1} 块)")

    # 本地显示（如果是图片，显示缩略图）
    self._append_file_message("me", filename, filesize, mime_type, file_bytes)
```

### 7.3 新增 `_handle_incoming_file()` 处理接收

在 `_poll_events()` 中新增对 `file_transfer` 事件的处理：

```python
# chat_client.py 中需要新增事件类型：
EVT_FILE_TRANSFER = "file_transfer"
EVT_FILE_CHUNK    = "file_chunk"

# desktop_chat_gui.py _poll_events 中新增分支：
elif evt_type == chat_client.EVT_FILE_TRANSFER:
    self._handle_incoming_file(event["data"])
elif evt_type == chat_client.EVT_FILE_CHUNK:
    self._handle_incoming_file_chunk(event["data"])
```

```python
def _handle_incoming_file(self, msg: dict) -> None:
    """处理接收到的小文件。"""
    sender_id = msg["sender_id"]
    payload = msg["payload"]
    filename = payload["filename"]
    filesize = payload["filesize"]
    mime_type = payload["mime_type"]

    self._crypto_log("recv", f"收到来自 {sender_id} 的文件: {filename}")
    try:
        result = self._session.decrypt_file_from_message(payload)
        file_bytes = result["file_bytes"]
        self._crypto_log("decrypt", f"文件解密成功: {len(file_bytes)} bytes")
        self._append_file_message("peer", filename, filesize, mime_type, file_bytes, sender_id)
    except Exception as e:
        self._crypto_log("error", f"文件解密失败: {e}")
```

### 7.4 大文件分块接收缓冲

```python
# 在 __init__ 中新增：
self._chunk_buffers: dict[str, dict] = {}
# 结构: {transfer_id: {"chunks": {index: bytes}, "total": int, "filename": str, ...}}

def _handle_incoming_file_chunk(self, msg: dict) -> None:
    """处理分块文件的单个块。"""
    sender_id = msg["sender_id"]
    payload = msg["payload"]
    transfer_id = payload["transfer_id"]
    chunk_index = payload["chunk_index"]
    total_chunks = payload["total_chunks"]
    filename = payload["filename"]
    filesize = payload["filesize"]
    mime_type = payload["mime_type"]

    # 解密当前块
    try:
        result = self._session.decrypt_file_from_message(payload)
        chunk_bytes = result["file_bytes"]
    except Exception as e:
        self._crypto_log("error", f"文件块 {chunk_index}/{total_chunks} 解密失败: {e}")
        return

    # 存入缓冲
    if transfer_id not in self._chunk_buffers:
        self._chunk_buffers[transfer_id] = {
            "chunks": {}, "total": total_chunks,
            "filename": filename, "filesize": filesize,
            "mime_type": mime_type, "sender_id": sender_id,
        }
        self._crypto_log("recv", f"开始接收分块文件: {filename} ({total_chunks} 块)")

    buf = self._chunk_buffers[transfer_id]
    buf["chunks"][chunk_index] = chunk_bytes
    self._crypto_log("recv", f"收到块 {chunk_index+1}/{total_chunks}")

    # 检查是否全部到齐
    if len(buf["chunks"]) == total_chunks:
        # 按序拼装
        file_bytes = b"".join(buf["chunks"][i] for i in range(total_chunks))
        self._crypto_log("decrypt", f"文件拼装完成: {filename} ({len(file_bytes)} bytes)")
        self._append_file_message("peer", filename, filesize, mime_type, file_bytes, sender_id)
        del self._chunk_buffers[transfer_id]
```

### 7.5 新增 `_append_file_message()` — 聊天区文件/图片渲染

```python
import io
from PIL import Image, ImageTk  # 需新增 Pillow 依赖

# 图片 MIME 类型集合
IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/bmp", "image/webp"}
# 缩略图最大尺寸
THUMBNAIL_MAX = (300, 300)

def _append_file_message(self, role: str, filename: str, filesize: int,
                          mime_type: str, file_bytes: bytes,
                          sender_id: str = "") -> None:
    """在聊天区显示文件消息，图片自动预览。"""
    tag = "me" if role == "me" else "peer"
    prefix = "我" if role == "me" else sender_id
    time_str = time.strftime("%H:%M:%S")
    size_str = self._format_size(filesize)

    self._chat_display.config(state=tk.NORMAL)

    # 插入文件头信息
    self._chat_display.insert(tk.END, f"[{time_str}] {prefix}: ", tag)
    self._chat_display.insert(tk.END, f"📎 {filename} ({size_str})\n", tag)

    # 如果是图片，显示缩略图
    if mime_type in IMAGE_MIMES:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            img.thumbnail(THUMBNAIL_MAX, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            # 保持引用防止被 GC
            if not hasattr(self, "_image_refs"):
                self._image_refs = []
            self._image_refs.append(photo)
            self._chat_display.image_create(tk.END, image=photo)
            self._chat_display.insert(tk.END, "\n")
        except Exception:
            self._chat_display.insert(tk.END, "[图片预览失败]\n", "system")

    # 插入"保存"按钮（使用可点击文本模拟）
    save_tag = f"save_{id(file_bytes)}"
    self._chat_display.tag_config(save_tag, foreground="#4fc3f7", underline=True)
    self._chat_display.tag_bind(save_tag, "<Button-1>",
        lambda e, fb=file_bytes, fn=filename: self._save_file(fb, fn))
    self._chat_display.insert(tk.END, "[点击保存文件]", save_tag)
    self._chat_display.insert(tk.END, "\n\n")

    self._chat_display.config(state=tk.DISABLED)
    self._chat_display.see(tk.END)

def _save_file(self, file_bytes: bytes, default_name: str) -> None:
    """弹出保存对话框，将解密的文件保存到本地。"""
    filepath = filedialog.asksaveasfilename(
        initialfile=default_name,
        title="保存文件",
    )
    if filepath:
        with open(filepath, "wb") as f:
            f.write(file_bytes)
        self._crypto_log("recv", f"文件已保存: {filepath}")

@staticmethod
def _format_size(size: int) -> str:
    """格式化文件大小。"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / 1024 / 1024:.1f} MB"
```

---

## 8. Web 端改造

### 8.1 web/crypto.js — 新增字节加密

```javascript
/**
 * AES-GCM 加密原始字节。
 * @param {Uint8Array} data
 * @param {CryptoKey} aesKey
 * @returns {Promise<{nonce: string, ciphertext: string}>}
 */
export async function aesEncryptBytes(data, aesKey) {
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce, tagLength: 128 },
    aesKey,
    data,
  );
  return {
    nonce: btoa(String.fromCharCode(...nonce)),
    ciphertext: btoa(String.fromCharCode(...new Uint8Array(ct))),
  };
}

/**
 * AES-GCM 解密原始字节。
 * @returns {Promise<Uint8Array>}
 */
export async function aesDecryptBytes(nonce64, ciphertext64, aesKey) {
  const nonce = Uint8Array.from(atob(nonce64), (c) => c.charCodeAt(0));
  const ct = Uint8Array.from(atob(ciphertext64), (c) => c.charCodeAt(0));
  const plainBuf = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce, tagLength: 128 },
    aesKey,
    ct,
  );
  return new Uint8Array(plainBuf);
}

/**
 * 混合加密文件字节。
 */
export async function encryptFileData(fileBytes, peerPublicKey) {
  const rawKey = crypto.getRandomValues(new Uint8Array(32));
  const aesKey = await crypto.subtle.importKey(
    "raw",
    rawKey,
    { name: "AES-GCM" },
    false,
    ["encrypt"],
  );
  const aesResult = await aesEncryptBytes(fileBytes, aesKey);
  const wrappedKey = await rsaWrapKey(rawKey, peerPublicKey);
  return {
    wrapped_key: wrappedKey,
    nonce: aesResult.nonce,
    ciphertext: aesResult.ciphertext,
  };
}

/**
 * 混合解密文件字节。
 * @returns {Promise<Uint8Array>}
 */
export async function decryptFileData(payload, localPrivateKey) {
  const rawKey = await rsaUnwrapKey(payload.wrapped_key, localPrivateKey);
  const aesKey = await crypto.subtle.importKey(
    "raw",
    rawKey,
    { name: "AES-GCM" },
    false,
    ["decrypt"],
  );
  return aesDecryptBytes(payload.nonce, payload.ciphertext, aesKey);
}
```

### 8.2 web/protocol.js — 新增消息类型

```javascript
export const MSG_FILE_TRANSFER = "file_transfer";
export const MSG_FILE_CHUNK = "file_chunk";

// 在 VALID_TYPES Set 中追加
// 在 NEEDS_RECEIVER Set 中追加
// 在 PAYLOAD_REQUIRED_FIELDS 中追加

export function makeFileTransferMessage(
  senderId,
  receiverId,
  encrypted,
  filename,
  filesize,
  mimeType,
) {
  return buildEnvelope(MSG_FILE_TRANSFER, senderId, receiverId, {
    wrapped_key: encrypted.wrapped_key,
    nonce: encrypted.nonce,
    ciphertext: encrypted.ciphertext,
    filename,
    filesize,
    mime_type: mimeType,
  });
}

export function makeFileChunkMessage(
  senderId,
  receiverId,
  encrypted,
  transferId,
  chunkIndex,
  totalChunks,
  filename,
  filesize,
  mimeType,
) {
  return buildEnvelope(MSG_FILE_CHUNK, senderId, receiverId, {
    wrapped_key: encrypted.wrapped_key,
    nonce: encrypted.nonce,
    ciphertext: encrypted.ciphertext,
    transfer_id: transferId,
    chunk_index: chunkIndex,
    total_chunks: totalChunks,
    filename,
    filesize,
    mime_type: mimeType,
  });
}
```

### 8.3 web/app.js — 文件发送与渲染

#### 新增 UI 元素

在 `index.html` 的消息输入区新增文件按钮：

```html
<div id="chat-input-area">
  <input
    type="file"
    id="file-input"
    style="display:none"
    accept="image/*,.pdf,.doc,.docx,.txt,.zip"
  />
  <button id="btn-file" class="btn" title="发送文件">📎</button>
  <input type="text" id="msg-input" placeholder="输入消息..." disabled />
  <button id="btn-send" class="btn btn-primary" style="width:auto;" disabled>
    发送
  </button>
</div>
```

#### 新增发送逻辑

```javascript
const SMALL_FILE_LIMIT = 5 * 1024 * 1024;
const FILE_SIZE_LIMIT = 50 * 1024 * 1024;
const CHUNK_SIZE = 1 * 1024 * 1024;

dom.btnFile = document.getElementById("btn-file");
dom.fileInput = document.getElementById("file-input");

dom.btnFile.addEventListener("click", () => dom.fileInput.click());
dom.fileInput.addEventListener("change", handleFileSelect);

async function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  dom.fileInput.value = ""; // 重置

  if (file.size > FILE_SIZE_LIMIT) {
    cryptoLog(
      "error",
      `文件过大: ${(file.size / 1024 / 1024).toFixed(1)} MB，上限 50 MB`,
    );
    return;
  }
  if (!state.activePeer || !state.peerKeys.has(state.activePeer)) {
    cryptoLog("error", "请先选择联系人");
    return;
  }

  const arrayBuf = await file.arrayBuffer();
  const fileBytes = new Uint8Array(arrayBuf);
  const peerKey = state.peerKeys.get(state.activePeer);
  const mimeType = file.type || "application/octet-stream";

  cryptoLog("encrypt", `开始加密文件: ${file.name} (${file.size} bytes)`);

  if (file.size <= SMALL_FILE_LIMIT) {
    // 小文件单条
    const encrypted = await Crypto.encryptFileData(fileBytes, peerKey);
    const msg = Protocol.makeFileTransferMessage(
      state.userId,
      state.activePeer,
      encrypted,
      file.name,
      file.size,
      mimeType,
    );
    state.ws.send(msg);
    cryptoLog("send", `文件已发送: ${file.name}`);
  } else {
    // 大文件分块
    const transferId = crypto.randomUUID();
    const totalChunks = Math.ceil(fileBytes.length / CHUNK_SIZE);
    for (let i = 0; i < totalChunks; i++) {
      const chunk = fileBytes.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
      const encrypted = await Crypto.encryptFileData(chunk, peerKey);
      const msg = Protocol.makeFileChunkMessage(
        state.userId,
        state.activePeer,
        encrypted,
        transferId,
        i,
        totalChunks,
        file.name,
        file.size,
        mimeType,
      );
      state.ws.send(msg);
      cryptoLog("send", `已发送块 ${i + 1}/${totalChunks}`);
    }
  }

  // 本地显示
  addFileMessage(
    state.activePeer,
    "sent",
    file.name,
    file.size,
    mimeType,
    fileBytes,
  );
}
```

#### 新增接收处理

在 `handleMessage()` 的 switch 中新增：

```javascript
case Protocol.MSG_FILE_TRANSFER:
    await handleFileTransfer(msg);
    break;
case Protocol.MSG_FILE_CHUNK:
    await handleFileChunk(msg);
    break;
```

```javascript
// 分块接收缓冲
const chunkBuffers = new Map(); // transferId → {chunks: Map, total, filename, ...}

async function handleFileTransfer(msg) {
  const payload = msg.payload;
  cryptoLog("recv", `收到来自 ${msg.sender_id} 的文件: ${payload.filename}`);
  try {
    const fileBytes = await Crypto.decryptFileData(
      payload,
      state.keyPair.privateKey,
    );
    cryptoLog("decrypt", `文件解密成功: ${fileBytes.length} bytes`);
    addFileMessage(
      msg.sender_id,
      "received",
      payload.filename,
      payload.filesize,
      payload.mime_type,
      fileBytes,
    );
  } catch (e) {
    cryptoLog("error", `文件解密失败: ${e.message}`);
  }
}

async function handleFileChunk(msg) {
  const p = msg.payload;
  const tid = p.transfer_id;

  try {
    const chunkBytes = await Crypto.decryptFileData(
      p,
      state.keyPair.privateKey,
    );
    if (!chunkBuffers.has(tid)) {
      chunkBuffers.set(tid, {
        chunks: new Map(),
        total: p.total_chunks,
        filename: p.filename,
        filesize: p.filesize,
        mimeType: p.mime_type,
        senderId: msg.sender_id,
      });
      cryptoLog(
        "recv",
        `开始接收分块文件: ${p.filename} (${p.total_chunks} 块)`,
      );
    }
    const buf = chunkBuffers.get(tid);
    buf.chunks.set(p.chunk_index, chunkBytes);
    cryptoLog("recv", `收到块 ${p.chunk_index + 1}/${p.total_chunks}`);

    if (buf.chunks.size === buf.total) {
      // 拼装
      let totalLen = 0;
      for (const c of buf.chunks.values()) totalLen += c.length;
      const assembled = new Uint8Array(totalLen);
      let offset = 0;
      for (let i = 0; i < buf.total; i++) {
        const c = buf.chunks.get(i);
        assembled.set(c, offset);
        offset += c.length;
      }
      cryptoLog(
        "decrypt",
        `文件拼装完成: ${buf.filename} (${assembled.length} bytes)`,
      );
      addFileMessage(
        buf.senderId,
        "received",
        buf.filename,
        buf.filesize,
        buf.mimeType,
        assembled,
      );
      chunkBuffers.delete(tid);
    }
  } catch (e) {
    cryptoLog("error", `文件块解密失败: ${e.message}`);
  }
}
```

#### 新增聊天区文件渲染

```javascript
function addFileMessage(peerId, type, filename, filesize, mimeType, fileBytes) {
  if (!state.chatHistory.has(peerId)) {
    state.chatHistory.set(peerId, []);
  }
  const entry = {
    type,
    time: new Date().toLocaleTimeString(),
    isFile: true,
    filename,
    filesize,
    mimeType,
    fileBytes,
  };
  state.chatHistory.get(peerId).push(entry);
  if (peerId === state.activePeer) {
    appendFileToUI(entry);
  }
}

function appendFileToUI(entry) {
  const emptyState = dom.chatMessages.querySelector(".empty-state");
  if (emptyState) emptyState.remove();

  const div = document.createElement("div");
  div.className = `message ${entry.type}`;

  const sizeStr = formatSize(entry.filesize);
  let html = `<div class="file-info">📎 ${escapeHtml(entry.filename)} (${sizeStr})</div>`;

  // 图片预览
  if (entry.mimeType && entry.mimeType.startsWith("image/")) {
    const blob = new Blob([entry.fileBytes], { type: entry.mimeType });
    const url = URL.createObjectURL(blob);
    html += `<img src="${url}" class="chat-image" style="max-width:300px;max-height:300px;border-radius:8px;margin:4px 0;cursor:pointer;" onclick="window.open('${url}')">`;
  }

  // 保存按钮
  html += `<div class="msg-meta">${entry.time}</div>`;
  div.innerHTML = html;

  // 保存按钮
  const saveBtn = document.createElement("a");
  saveBtn.textContent = "💾 保存";
  saveBtn.className = "file-save-link";
  saveBtn.style.cssText =
    "color:#4fc3f7;cursor:pointer;font-size:12px;text-decoration:underline;";
  saveBtn.addEventListener("click", () => {
    const blob = new Blob([entry.fileBytes], { type: entry.mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = entry.filename;
    a.click();
    URL.revokeObjectURL(url);
  });
  div.appendChild(saveBtn);

  dom.chatMessages.appendChild(div);
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}
```

#### 修改 `appendMessageToUI` 和 `renderChatHistory`

`renderChatHistory` 中需区分文件消息和文本消息：

```javascript
for (const entry of history) {
  if (entry.isFile) {
    appendFileToUI(entry);
  } else {
    appendMessageToUI(entry);
  }
}
```

### 8.4 web/style.css — 新增样式

```css
/* 文件消息样式 */
.file-info {
  font-size: 13px;
  padding: 2px 0;
}
.chat-image {
  display: block;
  max-width: 300px;
  max-height: 300px;
  border-radius: 8px;
  margin: 4px 0;
  cursor: pointer;
}
.file-save-link {
  display: inline-block;
  margin-top: 2px;
}
#btn-file {
  width: 36px;
  font-size: 16px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
}
#btn-file:hover {
  background: var(--hover);
  color: var(--text-primary);
}
```

---

## 9. 依赖变更

### Python

```
Pillow>=10.0.0   # 桌面端图片缩略图预览
```

更新 `pyproject.toml` 和 `requirements.txt`。

### Web 端

无新依赖（浏览器原生 File API + Blob + URL.createObjectURL）。

---

## 10. tests/test_file_transfer.py — 测试清单

```python
class TestAesBytesEncryption(unittest.TestCase):
    """AES-GCM 字节加密/解密。"""
    def test_encrypt_decrypt_bytes_roundtrip(self): ...
    def test_encrypt_empty_bytes(self): ...
    def test_encrypt_large_bytes(self): ...       # 5 MB
    def test_decrypt_tampered_ciphertext(self): ...  # InvalidTag

class TestFileDataCrypto(unittest.TestCase):
    """混合加密文件数据。"""
    def test_encrypt_decrypt_file_roundtrip(self): ...
    def test_encrypt_image_bytes(self): ...       # 模拟 PNG 文件头
    def test_large_file_roundtrip(self): ...      # 10 MB

class TestFileProtocol(unittest.TestCase):
    """文件消息协议。"""
    def test_make_file_transfer_message(self): ...
    def test_parse_file_transfer_message(self): ...
    def test_make_file_chunk_message(self): ...
    def test_parse_file_chunk_message(self): ...
    def test_file_transfer_requires_receiver_id(self): ...
    def test_file_chunk_payload_validation(self): ...

class TestChunking(unittest.TestCase):
    """分块逻辑。"""
    def test_chunk_count_calculation(self): ...
    def test_chunk_reassembly(self): ...          # 拆分→逐块加密→逐块解密→拼装→比对原文件
```

---

## 11. 实施顺序

```
步骤 1: aes_core.py          — 新增 encrypt_bytes / decrypt_bytes          (~20 行)
步骤 2: message_crypto.py    — 新增 encrypt_file_data / decrypt_file_data  (~40 行)
步骤 3: chat_protocol.py     — 新增消息类型 + 构造函数                      (~50 行)
步骤 4: session_manager.py   — 新增封装方法                                 (~15 行)
步骤 5: tests/               — 编写并运行测试                               (~100 行)
步骤 6: chat_server.py       — 路由分支追加 2 个消息类型                     (~3 行)
步骤 7: chat_client.py       — 新增发送方法 + 事件类型                       (~40 行)
步骤 8: desktop_chat_gui.py  — UI 改造（文件按钮 + 渲染 + 分块接收）         (~150 行)
步骤 9: web/crypto.js        — 新增字节加密 API                              (~50 行)
步骤 10: web/protocol.js     — 新增消息类型                                  (~30 行)
步骤 11: web/app.js + html   — 文件发送 + 接收 + 渲染                        (~150 行)
步骤 12: web/style.css       — 文件样式                                      (~20 行)
步骤 13: 联调测试            — 桌面↔桌面 / Web↔Web / 桌面↔Web 文件互传
```

**预计新增代码量：~670 行（Python ~265 行 + JS ~300 行 + HTML/CSS ~55 行 + 测试 ~100 行）**

---

## 12. 注意事项

### 安全性

- 每块文件使用**独立的一次性 AES-256 密钥**，与文本消息保持一致的安全等级。
- 文件名在 payload 中是明文（服务端可见），但文件内容是密文。如需隐藏文件名，可将 filename 也纳入加密内容。
- 大文件的 `transfer_id` 是 UUID，不可猜测。

### 性能

- 50 MB 文件 Base64 后约 67 MB，分 50 块 × 1 MB，每块加密 + Base64 → ~1.35 MB JSON。WebSocket 单帧可承受。
- 加密/解密是 CPU 密集操作，大文件建议在异步线程中处理（桌面端已有后台线程模型）。

### 兼容性

- 旧版客户端（无文件传输支持）收到 `file_transfer` / `file_chunk` 消息类型时，`parse_message` 的 strict 模式会因未知类型而报错，非 strict 模式下会忽略。需确保 `parse_message` 的 `VALID_TYPES` 集合更新。
- Web 端 `File API` 和 `Blob` 在所有现代浏览器中均可用（Chrome 76+、Firefox 69+、Safari 14+）。
