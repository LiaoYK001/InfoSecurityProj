/**
 * 消息协议模块 — 对应桌面端 chat_protocol.py
 *
 * 负责构造和解析 WebSocket JSON 消息。
 * 所有消息均遵循统一信封格式：
 *   { type, sender_id, receiver_id, timestamp, payload }
 */

// ── 消息类型常量 ──────────────────────────────────────────
export const MSG_REGISTER     = "register";
export const MSG_PUBLIC_KEY   = "public_key";
export const MSG_CHAT_MESSAGE = "chat_message";
export const MSG_ACK          = "ack";
export const MSG_ERROR        = "error";
export const MSG_HEARTBEAT    = "heartbeat";
export const MSG_USER_LIST    = "user_list";
export const MSG_FILE_TRANSFER = "file_transfer";
export const MSG_FILE_CHUNK    = "file_chunk";

/** 需要 receiver_id 的消息类型 */
const REQUIRES_RECEIVER = new Set([
    MSG_PUBLIC_KEY,
    MSG_CHAT_MESSAGE,
    MSG_ACK,
    MSG_FILE_TRANSFER,
    MSG_FILE_CHUNK,
]);

// ── 内部工具 ──────────────────────────────────────────────

/** 返回当前 UTC 时间的 ISO 8601 字符串 */
function utcTimestamp() {
    return new Date().toISOString();
}

/**
 * 构建统一消息信封
 * @param {string} type
 * @param {string} senderId
 * @param {string} receiverId
 * @param {object} payload
 * @returns {string} JSON 字符串
 */
function buildEnvelope(type, senderId, receiverId, payload) {
    return JSON.stringify({
        type,
        sender_id: senderId,
        receiver_id: receiverId,
        timestamp: utcTimestamp(),
        payload,
    });
}

// ── 消息构造函数 ──────────────────────────────────────────

export function makeRegisterMessage(senderId, publicKeyPem) {
    return buildEnvelope(MSG_REGISTER, senderId, "", {
        public_key: publicKeyPem,
    });
}

export function makePublicKeyMessage(senderId, receiverId, publicKeyPem) {
    return buildEnvelope(MSG_PUBLIC_KEY, senderId, receiverId, {
        public_key: publicKeyPem,
    });
}

export function makeChatMessage(senderId, receiverId, payload) {
    return buildEnvelope(MSG_CHAT_MESSAGE, senderId, receiverId, payload);
}

export function makeAckMessage(senderId, receiverId, ackFor) {
    return buildEnvelope(MSG_ACK, senderId, receiverId, {
        ack_for: ackFor,
    });
}

export function makeErrorMessage(message, senderId = "server") {
    return buildEnvelope(MSG_ERROR, senderId, "", {
        message,
    });
}

export function makeHeartbeatMessage(senderId) {
    return buildEnvelope(MSG_HEARTBEAT, senderId, "", {});
}

export function makeUserListMessage(users) {
    return buildEnvelope(MSG_USER_LIST, "server", "", {
        users,
    });
}

export function makeFileTransferMessage(
    senderId, receiverId, encrypted, filename, filesize, mimeType,
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
    senderId, receiverId, encrypted,
    transferId, chunkIndex, totalChunks,
    filename, filesize, mimeType,
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

// ── 消息解析 ──────────────────────────────────────────────

/**
 * 解析 JSON 消息字符串
 * @param {string} raw
 * @returns {object} 解析后的消息对象
 * @throws {Error} 如果消息格式无效
 */
export function parseMessage(raw) {
    let msg;
    try {
        msg = JSON.parse(raw);
    } catch {
        throw new Error("无效 JSON 消息");
    }

    const required = ["type", "sender_id", "timestamp", "payload"];
    for (const key of required) {
        if (!(key in msg)) {
            throw new Error(`缺少必要字段: ${key}`);
        }
    }

    if (REQUIRES_RECEIVER.has(msg.type) && !msg.receiver_id) {
        throw new Error(`消息类型 ${msg.type} 需要 receiver_id`);
    }

    return msg;
}
