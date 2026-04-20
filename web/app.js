/**
 * SecureChat Web 客户端主应用
 *
 * 整合 WebSocket 通信、加密模块和 UI 交互，
 * 实现与桌面端完全互通的端到端加密聊天。
 */

import * as Crypto from "./crypto.js";
import * as Protocol from "./protocol.js";

// ── 应用状态 ──────────────────────────────────────────────

const state = {
    /** @type {WebSocket|null} */
    ws: null,
    /** @type {CryptoKeyPair|null} */
    keyPair: null,
    /** @type {string} 本地公钥 PEM */
    publicKeyPem: "",
    /** @type {string} 本地公钥指纹 */
    localFingerprint: "",
    /** @type {string} 当前用户 ID */
    userId: "",
    /** @type {string} 当前聊天对象 ID */
    activePeer: "",
    /** @type {Map<string, CryptoKey>} userId → CryptoKey (对方 RSA 公钥) */
    peerKeys: new Map(),
    /** @type {Map<string, string>} userId → 公钥指纹 */
    peerFingerprints: new Map(),
    /** @type {Map<string, string>} userId → 公钥 PEM */
    peerPems: new Map(),
    /** @type {Map<string, Array>} userId → 消息历史 [{type, text, time}] */
    chatHistory: new Map(),
    /** @type {number|null} 心跳定时器 */
    heartbeatTimer: null,
    /** @type {Map<string, object>} transferId → 分块缓冲 */
    chunkBuffers: new Map(),
};

// 文件大小限制
const SMALL_FILE_LIMIT = 5 * 1024 * 1024;
const FILE_SIZE_LIMIT = 50 * 1024 * 1024;
const CHUNK_SIZE = 1 * 1024 * 1024;

// ── DOM 元素引用 ─────────────────────────────────────────

const dom = {
    serverUrl:        document.getElementById("server-url"),
    userId:           document.getElementById("user-id"),
    btnConnect:       document.getElementById("btn-connect"),
    btnDisconnect:    document.getElementById("btn-disconnect"),
    btnGenerateKeys:  document.getElementById("btn-generate-keys"),
    keyInfo:          document.getElementById("key-info"),
    contactsList:     document.getElementById("contacts-list"),
    chatHeader:       document.getElementById("chat-header"),
    chatMessages:     document.getElementById("chat-messages"),
    msgInput:         document.getElementById("msg-input"),
    btnSend:          document.getElementById("btn-send"),
    btnFile:          document.getElementById("btn-file"),
    fileInput:        document.getElementById("file-input"),
    connStatus:       document.getElementById("connection-status"),
    cryptoConsole:    document.getElementById("crypto-console"),
};

// ── Crypto Console 日志 ──────────────────────────────────

let cryptoLogStarted = false;

function cryptoLog(tag, text) {
    if (!cryptoLogStarted) {
        dom.cryptoConsole.innerHTML = "";
        cryptoLogStarted = true;
    }
    const line = document.createElement("div");
    line.className = `crypto-line log-${tag}`;
    const time = new Date().toLocaleTimeString();
    line.textContent = `[${time}] ${text}`;
    dom.cryptoConsole.appendChild(line);
    dom.cryptoConsole.scrollTop = dom.cryptoConsole.scrollHeight;
}

// ── 密钥管理 ─────────────────────────────────────────────

dom.btnGenerateKeys.addEventListener("click", async () => {
    dom.btnGenerateKeys.disabled = true;
    dom.btnGenerateKeys.textContent = "生成中...";
    cryptoLog("key", "正在生成 RSA-2048 密钥对...");

    try {
        state.keyPair = await Crypto.generateRSAKeyPair();
        state.publicKeyPem = await Crypto.exportPublicKeyPEM(state.keyPair.publicKey);
        state.localFingerprint = await Crypto.getPublicKeyFingerprint(state.keyPair.publicKey);

        dom.keyInfo.innerHTML =
            `✅ 密钥已生成<br>指纹: <span class="fingerprint">${state.localFingerprint}</span>`;
        cryptoLog("key", `RSA-2048 密钥对已生成`);
        cryptoLog("key", `本地公钥指纹: ${state.localFingerprint}`);
    } catch (e) {
        dom.keyInfo.textContent = `❌ 生成失败: ${e.message}`;
        cryptoLog("error", `密钥生成失败: ${e.message}`);
    }

    dom.btnGenerateKeys.disabled = false;
    dom.btnGenerateKeys.textContent = "生成 RSA-2048 密钥对";
});

// ── WebSocket 连接管理 ───────────────────────────────────

