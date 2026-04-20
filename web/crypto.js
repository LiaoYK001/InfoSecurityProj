/**
 * Web Crypto API 加密模块 — 对应桌面端 aes_core.py + rsa_core.py + message_crypto.py
 *
 * 加密参数与桌面端完全一致：
 *   - RSA-2048 OAEP SHA-256 (hash + MGF1 均为 SHA-256)
 *   - AES-256-GCM, 12-byte nonce, 128-bit auth tag
 *   - 标准 Base64 编码
 *   - 公钥格式: SPKI (SubjectPublicKeyInfo) PEM
 */

// ── Base64 工具 ──────────────────────────────────────────

/** ArrayBuffer / Uint8Array → 标准 Base64 字符串 */
export function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

/** 标准 Base64 字符串 → Uint8Array */
export function base64ToArrayBuffer(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
}

// ── PEM 工具 ─────────────────────────────────────────────

/**
 * PEM 字符串 → ArrayBuffer (DER)
 * 支持 "-----BEGIN PUBLIC KEY-----" 和 "-----BEGIN PRIVATE KEY-----"
 */
export function pemToArrayBuffer(pem) {
    const lines = pem.split("\n").filter(
        (l) => !l.startsWith("-----") && l.trim().length > 0
    );
    const b64 = lines.join("");
    return base64ToArrayBuffer(b64);
}

/** ArrayBuffer (DER) → PEM 公钥字符串 */
export function arrayBufferToPublicKeyPem(buffer) {
    const b64 = arrayBufferToBase64(buffer);
    const lines = [];
    for (let i = 0; i < b64.length; i += 64) {
        lines.push(b64.substring(i, i + 64));
    }
    return `-----BEGIN PUBLIC KEY-----\n${lines.join("\n")}\n-----END PUBLIC KEY-----`;
}

// ── RSA 密钥操作 ─────────────────────────────────────────

/** RSA 算法参数（用于 generateKey / importKey） */
const RSA_ALGO = {
    name: "RSA-OAEP",
    modulusLength: 2048,
    publicExponent: new Uint8Array([0x01, 0x00, 0x01]), // 65537
    hash: "SHA-256",
};

/**
 * 生成 RSA-2048 密钥对
 * @returns {Promise<CryptoKeyPair>} { publicKey, privateKey }
 */
export async function generateRSAKeyPair() {
    return await crypto.subtle.generateKey(
        RSA_ALGO,
        true, // extractable
        ["encrypt", "decrypt", "wrapKey", "unwrapKey"]
    );
}

/**
 * 导出公钥为 PEM 格式字符串
 * @param {CryptoKey} publicKey
 * @returns {Promise<string>} PEM 字符串
 */
export async function exportPublicKeyPEM(publicKey) {
    const spki = await crypto.subtle.exportKey("spki", publicKey);
    return arrayBufferToPublicKeyPem(spki);
}

/**
 * 从 PEM 字符串导入对端 RSA 公钥
 * @param {string} pem
 * @returns {Promise<CryptoKey>}
 */
export async function importPublicKeyFromPEM(pem) {
    const der = pemToArrayBuffer(pem);
    return await crypto.subtle.importKey(
        "spki",
        der,
        { name: "RSA-OAEP", hash: "SHA-256" },
        true, // extractable (用于计算指纹)
        ["encrypt", "wrapKey"]
    );
}

/**
 * 计算公钥的 SHA-256 指纹（前 16 位 hex）
 * @param {CryptoKey} publicKey
 * @returns {Promise<string>} 16 个十六进制字符
 */
export async function getPublicKeyFingerprint(publicKey) {
    const spki = await crypto.subtle.exportKey("spki", publicKey);
    const hash = await crypto.subtle.digest("SHA-256", spki);
    const hashArray = new Uint8Array(hash);
    let hex = "";
    for (let i = 0; i < hashArray.length; i++) {
        hex += hashArray[i].toString(16).padStart(2, "0");
    }
    return hex.substring(0, 16);
}

// ── AES-GCM 操作 ────────────────────────────────────────

/**
 * 生成随机 AES-256 密钥（原始 32 字节）
 * @returns {Uint8Array} 32 字节密钥
 */
