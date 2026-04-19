"""RSA 非对称加密核心模块。

本模块提供 RSA 密钥对生成、OAEP 填充加解密、分块加密、密钥序列化/反序列化
以及公钥指纹计算等功能。在即时通讯系统中，RSA 用于安全传输一次性 AES 会话密钥，
是混合加密方案（RSA-OAEP + AES-GCM）的非对称加密部分。

主要组件：
    - 顶层函数：generate_rsa_key_pair, encrypt_bytes, decrypt_bytes 等
    - RSAKeyManager：密钥对管理类，供新版聊天系统使用
    - RSAFileCipher：文件级加解密类
    - RSAService：为旧版 GUI (InfoSecurWork_GUI.py) 提供的门面类
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import cast

# 导入 cryptography 库提供密码学相关的算法实现
# hashes 用于计算哈希值，serialization 用于密钥的序列化（保存为文件格式）
from cryptography.hazmat.primitives import hashes, serialization
# padding 用于填充（如 OAEP），rsa 用于生成和使用 RSA 密钥
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# ----- 常量定义 -----

# 默认的 RSA 密钥长度（位），1024 位由于安全性问题通常建议只用于学习，生产环境建议至少 2048 位
DEFAULT_KEY_SIZE = 1024
# 支持的密钥长度列表
SUPPORTED_KEY_SIZES = (1024, 2048, 3072)
# 用于标识本程序加密出来的文件的一个特殊的头部标记 (Magic Number)
FILE_MAGIC = b"RSAFILE1"
# 用于记录元数据（Metadata，如原始文件名、大小等）长度所占用的字节数
METADATA_LENGTH_BYTES = 4
# 加解密填充阶段使用的哈希算法（SHA256）
OAEP_HASH = hashes.SHA256()


def get_public_key_fingerprint(public_key: rsa.RSAPublicKey) -> str:
	"""
	计算公钥的 SHA-256 指纹（取前 16 个十六进制字符）。
	用于在界面上简短地标识一把公钥，方便用户确认对方身份。
	"""
	pub_bytes = public_key.public_bytes(
		encoding=serialization.Encoding.DER,
		format=serialization.PublicFormat.SubjectPublicKeyInfo,
	)
	digest = hashes.Hash(hashes.SHA256())
	digest.update(pub_bytes)
	return digest.finalize().hex()[:16]


def generate_rsa_key_pair(key_size: int = DEFAULT_KEY_SIZE) -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
	"""
	生成一对新的 RSA 密钥对（包含私钥和公钥）。
	:param key_size: 密钥长度，数值越大越安全，但速度越慢。
	:return: (私钥对象, 公钥对象) 的元组。
	"""
	# 生成 RSA 私钥。public_exponent 固定使用 65537（常见的安全值），key_size 为密钥长度
	private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
	# 通过私钥对象推导出对应的公钥对象，并一同返回
	return private_key, private_key.public_key()


def get_oaep_padding() -> padding.OAEP:
	"""
	获取 OAEP 填充方式。
	在 RSA 加密中，直接加密（教科书 RSA）是不安全的，加入填充（Padding）可以增加随机性。
	这里使用了 MGF1 和 SHA256 作为内部哈希算法，这是目前推荐的安全配置。
	"""
	return padding.OAEP(mgf=padding.MGF1(algorithm=OAEP_HASH), algorithm=OAEP_HASH, label=None)


def max_encrypt_block_size(public_key: rsa.RSAPublicKey) -> int:
	"""
	计算给定公钥单次加密能处理的“最大明文字节数”。
	由于 RSA 的数学特性，要加密的数据不能比密钥长度还长。
	公式解释：密钥字节数 - 2倍的哈希长度 - 2（OAEP 填充规则的固定消耗）
	"""
	key_bytes = public_key.key_size // 8
	return key_bytes - 2 * OAEP_HASH.digest_size - 2


def encrypt_bytes(data: bytes, public_key: rsa.RSAPublicKey) -> bytes:
	"""
	对任意字节数据进行 RSA 加密。
	由于长数据无法一次性加密，我们采用“分块加密”的方法。
	"""
	block_size = max_encrypt_block_size(public_key)
	encrypted_blocks = []
	oaep_padding = get_oaep_padding()
	# range(0, 长度, 步长) 实现分块循环
	for start in range(0, len(data), block_size):
		chunk = data[start : start + block_size] # 切片截取一段明文
		# public_key.encrypt 方法执行真正的加密操作
		encrypted_blocks.append(public_key.encrypt(chunk, oaep_padding))
	# 将所有加密好的块拼接成一个大的字节串并返回
	return b"".join(encrypted_blocks)


def decrypt_bytes(ciphertext: bytes, private_key: rsa.RSAPrivateKey) -> bytes:
	"""
	使用私钥对字节数据进行 RSA 解密。
	解密同样需要按“密文块”的大小进行分块还原。
	"""
	block_size = private_key.key_size // 8 # 密文块的大小恰好等于密钥的长度(字节)
	if len(ciphertext) % block_size != 0:
		raise ValueError("密文长度与当前私钥不匹配，无法按 RSA 分块解密。")

	decrypted_blocks = []
	oaep_padding = get_oaep_padding()
	for start in range(0, len(ciphertext), block_size):
		chunk = ciphertext[start : start + block_size]
		# private_key.decrypt 方法执行真正的解密操作
		decrypted_blocks.append(private_key.decrypt(chunk, oaep_padding))
	return b"".join(decrypted_blocks)


def serialize_private_key(private_key: rsa.RSAPrivateKey) -> bytes:
	"""
	序列化私钥（把内存里的私钥对象变成可以保存到文件里的文本/字节格式 PEM）。
	此处选用了 PKCS8 格式，且不设置额外密码(NoEncryption)。
	"""
	return private_key.private_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PrivateFormat.PKCS8,
		encryption_algorithm=serialization.NoEncryption(),
	)


def serialize_public_key(public_key: rsa.RSAPublicKey) -> bytes:
	"""
	序列化公钥（把公钥对象变成可保存的文本/字节格式 PEM）。
	使用 SubjectPublicKeyInfo 格式，这是最通用的公钥公开格式。
	"""
	return public_key.public_bytes(
		encoding=serialization.Encoding.PEM,
		format=serialization.PublicFormat.SubjectPublicKeyInfo,
	)


def load_private_key_from_file(file_path: str) -> rsa.RSAPrivateKey:
	"""从文件路径读取并还原私钥对象。"""
	with open(file_path, "rb") as file: # "rb" 表示以二进制只读模式打开
		return cast(rsa.RSAPrivateKey, serialization.load_pem_private_key(file.read(), password=None))


def load_public_key_from_file(file_path: str) -> rsa.RSAPublicKey:
	"""从文件路径读取并还原公钥对象。"""
	with open(file_path, "rb") as file:
		return cast(rsa.RSAPublicKey, serialization.load_pem_public_key(file.read()))


def load_public_key_from_pem_text(public_key_pem: str) -> rsa.RSAPublicKey:
	"""直接从 PEM 格式的纯字符串文本中还原公钥对象，方便像文字直接复制粘贴。"""
	return cast(rsa.RSAPublicKey, serialization.load_pem_public_key(public_key_pem.encode("utf-8")))


def encrypt_file(input_path: str, output_path: str, public_key: rsa.RSAPublicKey) -> dict[str, str | int]:
	"""
	加密整个文件：先将文件的名字、大小等元数据写在前面，然后把文件核心内容一块一块加密写进去。
	"""
	source = Path(input_path) # 把路径如 "C:/doc/test.txt" 转化为 Path 对象方便操作
	# 收集要加密的文件的元数据信息（原名即后缀等），以便解密时恢复它原本的名字
	metadata = {
		"version": 1,
		"original_name": source.name,
		"original_suffix": source.suffix,
		"original_size": source.stat().st_size,
	}
	# 将字典信息转成 JSON，再转成 UTF-8 字节串
	metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
	if len(metadata_bytes) >= 2 ** (METADATA_LENGTH_BYTES * 8):
		raise ValueError("文件元数据过长，无法写入加密文件头。")

	block_size = max_encrypt_block_size(public_key)
	oaep_padding = get_oaep_padding()

	# 同时打开原文件（用于读取）和新文件（用于写入）
	with open(input_path, "rb") as source_file, open(output_path, "wb") as target_file:
		# 写入特供的“安全标记”，别人一看就知道这是我们系统加密过的
		target_file.write(FILE_MAGIC)
		# 写入用固定字节长度表示的元数据大小（大端模式）
		target_file.write(len(metadata_bytes).to_bytes(METADATA_LENGTH_BYTES, "big"))
		# 把真实的元数据写进去
		target_file.write(metadata_bytes)

		# 重点来了：死循环不断读取原文件的内容（流式读取，防内存爆炸）
		while True:
			chunk = source_file.read(block_size) # 每次只抽一小勺水
			if not chunk: # 水抽干了，退出循环
				break
			# 把这一小勺水（字节块）用公钥加密，然后倒进新文件里
			target_file.write(public_key.encrypt(chunk, oaep_padding))

	return metadata


def decrypt_file(input_path: str, output_path: str, private_key: rsa.RSAPrivateKey) -> dict[str, str | int]:
	"""
	解密整个加密文件，逆向还原出原数据信息并将元数据一并丢回字典。
	"""
	encrypted_block_size = private_key.key_size // 8
	oaep_padding = get_oaep_padding()

	with open(input_path, "rb") as source_file:
		# 第一步：核实验明正身，标记对不对得上
		if source_file.read(len(FILE_MAGIC)) != FILE_MAGIC:
			raise ValueError("文件头无效，这不是本程序生成的 RSA 加密文件。")

		# 第二步：获取原信息的大小
		metadata_length = int.from_bytes(source_file.read(METADATA_LENGTH_BYTES), "big")
		# 提取并恢复我们的元数据（像原来的文件名等）
		metadata_bytes = source_file.read(metadata_length)
		metadata = json.loads(metadata_bytes.decode("utf-8"))

		# 第三步：读出接下来的纯货（之前加密好的密文数据），并且解密写入
		with open(output_path, "wb") as target_file:
			while True:
				chunk = source_file.read(encrypted_block_size)
				if not chunk:
					break
				if len(chunk) != encrypted_block_size:
					raise ValueError("密文块长度异常，文件可能已损坏或密钥不匹配。")
				# secret.decrypt，使用私钥还原被锁定的小字节块
				target_file.write(private_key.decrypt(chunk, oaep_padding))

	return metadata


class RSAKeyManager:
	"""
	密钥管理器：主要存储并管理当前正在使用的各种密钥。
	这就像一个保险柜，把你自己的私钥、公钥以及别人的公钥（peer_public_key）存放在其中，以方便调用。
	"""
	def __init__(self) -> None:
		self.private_key: rsa.RSAPrivateKey | None = None # 本地自己的私钥 (解密用)
		self.public_key: rsa.RSAPublicKey | None = None   # 本地自己的公钥 (给别人加密发给你用)
		self.peer_public_key: rsa.RSAPublicKey | None = None # 对方(好友)的公钥 (你用来给他加密消息用)

	def generate_keys(self, key_size: int = DEFAULT_KEY_SIZE) -> None:
		"""让上面写好的 generate_rsa_key_pair 跑起来，填满自己保险箱里的两个空位！"""
		self.private_key, self.public_key = generate_rsa_key_pair(key_size)

	def has_public_key(self) -> bool:
		"""是否有本地公钥？(布尔值返回：True/False)"""
		return self.public_key is not None

	def has_private_key(self) -> bool:
		"""是否有本地私钥？"""
		return self.private_key is not None

	def has_peer_public_key(self) -> bool:
		"""是否导入了对方朋友的公钥？"""
		return self.peer_public_key is not None

	def require_public_key(self) -> rsa.RSAPublicKey:
		"""获取公钥。如果没有就当场报错(抛出异常)。这是一种安全编程习惯。"""
		if not self.public_key:
			raise ValueError("当前未加载本地公钥。")
		return self.public_key

	def require_private_key(self) -> rsa.RSAPrivateKey:
		"""获取私钥。如果没有就报错。"""
		if not self.private_key:
			raise ValueError("当前未加载本地私钥。")
		return self.private_key

	def require_peer_public_key(self) -> rsa.RSAPublicKey:
		"""获取对方的公钥，没有则报错。"""
		if not self.peer_public_key:
			raise ValueError("当前未导入对方公钥。")
		return self.peer_public_key

	def get_key_size(self) -> int | None:
		"""自动侦测当前所用密钥的大小（长度）。"""
		if self.public_key:
			return self.public_key.key_size
		if self.private_key:
			return self.private_key.key_size
		return None

	def get_key_summary(self) -> str:
		"""返回目前所有密钥的通俗总结信息，用于展现在图形界面的右侧文本框里方便核查。"""
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
		"""掏出公钥并调用前面写的 serialize_public_key 保存进指定的文件位置"""
		with open(file_path, "wb") as file:
			file.write(serialize_public_key(self.require_public_key()))

	def save_private_key(self, file_path: str) -> None:
		"""掏出私钥并保存在本地磁盘（绝密保护好！）"""
		with open(file_path, "wb") as file:
			file.write(serialize_private_key(self.require_private_key()))

	def load_public_key(self, file_path: str) -> None:
		"""从硬盘将刚刚保存的公钥文件重新载入系统里使用"""
		self.public_key = load_public_key_from_file(file_path)

	def load_private_key(self, file_path: str) -> None:
		"""从硬盘载入私钥。同时！根据密码学特性，有了私钥我们直接就白送推导出了公钥！"""
		self.private_key = load_private_key_from_file(file_path)
		self.public_key = self.private_key.public_key()

	def export_public_key_bytes(self) -> bytes:
		"""以字节串形式打包公钥"""
		return serialize_public_key(self.require_public_key())

	def export_public_key_string(self) -> str:
		"""把上面的字节串强制转成可以阅读的 UTF-8 字符串"""
		return self.export_public_key_bytes().decode("utf-8")

	def import_peer_public_key_from_file(self, file_path: str) -> None:
		"""如果朋友给你发来一份公钥文件（.pem），你可以用这个方法去识别它"""
		self.peer_public_key = load_public_key_from_file(file_path)

	def import_peer_public_key_from_string(self, public_key_pem: str) -> None:
		"""如果朋友在微信直接复制了一串公钥文本，粘贴进这里直接读取"""
		self.peer_public_key = load_public_key_from_pem_text(public_key_pem)

	def clear_peer_public_key(self) -> None:
		"""干掉对方留存的公钥记录（比如和朋友吵架了不再联系...）"""
		self.peer_public_key = None

	def get_local_public_key_fingerprint(self) -> str:
		"""获取本地公钥的 SHA-256 短指纹，用于界面展示和身份确认。"""
		return get_public_key_fingerprint(self.require_public_key())

	def get_peer_public_key_fingerprint(self) -> str | None:
		"""获取对方公钥的指纹。如果尚未导入对方公钥则返回 None。"""
		if self.peer_public_key is None:
			return None
		return get_public_key_fingerprint(self.peer_public_key)

	def encrypt_text(self, plaintext: str, public_key: rsa.RSAPublicKey | None = None) -> bytes:
		"""
		加密短文本（比如文字消息）。
		如果没有特殊指定公钥，就会使用自己的本机的 public_key 加密。
		"""
		if not plaintext:
			raise ValueError("请输入要加密的字符串。")
		target_public_key = public_key or self.require_public_key()
		return encrypt_bytes(plaintext.encode("utf-8"), target_public_key)

	def encrypt_text_to_base64(self, plaintext: str, public_key: rsa.RSAPublicKey | None = None) -> str:
		"""
		将文本加密后的“乱码字节”进一步使用 Base64 包装成可以在网上正常显示的英文字母（形如：A1x/Z...）
		"""
		ciphertext = self.encrypt_text(plaintext, public_key=public_key)
		return base64.b64encode(ciphertext).decode("ascii")

	def decrypt_text(self, ciphertext: bytes) -> str:
		"""从之前说的 bytes (乱码) 形式利用私钥解密为中文等阅读文本"""
		return decrypt_bytes(ciphertext, self.require_private_key()).decode("utf-8")

	def decrypt_text_from_base64(self, ciphertext_base64: str) -> str:
		"""先把对方发给你的 Base64 包裹（A1x/Z）给脱下，然后才能丢给上面真正去执行解锁！"""
		if not ciphertext_base64.strip():
			raise ValueError("请输入 Base64 格式的密文。")
		ciphertext = base64.b64decode(ciphertext_base64)
		return self.decrypt_text(ciphertext)

	def encrypt_session_key_for_peer(self, session_key: bytes) -> bytes:
		"""进阶功能：如果你想将 AES (一种更快的对称加密) 的会话私钥锁起来发给朋友"""
		if not session_key:
			raise ValueError("会话密钥不能为空。")
		return encrypt_bytes(session_key, self.require_peer_public_key())

	def encrypt_session_key_for_peer_base64(self, session_key: bytes) -> str:
		"""加上 Base64 使得传输时不丢失数据乱码"""
		ciphertext = self.encrypt_session_key_for_peer(session_key)
		return base64.b64encode(ciphertext).decode("ascii")

	def decrypt_session_key_from_peer(self, encrypted_session_key: bytes) -> bytes:
		"""接受方提取朋友发给你的会话钥匙"""
		return decrypt_bytes(encrypted_session_key, self.require_private_key())

	def decrypt_session_key_from_peer_base64(self, encrypted_session_key_base64: str) -> bytes:
		"""解包 Base64 后并解开对应的钥匙"""
		if not encrypted_session_key_base64.strip():
			raise ValueError("会话密钥密文不能为空。")
		ciphertext = base64.b64decode(encrypted_session_key_base64)
		return self.decrypt_session_key_from_peer(ciphertext)


class RSAFileCipher:
	"""
	专门负责文件大文件加解密的帮手类。
	它从上面哪个 RSAKeyManager 拿钥匙（公钥借去加密，或者私钥拿去解密），然后使用最前面的加密大文件的函数帮你处理好。
	"""
	def __init__(self, key_manager: RSAKeyManager) -> None:
		self.key_manager = key_manager

	def encrypt_bytes_with_local_public_key(self, data: bytes) -> bytes:
		"""用自己的公钥加锁"""
		return encrypt_bytes(data, self.key_manager.require_public_key())

	def encrypt_bytes_with_peer_public_key(self, data: bytes) -> bytes:
		"""用朋友的公钥加锁（这样只有他的私钥才能开解）"""
		return encrypt_bytes(data, self.key_manager.require_peer_public_key())

	def decrypt_bytes_with_local_private_key(self, ciphertext: bytes) -> bytes:
		"""解密必定只能用自己不给外人的私钥来解锁"""
		return decrypt_bytes(ciphertext, self.key_manager.require_private_key())

	def encrypt_file(self, input_path: str, output_path: str, use_peer_public_key: bool = False) -> dict[str, str | int]:
		"""封装了我们前面的核心 `encrypt_file` 函数"""
		# 如果你想发给别人就要 use_peer_public_key=True，否则默认给自己加密
		public_key = self.key_manager.require_peer_public_key() if use_peer_public_key else self.key_manager.require_public_key()
		return encrypt_file(input_path, output_path, public_key)

	def decrypt_file(self, input_path: str, output_path: str) -> dict[str, str | int]:
		"""用本地绝对安全的私钥还原原来的文件"""
		return decrypt_file(input_path, output_path, self.key_manager.require_private_key())


class RSAService:
	"""
	最高层服务管家。为 GUI 界面（InfoSecurWork_GUI.py）提供极简的统一呼叫入口！
	界面不需要知道内部用了什么数学算法或填充，只要调用这个服务生说 “帮我加个密” 或者 “存一下私钥” 就行。
	"""
	def __init__(self) -> None:
		self.key_manager = RSAKeyManager()               # 左护法：管理各种钥匙
		self.file_cipher = RSAFileCipher(self.key_manager) # 右护法：专门读写文件加密

	def generate_keys(self, key_size: int = DEFAULT_KEY_SIZE) -> None:
		"""调用左护法帮你打造一对新的雌雄双剑（公私钥对）"""
		self.key_manager.generate_keys(key_size)

	def has_public_key(self) -> bool:
		"""检查有公钥吗？"""
		return self.key_manager.has_public_key()

	def has_private_key(self) -> bool:
		"""检查有私钥吗？"""
		return self.key_manager.has_private_key()

	def has_peer_public_key(self) -> bool:
		"""有朋友的公钥吗？"""
		return self.key_manager.has_peer_public_key()

	def get_key_summary(self) -> str:
		"""获取当前密钥状态摘要信息。"""
		return self.key_manager.get_key_summary()

	def save_public_key(self, file_path: str) -> None:
		"""将公钥保存到指定文件路径（PEM 格式）。"""
		self.key_manager.save_public_key(file_path)

	def save_private_key(self, file_path: str) -> None:
		"""将私钥保存到指定文件路径（PEM 格式，无密码保护）。"""
		self.key_manager.save_private_key(file_path)

	def load_public_key(self, file_path: str) -> None:
		"""从文件加载公钥。"""
		self.key_manager.load_public_key(file_path)

	def load_private_key(self, file_path: str) -> None:
		"""从文件加载私钥，并自动派生公钥。"""
		self.key_manager.load_private_key(file_path)

	def export_public_key_string(self) -> str:
		"""将公钥导出为 PEM 格式字符串。"""
		return self.key_manager.export_public_key_string()

	def import_peer_public_key_from_string(self, public_key_pem: str) -> None:
		"""从 PEM 字符串导入对端公钥。"""
		self.key_manager.import_peer_public_key_from_string(public_key_pem)

	def import_peer_public_key_from_file(self, file_path: str) -> None:
		"""从文件导入对端公钥。"""
		self.key_manager.import_peer_public_key_from_file(file_path)

	def encrypt_text_to_base64(self, plaintext: str) -> str:
		"""让左护法把前端的正常字符串变个魔术变成一串 Base64 的神奇乱码。"""
		return self.key_manager.encrypt_text_to_base64(plaintext)

	def decrypt_text_from_base64(self, ciphertext_base64: str) -> str:
		"""让左护法用你的私钥把发成乱码还原成你认识的汉字。"""
		return self.key_manager.decrypt_text_from_base64(ciphertext_base64)

	def encrypt_file(self, input_path: str, output_path: str) -> dict[str, str | int]:
		"""让右护法去对那个大文件进行加密保存，并且返回文件属性的字典。"""
		return self.file_cipher.encrypt_file(input_path, output_path)

	def decrypt_file(self, input_path: str, output_path: str) -> dict[str, str | int]:
		"""让右护法去把被锁上的文件解密出来，并还原为原始文件类型。"""
		return self.file_cipher.decrypt_file(input_path, output_path)

	def encrypt_session_key_for_peer_base64(self, session_key: bytes) -> str:
		"""使用对端公钥加密 AES 会话密钥，返回 Base64 编码。"""
		return self.key_manager.encrypt_session_key_for_peer_base64(session_key)

	def decrypt_session_key_from_peer_base64(self, encrypted_session_key_base64: str) -> bytes:
		"""使用本地私钥解密对端发来的 AES 会话密钥。"""
		return self.key_manager.decrypt_session_key_from_peer_base64(encrypted_session_key_base64)