function setConnected(connected) {
    dom.btnConnect.disabled = connected;
    dom.btnDisconnect.disabled = !connected;
    dom.serverUrl.disabled = connected;
    dom.userId.disabled = connected;
    dom.connStatus.textContent = connected ? "已连接" : "未连接";
    dom.connStatus.className = connected ? "connected" : "disconnected";
    if (!connected) {
        dom.msgInput.disabled = true;
        dom.btnSend.disabled = true;
    }
}

dom.btnConnect.addEventListener("click", () => {
    const serverUrl = dom.serverUrl.value.trim();
    const userId = dom.userId.value.trim();

    if (!userId) {
        alert("请输入用户 ID");
        return;
    }
    if (!state.keyPair) {
        alert("请先生成 RSA 密钥对");
        return;
    }

    state.userId = userId;
    connectWebSocket(serverUrl, userId);
});

dom.btnDisconnect.addEventListener("click", () => {
    disconnectWebSocket();
});

function connectWebSocket(url, userId) {
    cryptoLog("conn", `正在连接 ${url} ...`);

    try {
        state.ws = new WebSocket(url);
    } catch (e) {
        cryptoLog("error", `WebSocket 创建失败: ${e.message}`);
        return;
    }

    state.ws.onopen = () => {
        cryptoLog("conn", "WebSocket 连接已建立");
        setConnected(true);

        // 发送 register 消息
        const regMsg = Protocol.makeRegisterMessage(userId, state.publicKeyPem);
        state.ws.send(regMsg);
        cryptoLog("conn", `已发送注册消息 (用户: ${userId})`);

        // 启动心跳
        state.heartbeatTimer = setInterval(() => {
            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send(Protocol.makeHeartbeatMessage(userId));
            }
        }, 30000);
    };

    state.ws.onmessage = (event) => {
        handleMessage(event.data);
    };

    state.ws.onclose = () => {
        cryptoLog("conn", "WebSocket 连接已关闭");
        cleanup();
    };

    state.ws.onerror = (err) => {
        cryptoLog("error", "WebSocket 连接错误");
        cleanup();
    };
}

function disconnectWebSocket() {
    if (state.ws) {
        state.ws.close();
    }
    cleanup();
}

function cleanup() {
    setConnected(false);
    if (state.heartbeatTimer) {
        clearInterval(state.heartbeatTimer);
        state.heartbeatTimer = null;
    }
    state.ws = null;
    state.peerKeys.clear();
    state.peerFingerprints.clear();
    state.peerPems.clear();
    state.activePeer = "";
    renderContacts({});
    dom.chatHeader.textContent = "选择一个联系人开始聊天";
    dom.chatMessages.innerHTML = `
        <div class="empty-state">
            <div class="icon">💬</div>
            <div>选择联系人后即可开始端到端加密聊天</div>
        </div>`;
}

// ── 消息处理 ─────────────────────────────────────────────

async function handleMessage(raw) {
    let msg;
    try {
        msg = Protocol.parseMessage(raw);
    } catch (e) {
        cryptoLog("error", `消息解析失败: ${e.message}`);
        return;
    }

    switch (msg.type) {
        case Protocol.MSG_USER_LIST:
            await handleUserList(msg);
            break;
        case Protocol.MSG_PUBLIC_KEY:
            await handlePublicKey(msg);
            break;
        case Protocol.MSG_CHAT_MESSAGE:
            await handleChatMessage(msg);
            break;
        case Protocol.MSG_FILE_TRANSFER:
            await handleFileTransfer(msg);
            break;
        case Protocol.MSG_FILE_CHUNK:
            await handleFileChunk(msg);
            break;
        case Protocol.MSG_ACK:
            cryptoLog("recv", `收到 ACK: ${msg.payload.ack_for}`);
            break;
        case Protocol.MSG_ERROR:
            cryptoLog("error", `服务端错误: ${msg.payload.message}`);
            break;
        default:
            break;
    }
}

async function handleUserList(msg) {
    const users = msg.payload.users || {};
    cryptoLog("conn", `在线用户列表更新: ${Object.keys(users).length} 人`);

    // 导入所有用户的公钥
    for (const [uid, pem] of Object.entries(users)) {
        if (uid === state.userId) continue;
        if (pem && !state.peerKeys.has(uid)) {
            try {
                const key = await Crypto.importPublicKeyFromPEM(pem);
                const fp = await Crypto.getPublicKeyFingerprint(key);
                state.peerKeys.set(uid, key);
                state.peerFingerprints.set(uid, fp);
                state.peerPems.set(uid, pem);
                cryptoLog("key", `已导入 ${uid} 的公钥 [${fp}]`);
            } catch (e) {
                cryptoLog("error", `导入 ${uid} 公钥失败: ${e.message}`);
            }
        }
    }

    renderContacts(users);
}

