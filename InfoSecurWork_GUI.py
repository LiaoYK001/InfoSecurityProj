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
	"""
	图形用户界面类，继承自 tk.Tk，代表整个应用程序的根窗口。
	为初学者导向：这个类里面定义了窗口的大小、标题、各个按钮的点击事件等。
	"""
	def __init__(self) -> None:
		# 初始化父类 tk.Tk 
		super().__init__()
		self.title("RSA 非对称加密解密工具")  # 设置窗口标题
		self.geometry("980x720")             # 设置界面的初始宽和高 (宽 x 高)
		self.minsize(900, 640)               # 设置窗口可以缩小的最小尺寸

		# 实例化后端服务，它封装了核心的 RSA 加密与解密逻辑
		self.rsa_service = RSAService()

		# Tkinter 的各种 StringVar 用于绑定到输入框、标签等组件上，当值变化时，界面会自动更新
		self.key_size_var = tk.StringVar(value=str(DEFAULT_KEY_SIZE)) # 当前选中的密钥长度
		self.public_key_path_var = tk.StringVar(value="未加载")       # 界面显示的公钥路径
		self.private_key_path_var = tk.StringVar(value="未加载")      # 界面显示的私钥路径
		self.file_input_var = tk.StringVar()                          # 要加密/解密的文件路径
		self.file_output_var = tk.StringVar()                         # 加解密后的输出文件路径
		self.file_status_var = tk.StringVar(value="支持字符串、文本文件和任意二进制文件。") # 状态栏提示

		# 调用封装的界面构建方法来生成各个组件
		self._build_layout()
		# 程序启动时，自动生成一对新的密钥供使用
		self.generate_keys()

	def _build_layout(self) -> None:
		"""
		负责搭建并排版整个主页面的布局大框架（包括标题，副标题以及各个分页卡片）。
		"""
		# 一个 Frame 就像一个在窗口里面的“透明大箱子”，用来装其他的组件
		container = ttk.Frame(self, padding=12)
		container.pack(fill="both", expand=True) # 让它自适应填满全屏放大

		# 创建界面的主标题
		title = ttk.Label(
			container,
			text="基于 RSA 非对称密码体系的加密解密工具",
			font=("Microsoft YaHei UI", 16, "bold"),
		)
		title.pack(anchor="w") # 靠西（左边）对齐

		# 创建紧随其后的解释字小标题
		subtitle = ttk.Label(
			container,
			text="默认生成 1024 bit 密钥，采用 RSA-OAEP(SHA-256) 分块处理字符串、文本文件与二进制文件。",
		)
		subtitle.pack(anchor="w", pady=(4, 10))

		# 创建一个“笔记本”组件（Notebook），用于存放多个切换页面（类似网页浏览器标签）
		notebook = ttk.Notebook(container)
		notebook.pack(fill="both", expand=True)

		# 创建三个分页小箱子（Frame）放入笔记本
		self.key_tab = ttk.Frame(notebook, padding=12)
		self.text_tab = ttk.Frame(notebook, padding=12)
		self.file_tab = ttk.Frame(notebook, padding=12)

		# 给笔记本标签起名：
		notebook.add(self.key_tab, text="密钥管理")
		notebook.add(self.text_tab, text="字符串加解密")
		notebook.add(self.file_tab, text="文件加解密")

		# 分别叫来专门的函数将对应的各种组件填满三个空箱子
		self._build_key_tab()
		self._build_text_tab()
		self._build_file_tab()

	def _build_key_tab(self) -> None:
		"""
		搭建第一页：“密钥管理”页里面的东西。包含了一排设置按钮和详细信息展示框。
		"""
		# 一组有关“密钥参数”的操作面板
		options_frame = ttk.LabelFrame(self.key_tab, text="密钥参数", padding=12)
		options_frame.pack(fill="x") # 宽度拉满，高度不变

		# 第一行的选择框与各大按钮
		ttk.Label(options_frame, text="密钥长度:").grid(row=0, column=0, sticky="w")
		key_size_box = ttk.Combobox(
			options_frame,
			textvariable=self.key_size_var,
			values=[str(size) for size in SUPPORTED_KEY_SIZES], # 从列表选项里读取 1024/2048 
			state="readonly",
			width=12,
		)
		key_size_box.grid(row=0, column=1, sticky="w", padx=(8, 20))

		# 将点击事件与后文中定义的实际功能（command=self.xxx）对接联动起来
		ttk.Button(options_frame, text="生成新密钥", command=self.generate_keys).grid(row=0, column=2, padx=6)
		ttk.Button(options_frame, text="保存公钥", command=self.save_public_key).grid(row=0, column=3, padx=6)
		ttk.Button(options_frame, text="保存私钥", command=self.save_private_key).grid(row=0, column=4, padx=6)
		ttk.Button(options_frame, text="加载公钥", command=self.load_public_key).grid(row=0, column=5, padx=6)
		ttk.Button(options_frame, text="加载私钥", command=self.load_private_key).grid(row=0, column=6, padx=6)

		# 状态提示框架：展示当前公钥/私钥的读取情况
		status_frame = ttk.LabelFrame(self.key_tab, text="当前状态", padding=12)
		status_frame.pack(fill="x", pady=(12, 0))
		status_frame.columnconfigure(1, weight=1)

		ttk.Label(status_frame, text="公钥来源:").grid(row=0, column=0, sticky="nw")
		ttk.Label(status_frame, textvariable=self.public_key_path_var).grid(row=0, column=1, sticky="nw")
		ttk.Label(status_frame, text="私钥来源:").grid(row=1, column=0, sticky="nw", pady=(6, 0))
		ttk.Label(status_frame, textvariable=self.private_key_path_var).grid(row=1, column=1, sticky="nw", pady=(6, 0))

		# 允许你滚动查看的长文本显示大框架（用于展示 RSA 提示与明细信息）
		self.key_info_text = scrolledtext.ScrolledText(self.key_tab, wrap="word", height=20)
		self.key_info_text.pack(fill="both", expand=True, pady=(12, 0))
		self.key_info_text.configure(state="disabled") # 暂时锁住它禁止人手动瞎敲字进去

	def _build_text_tab(self) -> None:
		"""
		搭建第二页：“字符串加解密”。左边明文输入，右边密文结果，底下附带3个按钮。
		"""
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

		# 两个大块文本区域建立
		self.plaintext_text = scrolledtext.ScrolledText(text_panes, wrap="word")
		self.plaintext_text.grid(row=1, column=0, sticky="nsew")
		self.ciphertext_text = scrolledtext.ScrolledText(text_panes, wrap="word")
		self.ciphertext_text.grid(row=1, column=1, sticky="nsew", padx=(12, 0))

		# 封装底下这排横着的三兄弟按钮
		button_row = ttk.Frame(self.text_tab)
		button_row.pack(fill="x", pady=(12, 0))
		ttk.Button(button_row, text="加密字符串", command=self.encrypt_text).pack(side="left")
		ttk.Button(button_row, text="解密字符串", command=self.decrypt_text).pack(side="left", padx=8)
		ttk.Button(button_row, text="清空文本", command=self.clear_text_boxes).pack(side="left")

	def _build_file_tab(self) -> None:
		"""
		搭建第三页：“文件操作”。包含了原文件的选择、输出文件的选位等内容。
		"""
		file_frame = ttk.LabelFrame(self.file_tab, text="文件处理", padding=12)
		file_frame.pack(fill="x")
		file_frame.columnconfigure(1, weight=1) # 使得中间的路径输入框随窗口变化自动拉长

		# 第一行：原文件输入区域
		ttk.Label(file_frame, text="输入文件:").grid(row=0, column=0, sticky="w")
		ttk.Entry(file_frame, textvariable=self.file_input_var).grid(row=0, column=1, sticky="ew", padx=8)
		# 绑定打开文件夹找文件功能的按钮： command=self.select_input_file 
		ttk.Button(file_frame, text="浏览", command=self.select_input_file).grid(row=0, column=2)

		# 第二行：处理结果输出位置的区域
		ttk.Label(file_frame, text="输出文件:").grid(row=1, column=0, sticky="w", pady=(10, 0))
		ttk.Entry(file_frame, textvariable=self.file_output_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(10, 0))
		ttk.Button(file_frame, text="选择保存位置", command=self.select_output_file).grid(row=1, column=2, pady=(10, 0))

		# 这里放一行用来给用户做状态提示文字（蓝色字体文字）
		ttk.Label(
			self.file_tab,
			textvariable=self.file_status_var,
			foreground="#0b5cab",
			wraplength=860,
		).pack(anchor="w", pady=(10, 0))

		# 新建操作小箱子，塞进去两兄弟按钮：加密/解密
		actions = ttk.Frame(self.file_tab)
		actions.pack(fill="x", pady=(12, 0))
		ttk.Button(actions, text="加密文件", command=self.encrypt_selected_file).pack(side="left")
		ttk.Button(actions, text="解密文件", command=self.decrypt_selected_file).pack(side="left", padx=8)

		# 底部“使用说明”的贴心提示栏
		tips = ttk.LabelFrame(self.file_tab, text="说明", padding=12)
		tips.pack(fill="both", expand=True, pady=(12, 0))
		tips_text = (
			"1. 文本文件与二进制文件均按字节流处理，不依赖文件类型。\n"
			"2. 加密输出会写入自定义文件头与原文件元数据，默认建议扩展名为 .rsa。\n"
			"3. 解密时请使用与加密匹配的私钥，否则会出现解密失败。"
		)
		ttk.Label(tips, text=tips_text, justify="left").pack(anchor="w")

	# ========== 下方全部都是各种小按钮实际触发调用的内部函数 =============

	def update_key_info(self, message: str) -> None:
		"""在右侧文本大框中刷新打印消息（更新钥匙简报）"""
		self.key_info_text.configure(state="normal") # 给大文本框开锁（允许编辑）
		self.key_info_text.delete("1.0", tk.END)     # 清空里面原有的文字
		self.key_info_text.insert(tk.END, message)   # 插入新的信息报告
		self.key_info_text.configure(state="disabled") # 再次把大文本框锁住

	def refresh_key_summary(self) -> None:
		"""向底层 rsa_core 发送请求获知现在的钥匙列表情况，借此来刷新到前台展示"""
		if not self.rsa_service.has_public_key() or not self.rsa_service.has_private_key():
			self.update_key_info("当前未加载完整的 RSA 密钥对。")
			return
		self.update_key_info(self.rsa_service.get_key_summary())

	def generate_keys(self) -> None:
		"""用户点击“生成新密钥”按钮后发生的事"""
		try:
			# 从前端下拉框上提取当前所选的数字 (1024 还是 2048 等等)
			key_size = int(self.key_size_var.get())
			self.rsa_service.generate_keys(key_size) 
			# 更新各种图形标签上的文字
			self.public_key_path_var.set(f"程序内新生成 ({key_size} bit)")
			self.private_key_path_var.set(f"程序内新生成 ({key_size} bit)")
			self.refresh_key_summary()
			self.file_status_var.set(f"已生成新的 {key_size} bit RSA 密钥对。")
		except Exception as error:
			# 若计算挂了或是啥问题，就弹窗红叉报错
			messagebox.showerror("生成密钥失败", str(error))

	def save_public_key(self) -> None:
		"""用户点击“保存公钥”：要求将公钥存到此电脑上"""
		try:
			# 防御性判断：目前到底有没有能够保持的公钥
			if not self.rsa_service.has_public_key():
				raise ValueError("当前未加载公钥。")
			# 召唤系统自带的“另存为”对话窗口给用户选路径
			file_path = filedialog.asksaveasfilename(
				title="保存公钥",
				defaultextension=".pem",
				filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
			)
			if not file_path:
				return # 会发生在这个用户刚刚在弹窗里点了“取消”的情况
			
			# 调用 rsa_core 的存盘功能真正保存到文件里
			self.rsa_service.save_public_key(file_path)
			self.public_key_path_var.set(file_path)
			self.file_status_var.set("公钥已保存。")
		except Exception as error:
			messagebox.showerror("保存公钥失败", str(error))

	def save_private_key(self) -> None:
		"""同样的原理：用来保存私钥文件(格式依然是 .pem)"""
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
		"""从硬盘文件中把一个存起来的公钥读取到程序内使用"""
		try:
			# 召唤出系统自带的“选择打开文件”对话框
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
		"""加载私钥操作"""
		try:
			file_path = filedialog.askopenfilename(
				title="加载私钥",
				filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
			)
			if not file_path:
				return
			self.rsa_service.load_private_key(file_path)
			self.private_key_path_var.set(file_path)
			# 这里强调了密码学上的特点：只要读取还原了私钥，我们连带着也就拥有了它绑定的专属公钥
			self.public_key_path_var.set(f"由私钥派生: {file_path}")
			self.refresh_key_summary()
			self.file_status_var.set("私钥已加载。")
		except Exception as error:
			messagebox.showerror("加载私钥失败", str(error))

	def encrypt_text(self) -> None:
		"""短字符串加密按钮事件：把用户在左边输入框的短句转换成乱码（Base64）塞到右边"""
		try:
			# get("1.0", tk.END) 取出了从第 1 行第 0 字符一直到末尾的全部文本内容。 rstrip("\n") 删去了结尾换行
			plaintext = self.plaintext_text.get("1.0", tk.END).rstrip("\n")
			encoded = self.rsa_service.encrypt_text_to_base64(plaintext)
			self.ciphertext_text.delete("1.0", tk.END) # 右边老内容清空
			self.ciphertext_text.insert(tk.END, encoded) # 新算出来的结果打上去
		except Exception as error:
			messagebox.showerror("字符串加密失败", str(error))

	def decrypt_text(self) -> None:
		"""短文本解密按钮事件"""
		try:
			ciphertext_base64 = self.ciphertext_text.get("1.0", tk.END).strip()
			plaintext = self.rsa_service.decrypt_text_from_base64(ciphertext_base64)
			self.plaintext_text.delete("1.0", tk.END)
			self.plaintext_text.insert(tk.END, plaintext)
		except Exception as error:
			messagebox.showerror("字符串解密失败", str(error))

	def clear_text_boxes(self) -> None:
		"""就是清空文本，全闪电消灭干净"""
		self.plaintext_text.delete("1.0", tk.END)
		self.ciphertext_text.delete("1.0", tk.END)

	def select_input_file(self) -> None:
		"""文件界面：浏览输入待办文件（可能是要加密也是要解密的文件）"""
		file_path = filedialog.askopenfilename(title="选择要处理的文件")
		if not file_path:
			return
		self.file_input_var.set(file_path)
		# 这是一个小妙招：如果此时下方目标出口没内容，程序自动“帮忙贴上 .rsa”作为建议的新名称
		if not self.file_output_var.get():
			input_path = Path(file_path)
			suggested_output = input_path.with_suffix(input_path.suffix + ".rsa") if input_path.suffix else Path(str(input_path) + ".rsa")
			self.file_output_var.set(str(suggested_output))

	def select_output_file(self) -> None:
		"""用户想要自己明确指定文件加密解密后的路径名称"""
		file_path = filedialog.asksaveasfilename(title="选择输出文件")
		if file_path:
			self.file_output_var.set(file_path)

	def ensure_file_paths(self) -> tuple[str, str]:
		"""这是一个小小的防御性助理函数，执行前它先排查路径是不是合法或没写"""
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
		"""将上面的选择结果送入底层做重体力的加密文件操作"""
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
		"""还原解密文件到用户选择的位置"""
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


# 程序总司令从这里进入！这是 Python 专属套路：当被当做主程序双击运行时，这个分支才会被激活。
if __name__ == "__main__":
	# 创建出我们在之前定义好的那个 “最顶层大箱子” GUI应用
	app = RSAApp()
	# mainloop() 让大窗体保持运行，而不是一闪而过（通过监控各种鼠标键盘动作并刷新屏幕来实现的死循环）
	app.mainloop()