export function generateAESKey() {
    return crypto.getRandomValues(new Uint8Array(32));
}

/**
 * AES-GCM 加密
 * @param {string} plaintext UTF-8 明文
 * @param {Uint8Array} keyBytes 32 字节 AES 密钥
 * @returns {Promise<{nonce: string, ciphertext: string}>} Base64 编码的结果
 */
export async function aesEncrypt(plaintext, keyBytes) {
    const key = await crypto.subtle.importKey(
        "raw",
        keyBytes,
        { name: "AES-GCM" },
        false,
        ["encrypt"]
    );
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(plaintext);
    // Web Crypto AES-GCM encrypt 输出 = ciphertext + 16-byte auth tag
    const ciphertextWithTag = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv: nonce, tagLength: 128 },
        key,
        encoded
    );
    return {
        nonce: arrayBufferToBase64(nonce),
        ciphertext: arrayBufferToBase64(ciphertextWithTag),
    };
}

/**
 * AES-GCM 解密
 * @param {string} nonceB64
 * @param {string} ciphertextB64 密文 + auth tag
 * @param {Uint8Array} keyBytes 32 字节 AES 密钥
 * @returns {Promise<string>} UTF-8 明文
 */
export async function aesDecrypt(nonceB64, ciphertextB64, keyBytes) {
    const key = await crypto.subtle.importKey(
        "raw",
        keyBytes,
        { name: "AES-GCM" },
        false,
        ["decrypt"]
    );
    const nonce = base64ToArrayBuffer(nonceB64);
    const ciphertextWithTag = base64ToArrayBuffer(ciphertextB64);
    const decrypted = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: nonce, tagLength: 128 },
        key,
        ciphertextWithTag
    );
    return new TextDecoder().decode(decrypted);
}

// ── RSA-OAEP 包裹 AES 密钥 ──────────────────────────────

/**
 * 用对方 RSA 公钥加密（包裹）AES 会话密钥
 * @param {Uint8Array} sessionKey 32 字节 AES 密钥
 * @param {CryptoKey} peerPublicKey
 * @returns {Promise<Uint8Array>} RSA 密文
 */
export async function rsaWrapKey(sessionKey, peerPublicKey) {
    const encrypted = await crypto.subtle.encrypt(
        { name: "RSA-OAEP" },
        peerPublicKey,
        sessionKey
    );
    return new Uint8Array(encrypted);
}

/**
 * 用本地 RSA 私钥解密（解包）AES 会话密钥
 * @param {Uint8Array} wrappedKey RSA 密文
 * @param {CryptoKey} privateKey
 * @returns {Promise<Uint8Array>} 32 字节 AES 密钥
 */
export async function rsaUnwrapKey(wrappedKey, privateKey) {
    const decrypted = await crypto.subtle.decrypt(
        { name: "RSA-OAEP" },
        privateKey,
        wrappedKey
    );
    return new Uint8Array(decrypted);
}

// ── 混合加密 / 解密（对应 message_crypto.py）────────────

/**
 * 混合加密：AES-GCM 加密消息 + RSA-OAEP 包裹会话密钥
 * @param {string} plaintext
 * @param {CryptoKey} peerPublicKey 对方 RSA 公钥
 * @param {CryptoKey|null} localPublicKey 本地公钥（用于 debug 指纹，可选）
 * @returns {Promise<object>} { wrapped_key, nonce, ciphertext, debug }
 */
export async function encryptMessage(plaintext, peerPublicKey, localPublicKey = null) {
    // 1. 生成随机 AES-256 会话密钥
    const sessionKey = generateAESKey();

    // 2. AES-GCM 加密明文
    const aesResult = await aesEncrypt(plaintext, sessionKey);

    // 3. RSA-OAEP 包裹会话密钥
    const wrappedKeyBytes = await rsaWrapKey(sessionKey, peerPublicKey);
    const wrappedKeyB64 = arrayBufferToBase64(wrappedKeyBytes);

    // 4. 构建 debug 信息
    const debug = {
        plaintext_length: plaintext.length,
        ciphertext_length: aesResult.ciphertext.length,
        wrapped_key_length: wrappedKeyB64.length,
        nonce_length: aesResult.nonce.length,
        session_key_bits: 256,
        peer_key_fingerprint: await getPublicKeyFingerprint(peerPublicKey),
    };
    if (localPublicKey) {
        debug.sender_key_fingerprint = await getPublicKeyFingerprint(localPublicKey);
    }

    return {
        wrapped_key: wrappedKeyB64,
        nonce: aesResult.nonce,
        ciphertext: aesResult.ciphertext,
        debug,
    };
}