async function handlePublicKey(msg) {
    const senderId = msg.sender_id;
    const pem = msg.payload.public_key;
    cryptoLog("recv", `收到 ${senderId} 的公钥`);

    try {
        const key = await Crypto.importPublicKeyFromPEM(pem);
        const fp = await Crypto.getPublicKeyFingerprint(key);
        state.peerKeys.set(senderId, key);
        state.peerFingerprints.set(senderId, fp);
        state.peerPems.set(senderId, pem);
        cryptoLog("key", `已导入 ${senderId} 的公钥 [${fp}]`);
    } catch (e) {
        cryptoLog("error", `导入 ${senderId} 公钥失败: ${e.message}`);
    }
}

async function handleChatMessage(msg) {
    const senderId = msg.sender_id;
    const payload = msg.payload;

    cryptoLog("recv", `收到来自 ${senderId} 的加密消息`);
    cryptoLog("decrypt", `wrapped_key 长度: ${payload.wrapped_key?.length || 0}`);
    cryptoLog("decrypt", `nonce 长度: ${payload.nonce?.length || 0}`);
    cryptoLog("decrypt", `ciphertext 长度: ${payload.ciphertext?.length || 0}`);

    if (!state.keyPair) {
        cryptoLog("error", "本地密钥不存在，无法解密");
        return;
    }

    try {
        cryptoLog("decrypt", "开始 RSA-OAEP 解包会话密钥...");
        const result = await Crypto.decryptMessage(payload, state.keyPair.privateKey);
        cryptoLog("decrypt", `AES-GCM 解密成功，明文长度: ${result.plaintext.length}`);
        cryptoLog("decrypt", "✅ 解密完成");

        // 存储消息
        addChatMessage(senderId, "received", result.plaintext);

        // 发送 ACK
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            const ack = Protocol.makeAckMessage(state.userId, senderId, msg.timestamp);
            state.ws.send(ack);
        }
    } catch (e) {
        cryptoLog("error", `解密失败: ${e.message}`);
        addChatMessage(senderId, "system", `[解密失败: ${e.message}]`);
    }
}

// ── 发送消息 ─────────────────────────────────────────────

async function sendMessage() {
    const text = dom.msgInput.value.trim();
    if (!text || !state.activePeer) return;

    const peerKey = state.peerKeys.get(state.activePeer);
    if (!peerKey) {
        cryptoLog("error", `未找到 ${state.activePeer} 的公钥`);
        return;
    }

    dom.msgInput.value = "";

    try {
        cryptoLog("encrypt", `开始加密消息 (${text.length} 字符)`);
        cryptoLog("encrypt", "生成随机 AES-256 会话密钥...");
        const encrypted = await Crypto.encryptMessage(text, peerKey, state.keyPair.publicKey);

        cryptoLog("encrypt", `AES-GCM 加密完成`);
        cryptoLog("encrypt", `RSA-OAEP 包裹会话密钥完成`);
        cryptoLog("encrypt", `wrapped_key: ${encrypted.wrapped_key.length} chars`);
        cryptoLog("encrypt", `nonce: ${encrypted.nonce.length} chars`);
        cryptoLog("encrypt", `ciphertext: ${encrypted.ciphertext.length} chars`);
        cryptoLog("encrypt", `对端指纹: ${encrypted.debug.peer_key_fingerprint}`);

        const chatMsg = Protocol.makeChatMessage(state.userId, state.activePeer, encrypted);
        state.ws.send(chatMsg);

        cryptoLog("send", `已发送加密消息至 ${state.activePeer}`);
        addChatMessage(state.activePeer, "sent", text);
    } catch (e) {
        cryptoLog("error", `加密/发送失败: ${e.message}`);
    }
}

dom.btnSend.addEventListener("click", sendMessage);
dom.msgInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// ── 文件发送 ───────────────────────────────────────────────

dom.btnFile.addEventListener("click", () => dom.fileInput.click());
dom.fileInput.addEventListener("change", handleFileSelect);

