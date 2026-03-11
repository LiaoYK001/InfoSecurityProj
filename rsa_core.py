from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


DEFAULT_KEY_SIZE = 1024
SUPPORTED_KEY_SIZES = (1024, 2048, 3072)
FILE_MAGIC = b"RSAFILE1"
METADATA_LENGTH_BYTES = 4
OAEP_HASH = hashes.SHA256()


def generate_rsa_key_pair(key_size: int = DEFAULT_KEY_SIZE) -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
	private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
	return private_key, private_key.public_key()


def get_oaep_padding() -> padding.OAEP:
	return padding.OAEP(mgf=padding.MGF1(algorithm=OAEP_HASH), algorithm=OAEP_HASH, label=None)


def max_encrypt_block_size(public_key: rsa.RSAPublicKey) -> int:
	key_bytes = public_key.key_size // 8
	return key_bytes - 2 * OAEP_HASH.digest_size - 2


def encrypt_bytes(data: bytes, public_key: rsa.RSAPublicKey) -> bytes:
	block_size = max_encrypt_block_size(public_key)
	encrypted_blocks = []
	oaep_padding = get_oaep_padding()
	for start in range(0, len(data), block_size):
		chunk = data[start : start + block_size]
		encrypted_blocks.append(public_key.encrypt(chunk, oaep_padding))
	return b"".join(encrypted_blocks)


def decrypt_bytes(ciphertext: bytes, private_key: rsa.RSAPrivateKey) -> bytes:
	block_size = private_key.key_size // 8
	if len(ciphertext) % block_size != 0:
		raise ValueError("密文长度与当前私钥不匹配，无法按 RSA 分块解密。")

	decrypted_blocks = []
	oaep_padding = get_oaep_padding()
	for start in range(0, len(ciphertext), block_size):
		chunk = ciphertext[start : start + block_size]
		decrypted_blocks.append(private_key.decrypt(chunk, oaep_padding))
	return b"".join(decrypted_blocks)


def serialize_private_key(private_key: rsa.RSAPrivateKey) -> bytes:
	return private_key.private_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PrivateFormat.PKCS8,
		encryption_algorithm=serialization.NoEncryption(),
	)


def serialize_public_key(public_key: rsa.RSAPublicKey) -> bytes:
	return public_key.public_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PublicFormat.SubjectPublicKeyInfo,
	)


def load_private_key_from_file(file_path: str) -> rsa.RSAPrivateKey:
	with open(file_path, "rb") as file:
		return cast(rsa.RSAPrivateKey, serialization.load_pem_private_key(file.read(), password=None))


def load_public_key_from_file(file_path: str) -> rsa.RSAPublicKey:
	with open(file_path, "rb") as file:
		return cast(rsa.RSAPublicKey, serialization.load_pem_public_key(file.read()))


def load_public_key_from_pem_text(public_key_pem: str) -> rsa.RSAPublicKey:
	return cast(rsa.RSAPublicKey, serialization.load_pem_public_key(public_key_pem.encode("utf-8")))


def encrypt_file(input_path: str, output_path: str, public_key: rsa.RSAPublicKey) -> dict[str, str | int]:
	source = Path(input_path)
	metadata = {
		"version": 1,
		"original_name": source.name,
		"original_suffix": source.suffix,
		"original_size": source.stat().st_size,
	}
	metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
	if len(metadata_bytes) >= 2 ** (METADATA_LENGTH_BYTES * 8):
		raise ValueError("文件元数据过长，无法写入加密文件头。")

	block_size = max_encrypt_block_size(public_key)
	oaep_padding = get_oaep_padding()

	with open(input_path, "rb") as source_file, open(output_path, "wb") as target_file:
		target_file.write(FILE_MAGIC)
		target_file.write(len(metadata_bytes).to_bytes(METADATA_LENGTH_BYTES, "big"))
		target_file.write(metadata_bytes)

		while True:
			chunk = source_file.read(block_size)
			if not chunk:
				break
			target_file.write(public_key.encrypt(chunk, oaep_padding))

	return metadata


def decrypt_file(input_path: str, output_path: str, private_key: rsa.RSAPrivateKey) -> dict[str, str | int]:
	encrypted_block_size = private_key.key_size // 8
	oaep_padding = get_oaep_padding()

	with open(input_path, "rb") as source_file:
		if source_file.read(len(FILE_MAGIC)) != FILE_MAGIC:
			raise ValueError("文件头无效，这不是本程序生成的 RSA 加密文件。")

		metadata_length = int.from_bytes(source_file.read(METADATA_LENGTH_BYTES), "big")
		metadata_bytes = source_file.read(metadata_length)
		metadata = json.loads(metadata_bytes.decode("utf-8"))

		with open(output_path, "wb") as target_file:
			while True:
				chunk = source_file.read(encrypted_block_size)
				if not chunk:
					break
				if len(chunk) != encrypted_block_size:
					raise ValueError("密文块长度异常，文件可能已损坏或密钥不匹配。")
				target_file.write(private_key.decrypt(chunk, oaep_padding))

	return metadata


