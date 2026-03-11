from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from rsa_core import (
	DEFAULT_KEY_SIZE,
	SUPPORTED_KEY_SIZES,
	RSAService,
)

class RSAApp(tk.Tk):
	def __init__(self) -> None:
		super().__init__()
		self.title("RSA 非对称加密解密工具")
		self.geometry("980x720")
		self.minsize(900, 640)

		self.rsa_service = RSAService()

		self.key_size_var = tk.StringVar(value=str(DEFAULT_KEY_SIZE))
		self.public_key_path_var = tk.StringVar(value="未加载")
		self.private_key_path_var = tk.StringVar(value="未加载")
		self.file_input_var = tk.StringVar()
		self.file_output_var = tk.StringVar()
		self.file_status_var = tk.StringVar(value="支持字符串、文本文件和任意二进制文件。")

		self._build_layout()
		self.generate_keys()

	def _build_layout(self) -> None:
		container = ttk.Frame(self, padding=12)
		container.pack(fill="both", expand=True)

		title = ttk.Label(
			container,
			text="基于 RSA 非对称密码体系的加密解密工具",
			font=("Microsoft YaHei UI", 16, "bold"),
		)
		title.pack(anchor="w")

		subtitle = ttk.Label(
			container,
			text="默认生成 1024 bit 密钥，采用 RSA-OAEP(SHA-256) 分块处理字符串、文本文件与二进制文件。",
		)
		subtitle.pack(anchor="w", pady=(4, 10))

		notebook = ttk.Notebook(container)
		notebook.pack(fill="both", expand=True)

		self.key_tab = ttk.Frame(notebook, padding=12)
		self.text_tab = ttk.Frame(notebook, padding=12)
		self.file_tab = ttk.Frame(notebook, padding=12)

		notebook.add(self.key_tab, text="密钥管理")
		notebook.add(self.text_tab, text="字符串加解密")
		notebook.add(self.file_tab, text="文件加解密")

		self._build_key_tab()
		self._build_text_tab()
		self._build_file_tab()

	def _build_key_tab(self) -> None:
		options_frame = ttk.LabelFrame(self.key_tab, text="密钥参数", padding=12)
		options_frame.pack(fill="x")

		ttk.Label(options_frame, text="密钥长度:").grid(row=0, column=0, sticky="w")
		key_size_box = ttk.Combobox(
			options_frame,
			textvariable=self.key_size_var,
			values=[str(size) for size in SUPPORTED_KEY_SIZES],
			state="readonly",
			width=12,
		)
		key_size_box.grid(row=0, column=1, sticky="w", padx=(8, 20))

		ttk.Button(options_frame, text="生成新密钥", command=self.generate_keys).grid(row=0, column=2, padx=6)
		ttk.Button(options_frame, text="保存公钥", command=self.save_public_key).grid(row=0, column=3, padx=6)
		ttk.Button(options_frame, text="保存私钥", command=self.save_private_key).grid(row=0, column=4, padx=6)
		ttk.Button(options_frame, text="加载公钥", command=self.load_public_key).grid(row=0, column=5, padx=6)
		ttk.Button(options_frame, text="加载私钥", command=self.load_private_key).grid(row=0, column=6, padx=6)

		status_frame = ttk.LabelFrame(self.key_tab, text="当前状态", padding=12)
		status_frame.pack(fill="x", pady=(12, 0))
		status_frame.columnconfigure(1, weight=1)

		ttk.Label(status_frame, text="公钥来源:").grid(row=0, column=0, sticky="nw")
		ttk.Label(status_frame, textvariable=self.public_key_path_var).grid(row=0, column=1, sticky="nw")
		ttk.Label(status_frame, text="私钥来源:").grid(row=1, column=0, sticky="nw", pady=(6, 0))
		ttk.Label(status_frame, textvariable=self.private_key_path_var).grid(row=1, column=1, sticky="nw", pady=(6, 0))

		self.key_info_text = scrolledtext.ScrolledText(self.key_tab, wrap="word", height=20)
		self.key_info_text.pack(fill="both", expand=True, pady=(12, 0))
		self.key_info_text.configure(state="disabled")

	def _build_text_tab(self) -> None:
		description = ttk.Label(
			self.text_tab,
			text="明文将以 UTF-8 编码后进行 RSA 分块加密，密文使用 Base64 展示，便于复制保存。",
		)
		description.pack(anchor="w")

		text_panes = ttk.Frame(self.text_tab)
		text_panes.pack(fill="both", expand=True, pady=(10, 0))
		text_panes.columnconfigure(0, weight=1)
		text_panes.columnconfigure(1, weight=1)
		text_panes.rowconfigure(1, weight=1)

		ttk.Label(text_panes, text="明文输入").grid(row=0, column=0, sticky="w")
		ttk.Label(text_panes, text="密文 / 解密结果").grid(row=0, column=1, sticky="w", padx=(12, 0))

		self.plaintext_text = scrolledtext.ScrolledText(text_panes, wrap="word")
		self.plaintext_text.grid(row=1, column=0, sticky="nsew")
		self.ciphertext_text = scrolledtext.ScrolledText(text_panes, wrap="word")
		self.ciphertext_text.grid(row=1, column=1, sticky="nsew", padx=(12, 0))

		button_row = ttk.Frame(self.text_tab)
		button_row.pack(fill="x", pady=(12, 0))
		ttk.Button(button_row, text="加密字符串", command=self.encrypt_text).pack(side="left")
		ttk.Button(button_row, text="解密字符串", command=self.decrypt_text).pack(side="left", padx=8)
		ttk.Button(button_row, text="清空文本", command=self.clear_text_boxes).pack(side="left")

	def _build_file_tab(self) -> None:
		file_frame = ttk.LabelFrame(self.file_tab, text="文件处理", padding=12)
		file_frame.pack(fill="x")
		file_frame.columnconfigure(1, weight=1)

		ttk.Label(file_frame, text="输入文件:").grid(row=0, column=0, sticky="w")
		ttk.Entry(file_frame, textvariable=self.file_input_var).grid(row=0, column=1, sticky="ew", padx=8)
		ttk.Button(file_frame, text="浏览", command=self.select_input_file).grid(row=0, column=2)

		ttk.Label(file_frame, text="输出文件:").grid(row=1, column=0, sticky="w", pady=(10, 0))
		ttk.Entry(file_frame, textvariable=self.file_output_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(10, 0))
		ttk.Button(file_frame, text="选择保存位置", command=self.select_output_file).grid(row=1, column=2, pady=(10, 0))

		ttk.Label(
			self.file_tab,
			textvariable=self.file_status_var,
			foreground="#0b5cab",
			wraplength=860,
		).pack(anchor="w", pady=(10, 0))

		actions = ttk.Frame(self.file_tab)
		actions.pack(fill="x", pady=(12, 0))
		ttk.Button(actions, text="加密文件", command=self.encrypt_selected_file).pack(side="left")
		ttk.Button(actions, text="解密文件", command=self.decrypt_selected_file).pack(side="left", padx=8)

		tips = ttk.LabelFrame(self.file_tab, text="说明", padding=12)
		tips.pack(fill="both", expand=True, pady=(12, 0))

		tips_text = (
			"1. 文本文件与二进制文件均按字节流处理，不依赖文件类型。\n"
			"2. 加密输出会写入自定义文件头与原文件元数据，默认建议扩展名为 .rsa。\n"
			"3. 解密时请使用与加密匹配的私钥，否则会出现解密失败。"
		)
		ttk.Label(tips, text=tips_text, justify="left").pack(anchor="w")

	def update_key_info(self, message: str) -> None:
		self.key_info_text.configure(state="normal")
		self.key_info_text.delete("1.0", tk.END)
		self.key_info_text.insert(tk.END, message)
		self.key_info_text.configure(state="disabled")

	def refresh_key_summary(self) -> None:
		if not self.rsa_service.has_public_key() or not self.rsa_service.has_private_key():
			self.update_key_info("当前未加载完整的 RSA 密钥对。")
			return
		self.update_key_info(self.rsa_service.get_key_summary())

	def generate_keys(self) -> None:
		try:
			key_size = int(self.key_size_var.get())
			self.rsa_service.generate_keys(key_size)
			self.public_key_path_var.set(f"程序内新生成 ({key_size} bit)")
			self.private_key_path_var.set(f"程序内新生成 ({key_size} bit)")
			self.refresh_key_summary()
			self.file_status_var.set(f"已生成新的 {key_size} bit RSA 密钥对。")
		except Exception as error:
			messagebox.showerror("生成密钥失败", str(error))

	def save_public_key(self) -> None:
		try:
			if not self.rsa_service.has_public_key():
				raise ValueError("当前未加载公钥。")
			file_path = filedialog.asksaveasfilename(
				title="保存公钥",
				defaultextension=".pem",
				filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
			)
			if not file_path:
				return
			self.rsa_service.save_public_key(file_path)
			self.public_key_path_var.set(file_path)
			self.file_status_var.set("公钥已保存。")
		except Exception as error:
			messagebox.showerror("保存公钥失败", str(error))

	def save_private_key(self) -> None:
		try:
			if not self.rsa_service.has_private_key():
				raise ValueError("当前未加载私钥。")
			file_path = filedialog.asksaveasfilename(
				title="保存私钥",
				defaultextension=".pem",
				filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
			)
			if not file_path:
				return
			self.rsa_service.save_private_key(file_path)
			self.private_key_path_var.set(file_path)
			self.file_status_var.set("私钥已保存。")
		except Exception as error:
			messagebox.showerror("保存私钥失败", str(error))

	def load_public_key(self) -> None:
		try:
			file_path = filedialog.askopenfilename(
				title="加载公钥",
				filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
			)
			if not file_path:
				return
			self.rsa_service.load_public_key(file_path)
			self.public_key_path_var.set(file_path)
			self.refresh_key_summary()
			self.file_status_var.set("公钥已加载。")
		except Exception as error:
			messagebox.showerror("加载公钥失败", str(error))

	def load_private_key(self) -> None:
		try:
			file_path = filedialog.askopenfilename(
				title="加载私钥",
				filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
			)
			if not file_path:
				return
			self.rsa_service.load_private_key(file_path)
			self.private_key_path_var.set(file_path)
			self.public_key_path_var.set(f"由私钥派生: {file_path}")
			self.refresh_key_summary()
			self.file_status_var.set("私钥已加载。")
		except Exception as error:
			messagebox.showerror("加载私钥失败", str(error))

	def encrypt_text(self) -> None:
		try:
			plaintext = self.plaintext_text.get("1.0", tk.END).rstrip("\n")
			encoded = self.rsa_service.encrypt_text_to_base64(plaintext)
			self.ciphertext_text.delete("1.0", tk.END)
			self.ciphertext_text.insert(tk.END, encoded)
		except Exception as error:
			messagebox.showerror("字符串加密失败", str(error))

	def decrypt_text(self) -> None:
		try:
			ciphertext_base64 = self.ciphertext_text.get("1.0", tk.END).strip()
			plaintext = self.rsa_service.decrypt_text_from_base64(ciphertext_base64)
			self.plaintext_text.delete("1.0", tk.END)
			self.plaintext_text.insert(tk.END, plaintext)
		except Exception as error:
			messagebox.showerror("字符串解密失败", str(error))

	def clear_text_boxes(self) -> None:
		self.plaintext_text.delete("1.0", tk.END)
		self.ciphertext_text.delete("1.0", tk.END)

	def select_input_file(self) -> None:
		file_path = filedialog.askopenfilename(title="选择要处理的文件")
		if not file_path:
			return
		self.file_input_var.set(file_path)
		if not self.file_output_var.get():
			input_path = Path(file_path)
			suggested_output = input_path.with_suffix(input_path.suffix + ".rsa") if input_path.suffix else Path(str(input_path) + ".rsa")
			self.file_output_var.set(str(suggested_output))

	def select_output_file(self) -> None:
		file_path = filedialog.asksaveasfilename(title="选择输出文件")
		if file_path:
			self.file_output_var.set(file_path)

	def ensure_file_paths(self) -> tuple[str, str]:
		input_path = self.file_input_var.get().strip()
		output_path = self.file_output_var.get().strip()
		if not input_path:
			raise ValueError("请先选择输入文件。")
		if not output_path:
			raise ValueError("请先指定输出文件。")
		if not os.path.exists(input_path):
			raise ValueError("输入文件不存在。")
		return input_path, output_path

	def encrypt_selected_file(self) -> None:
		try:
			input_path, output_path = self.ensure_file_paths()
			metadata = self.rsa_service.encrypt_file(input_path, output_path)
			self.file_status_var.set(
				f"文件加密完成: {metadata['original_name']} ({metadata['original_size']} 字节) -> {output_path}"
			)
			messagebox.showinfo("加密完成", f"文件已加密并保存到:\n{output_path}")
		except Exception as error:
			messagebox.showerror("文件加密失败", str(error))

	def decrypt_selected_file(self) -> None:
		try:
			input_path, output_path = self.ensure_file_paths()
			metadata = self.rsa_service.decrypt_file(input_path, output_path)
			original_name = metadata.get("original_name", "未知文件")
			self.file_status_var.set(
				f"文件解密完成: 原文件名 {original_name}，输出路径 {output_path}"
			)
			messagebox.showinfo(
				"解密完成",
				f"文件已解密并保存到:\n{output_path}\n\n原始文件名: {original_name}",
			)
		except Exception as error:
			messagebox.showerror("文件解密失败", str(error))


if __name__ == "__main__":
	app = RSAApp()
	app.mainloop()