async function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    dom.fileInput.value = "";

    if (file.size > FILE_SIZE_LIMIT) {
        cryptoLog("error", `文件过大: ${(file.size / 1024 / 1024).toFixed(1)} MB，上限 50 MB`);
        return;
    }
    if (!state.activePeer || !state.peerKeys.has(state.activePeer)) {
        cryptoLog("error", "请先选择联系人（需已获取公钥）");
        return;
    }

    const arrayBuf = await file.arrayBuffer();
    const fileBytes = new Uint8Array(arrayBuf);
    const peerKey = state.peerKeys.get(state.activePeer);
    const mimeType = file.type || "application/octet-stream";

    cryptoLog("encrypt", `开始加密文件: ${file.name} (${formatSize(file.size)})`);

    try {
        if (file.size <= SMALL_FILE_LIMIT) {
            const encrypted = await Crypto.encryptFileData(fileBytes, peerKey);
            const msg = Protocol.makeFileTransferMessage(
                state.userId, state.activePeer, encrypted,
                file.name, file.size, mimeType,
            );
            state.ws.send(msg);
            cryptoLog("send", `文件已发送: ${file.name}`);
        } else {
            const transferId = crypto.randomUUID();
            const totalChunks = Math.ceil(fileBytes.length / CHUNK_SIZE);
            for (let i = 0; i < totalChunks; i++) {
                const chunk = fileBytes.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
                const encrypted = await Crypto.encryptFileData(chunk, peerKey);
                const msg = Protocol.makeFileChunkMessage(
                    state.userId, state.activePeer, encrypted,
                    transferId, i, totalChunks,
                    file.name, file.size, mimeType,
                );
                state.ws.send(msg);
                cryptoLog("send", `已发送块 ${i + 1}/${totalChunks}`);
            }
        }
        addFileMessage(state.activePeer, "sent", file.name, file.size, mimeType, fileBytes);
    } catch (err) {
        cryptoLog("error", `文件加密/发送失败: ${err.message}`);
    }
}

// ── 文件接收 ───────────────────────────────────────────────

async function handleFileTransfer(msg) {
    const payload = msg.payload;
    cryptoLog("recv", `收到来自 ${msg.sender_id} 的文件: ${payload.filename}`);
    try {
        const fileBytes = await Crypto.decryptFileData(payload, state.keyPair.privateKey);
        cryptoLog("decrypt", `文件解密成功: ${formatSize(fileBytes.length)}`);
        addFileMessage(
            msg.sender_id, "received",
            payload.filename, payload.filesize, payload.mime_type, fileBytes,
        );
    } catch (err) {
        cryptoLog("error", `文件解密失败: ${err.message}`);
    }
}

async function handleFileChunk(msg) {
    const p = msg.payload;
    const tid = p.transfer_id;

    try {
        const chunkBytes = await Crypto.decryptFileData(p, state.keyPair.privateKey);

        if (!state.chunkBuffers.has(tid)) {
            state.chunkBuffers.set(tid, {
                chunks: new Map(),
                total: p.total_chunks,
                filename: p.filename,
                filesize: p.filesize,
                mimeType: p.mime_type,
                senderId: msg.sender_id,
            });
            cryptoLog("recv", `开始接收分块文件: ${p.filename} (${p.total_chunks} 块)`);
        }
        const buf = state.chunkBuffers.get(tid);
        buf.chunks.set(p.chunk_index, chunkBytes);
        cryptoLog("recv", `收到块 ${p.chunk_index + 1}/${p.total_chunks}`);

        if (buf.chunks.size === buf.total) {
            let totalLen = 0;
            for (const c of buf.chunks.values()) totalLen += c.length;
            const assembled = new Uint8Array(totalLen);
            let offset = 0;
            for (let i = 0; i < buf.total; i++) {
                const c = buf.chunks.get(i);
                assembled.set(c, offset);
                offset += c.length;
            }
            cryptoLog("decrypt", `文件拼装完成: ${buf.filename} (${formatSize(assembled.length)})`);
            addFileMessage(
                buf.senderId, "received",
                buf.filename, buf.filesize, buf.mimeType, assembled,
            );
            state.chunkBuffers.delete(tid);
        }
    } catch (err) {
        cryptoLog("error", `文件块解密失败: ${err.message}`);
    }
}

// ── 联系人 UI ────────────────────────────────────────────

function renderContacts(users) {
    dom.contactsList.innerHTML = "";

    const uids = Object.keys(users).filter((u) => u !== state.userId);
    if (uids.length === 0) {
        dom.contactsList.innerHTML =
            `<div class="empty-state" style="height:auto; padding:20px 0;">
                <span style="font-size:12px;">尚无在线联系人</span>
            </div>`;
        return;
    }

    for (const uid of uids) {
        const item = document.createElement("div");
        item.className = "contact-item" + (uid === state.activePeer ? " active" : "");
        const fp = state.peerFingerprints.get(uid) || "...";
        const initial = uid.charAt(0).toUpperCase();
        item.innerHTML = `
            <div class="online-dot"></div>
            <div class="contact-avatar">${initial}</div>
            <div class="contact-info">
                <div class="contact-name">${escapeHtml(uid)}</div>
                <div class="contact-fingerprint">${fp}</div>
            </div>`;

        item.addEventListener("click", () => selectPeer(uid));
        dom.contactsList.appendChild(item);
    }
}