class RSAKeyManager:
	def __init__(self) -> None:
		self.private_key: rsa.RSAPrivateKey | None = None
		self.public_key: rsa.RSAPublicKey | None = None
		self.peer_public_key: rsa.RSAPublicKey | None = None

	def generate_keys(self, key_size: int = DEFAULT_KEY_SIZE) -> None:
		self.private_key, self.public_key = generate_rsa_key_pair(key_size)

	def has_public_key(self) -> bool:
		return self.public_key is not None

	def has_private_key(self) -> bool:
		return self.private_key is not None

	def has_peer_public_key(self) -> bool:
		return self.peer_public_key is not None

	def require_public_key(self) -> rsa.RSAPublicKey:
		if not self.public_key:
			raise ValueError("当前未加载本地公钥。")
		return self.public_key

	def require_private_key(self) -> rsa.RSAPrivateKey:
		if not self.private_key:
			raise ValueError("当前未加载本地私钥。")
		return self.private_key

	def require_peer_public_key(self) -> rsa.RSAPublicKey:
		if not self.peer_public_key:
			raise ValueError("当前未导入对方公钥。")
		return self.peer_public_key

	def get_key_size(self) -> int | None:
		if self.public_key:
			return self.public_key.key_size
		if self.private_key:
			return self.private_key.key_size
		return None

	def get_key_summary(self) -> str:
		public_key = self.require_public_key()
		private_key = self.require_private_key()
		key_size = public_key.key_size
		encrypt_block_size = max_encrypt_block_size(public_key)
		decrypt_block_size = private_key.key_size // 8
		peer_status = "已导入" if self.peer_public_key else "未导入"
		return (
			f"当前 RSA 密钥长度: {key_size} bit\n"
			f"公钥加密最大明文块长度: {encrypt_block_size} 字节\n"
			f"私钥解密密文块长度: {decrypt_block_size} 字节\n"
			f"对方公钥状态: {peer_status}\n\n"
			"本程序默认使用 RSA-OAEP(SHA-256) 填充。\n"
			"字符串会先按 UTF-8 编码，再做分块加密。\n"
			"文件以字节流方式分块处理，因此同样适用于 .txt、.md、图片、音频、压缩包和可执行文件等二进制内容。"
		)

	def save_public_key(self, file_path: str) -> None:
		with open(file_path, "wb") as file:
			file.write(serialize_public_key(self.require_public_key()))

	def save_private_key(self, file_path: str) -> None:
		with open(file_path, "wb") as file:
			file.write(serialize_private_key(self.require_private_key()))

	def load_public_key(self, file_path: str) -> None:
		self.public_key = load_public_key_from_file(file_path)

	def load_private_key(self, file_path: str) -> None:
		self.private_key = load_private_key_from_file(file_path)
		self.public_key = self.private_key.public_key()

	def export_public_key_bytes(self) -> bytes:
		return serialize_public_key(self.require_public_key())

	def export_public_key_string(self) -> str:
		return self.export_public_key_bytes().decode("utf-8")

	def import_peer_public_key_from_file(self, file_path: str) -> None:
		self.peer_public_key = load_public_key_from_file(file_path)

	def import_peer_public_key_from_string(self, public_key_pem: str) -> None:
		self.peer_public_key = load_public_key_from_pem_text(public_key_pem)

	def clear_peer_public_key(self) -> None:
		self.peer_public_key = None

	def encrypt_text(self, plaintext: str, public_key: rsa.RSAPublicKey | None = None) -> bytes:
		if not plaintext:
			raise ValueError("请输入要加密的字符串。")
		target_public_key = public_key or self.require_public_key()
		return encrypt_bytes(plaintext.encode("utf-8"), target_public_key)

	def encrypt_text_to_base64(self, plaintext: str, public_key: rsa.RSAPublicKey | None = None) -> str:
		ciphertext = self.encrypt_text(plaintext, public_key=public_key)
		return base64.b64encode(ciphertext).decode("ascii")

	def decrypt_text(self, ciphertext: bytes) -> str:
		return decrypt_bytes(ciphertext, self.require_private_key()).decode("utf-8")

	def decrypt_text_from_base64(self, ciphertext_base64: str) -> str:
		if not ciphertext_base64.strip():
			raise ValueError("请输入 Base64 格式的密文。")
		ciphertext = base64.b64decode(ciphertext_base64)
		return self.decrypt_text(ciphertext)

	def encrypt_session_key_for_peer(self, session_key: bytes) -> bytes:
		if not session_key:
			raise ValueError("会话密钥不能为空。")
		return encrypt_bytes(session_key, self.require_peer_public_key())

	def encrypt_session_key_for_peer_base64(self, session_key: bytes) -> str:
		ciphertext = self.encrypt_session_key_for_peer(session_key)
		return base64.b64encode(ciphertext).decode("ascii")

	def decrypt_session_key_from_peer(self, encrypted_session_key: bytes) -> bytes:
		return decrypt_bytes(encrypted_session_key, self.require_private_key())

	def decrypt_session_key_from_peer_base64(self, encrypted_session_key_base64: str) -> bytes:
		if not encrypted_session_key_base64.strip():
			raise ValueError("会话密钥密文不能为空。")
		ciphertext = base64.b64decode(encrypted_session_key_base64)
		return self.decrypt_session_key_from_peer(ciphertext)