/**
 * 混合解密：RSA-OAEP 解包会话密钥 + AES-GCM 解密消息
 * @param {object} payload { wrapped_key, nonce, ciphertext }
 * @param {CryptoKey} localPrivateKey 本地 RSA 私钥
 * @returns {Promise<object>} { plaintext, debug }
 */
export async function decryptMessage(payload, localPrivateKey) {
    const { wrapped_key, nonce, ciphertext } = payload;

    // 1. RSA-OAEP 解包会话密钥
    const wrappedKeyBytes = base64ToArrayBuffer(wrapped_key);
    const sessionKey = await rsaUnwrapKey(wrappedKeyBytes, localPrivateKey);

    // 2. AES-GCM 解密
    const plaintext = await aesDecrypt(nonce, ciphertext, sessionKey);

    return {
        plaintext,
        debug: {
            plaintext_length: plaintext.length,
            ciphertext_length: ciphertext.length,
            wrapped_key_length: wrapped_key.length,
            nonce_length: nonce.length,
        },
    };
}

// ── AES-GCM 字节加密 / 解密（文件传输用）────────────────

/**
 * AES-GCM 加密原始字节
 * @param {Uint8Array} data
 * @param {Uint8Array} keyBytes 32 字节 AES 密钥
 * @returns {Promise<{nonce: string, ciphertext: string}>} Base64 编码结果
 */
export async function aesEncryptBytes(data, keyBytes) {
    const key = await crypto.subtle.importKey(
        "raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt"]
    );
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv: nonce, tagLength: 128 }, key, data
    );
    return {
        nonce: arrayBufferToBase64(nonce),
        ciphertext: arrayBufferToBase64(ct),
    };
}

/**
 * AES-GCM 解密原始字节
 * @param {string} nonceB64
 * @param {string} ciphertextB64
 * @param {Uint8Array} keyBytes
 * @returns {Promise<Uint8Array>}
 */
export async function aesDecryptBytes(nonceB64, ciphertextB64, keyBytes) {
    const key = await crypto.subtle.importKey(
        "raw", keyBytes, { name: "AES-GCM" }, false, ["decrypt"]
    );
    const nonce = base64ToArrayBuffer(nonceB64);
    const ct = base64ToArrayBuffer(ciphertextB64);
    const plain = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: nonce, tagLength: 128 }, key, ct
    );
    return new Uint8Array(plain);
}

// ── 混合加密 / 解密文件字节 ─────────────────────────────

/**
 * 混合加密文件字节：AES-GCM 加密 + RSA-OAEP 包裹密钥
 * @param {Uint8Array} fileBytes
 * @param {CryptoKey} peerPublicKey
 * @returns {Promise<{wrapped_key: string, nonce: string, ciphertext: string}>}
 */
export async function encryptFileData(fileBytes, peerPublicKey) {
    const sessionKey = generateAESKey();
    const aesResult = await aesEncryptBytes(fileBytes, sessionKey);
    const wrappedKeyBytes = await rsaWrapKey(sessionKey, peerPublicKey);
    return {
        wrapped_key: arrayBufferToBase64(wrappedKeyBytes),
        nonce: aesResult.nonce,
        ciphertext: aesResult.ciphertext,
    };
}

/**
 * 混合解密文件字节
 * @param {object} payload { wrapped_key, nonce, ciphertext }
 * @param {CryptoKey} localPrivateKey
 * @returns {Promise<Uint8Array>}
 */
export async function decryptFileData(payload, localPrivateKey) {
    const wrappedKeyBytes = base64ToArrayBuffer(payload.wrapped_key);
    const sessionKey = await rsaUnwrapKey(wrappedKeyBytes, localPrivateKey);
    return aesDecryptBytes(payload.nonce, payload.ciphertext, sessionKey);
}