function selectPeer(uid) {
    state.activePeer = uid;

    // 更新联系人高亮
    dom.contactsList.querySelectorAll(".contact-item").forEach((el) => {
        el.classList.remove("active");
    });
    const items = dom.contactsList.querySelectorAll(".contact-item");
    items.forEach((el) => {
        if (el.querySelector(".contact-name")?.textContent === uid) {
            el.classList.add("active");
        }
    });

    // 更新聊天头部
    const fp = state.peerFingerprints.get(uid) || "";
    dom.chatHeader.textContent = `${uid}` + (fp ? ` [${fp}]` : "");

    // 启用输入
    const hasPeerKey = state.peerKeys.has(uid);
    dom.msgInput.disabled = !hasPeerKey;
    dom.btnSend.disabled = !hasPeerKey;

    if (!hasPeerKey) {
        cryptoLog("warn", `尚未获取 ${uid} 的公钥，无法发送加密消息`);
        // 主动请求公钥
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            const pkMsg = Protocol.makePublicKeyMessage(state.userId, uid, state.publicKeyPem);
            state.ws.send(pkMsg);
            cryptoLog("send", `已向 ${uid} 发送本地公钥`);
        }
    }

    // 渲染聊天历史
    renderChatHistory(uid);
}

// ── 聊天消息 UI ──────────────────────────────────────────

function addChatMessage(peerId, type, text) {
    if (!state.chatHistory.has(peerId)) {
        state.chatHistory.set(peerId, []);
    }
    const entry = { type, text, time: new Date().toLocaleTimeString() };
    state.chatHistory.get(peerId).push(entry);

    // 如果当前正在查看此对话，则更新 UI
    if (peerId === state.activePeer) {
        appendMessageToUI(entry);
    }
}

function addFileMessage(peerId, type, filename, filesize, mimeType, fileBytes) {
    if (!state.chatHistory.has(peerId)) {
        state.chatHistory.set(peerId, []);
    }
    const entry = {
        type, time: new Date().toLocaleTimeString(),
        isFile: true, filename, filesize, mimeType, fileBytes,
    };
    state.chatHistory.get(peerId).push(entry);
    if (peerId === state.activePeer) {
        appendFileToUI(entry);
    }
}

function renderChatHistory(peerId) {
    dom.chatMessages.innerHTML = "";
    const history = state.chatHistory.get(peerId) || [];

    if (history.length === 0) {
        dom.chatMessages.innerHTML = `
            <div class="empty-state">
                <div class="icon">🔐</div>
                <div>与 ${escapeHtml(peerId)} 的加密对话</div>
                <div style="font-size:12px;">消息将使用端到端加密传输</div>
            </div>`;
        return;
    }

    for (const entry of history) {
        if (entry.isFile) {
            appendFileToUI(entry);
        } else {
            appendMessageToUI(entry);
        }
    }
}

function appendMessageToUI(entry) {
    // 清除空状态提示
    const emptyState = dom.chatMessages.querySelector(".empty-state");
    if (emptyState) emptyState.remove();

    const div = document.createElement("div");
    div.className = `message ${entry.type}`;
    div.innerHTML = `${escapeHtml(entry.text)}<div class="msg-meta">${entry.time}</div>`;
    dom.chatMessages.appendChild(div);
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
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
        html += `<img src="${url}" class="chat-image">`;
    }

    html += `<div class="msg-meta">${entry.time}</div>`;
    div.innerHTML = html;

    // 保存按钮
    const saveBtn = document.createElement("a");
    saveBtn.textContent = "💾 保存";
    saveBtn.className = "file-save-link";
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

// ── 工具函数 ─────────────────────────────────────────────

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ── 远程部署自动检测 WebSocket 地址 ─────────────────────

(function autoDetectServerUrl() {
    const h = location.hostname;
    if (h && h !== "127.0.0.1" && h !== "localhost") {
        const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
        dom.serverUrl.value = `${wsProto}//${location.host}/ws`;
    }
})();

// ── 页面卸载时断开连接 ───────────────────────────────────

window.addEventListener("beforeunload", () => {
    if (state.ws) state.ws.close();
});