class RSAFileCipher:
	def __init__(self, key_manager: RSAKeyManager) -> None:
		self.key_manager = key_manager

	def encrypt_bytes_with_local_public_key(self, data: bytes) -> bytes:
		return encrypt_bytes(data, self.key_manager.require_public_key())

	def encrypt_bytes_with_peer_public_key(self, data: bytes) -> bytes:
		return encrypt_bytes(data, self.key_manager.require_peer_public_key())

	def decrypt_bytes_with_local_private_key(self, ciphertext: bytes) -> bytes:
		return decrypt_bytes(ciphertext, self.key_manager.require_private_key())

	def encrypt_file(self, input_path: str, output_path: str, use_peer_public_key: bool = False) -> dict[str, str | int]:
		public_key = self.key_manager.require_peer_public_key() if use_peer_public_key else self.key_manager.require_public_key()
		return encrypt_file(input_path, output_path, public_key)

	def decrypt_file(self, input_path: str, output_path: str) -> dict[str, str | int]:
		return decrypt_file(input_path, output_path, self.key_manager.require_private_key())


class RSAService:
	def __init__(self) -> None:
		self.key_manager = RSAKeyManager()
		self.file_cipher = RSAFileCipher(self.key_manager)

	def generate_keys(self, key_size: int = DEFAULT_KEY_SIZE) -> None:
		self.key_manager.generate_keys(key_size)

	def has_public_key(self) -> bool:
		return self.key_manager.has_public_key()

	def has_private_key(self) -> bool:
		return self.key_manager.has_private_key()

	def has_peer_public_key(self) -> bool:
		return self.key_manager.has_peer_public_key()

	def get_key_summary(self) -> str:
		return self.key_manager.get_key_summary()

	def save_public_key(self, file_path: str) -> None:
		self.key_manager.save_public_key(file_path)

	def save_private_key(self, file_path: str) -> None:
		self.key_manager.save_private_key(file_path)

	def load_public_key(self, file_path: str) -> None:
		self.key_manager.load_public_key(file_path)

	def load_private_key(self, file_path: str) -> None:
		self.key_manager.load_private_key(file_path)

	def export_public_key_string(self) -> str:
		return self.key_manager.export_public_key_string()

	def import_peer_public_key_from_string(self, public_key_pem: str) -> None:
		self.key_manager.import_peer_public_key_from_string(public_key_pem)

	def import_peer_public_key_from_file(self, file_path: str) -> None:
		self.key_manager.import_peer_public_key_from_file(file_path)

	def encrypt_text_to_base64(self, plaintext: str) -> str:
		return self.key_manager.encrypt_text_to_base64(plaintext)

	def decrypt_text_from_base64(self, ciphertext_base64: str) -> str:
		return self.key_manager.decrypt_text_from_base64(ciphertext_base64)

	def encrypt_file(self, input_path: str, output_path: str) -> dict[str, str | int]:
		return self.file_cipher.encrypt_file(input_path, output_path)

	def decrypt_file(self, input_path: str, output_path: str) -> dict[str, str | int]:
		return self.file_cipher.decrypt_file(input_path, output_path)

	def encrypt_session_key_for_peer_base64(self, session_key: bytes) -> str:
		return self.key_manager.encrypt_session_key_for_peer_base64(session_key)

	def decrypt_session_key_from_peer_base64(self, encrypted_session_key_base64: str) -> bytes:
		return self.key_manager.decrypt_session_key_from_peer_base64(encrypted_session_key_base64)
