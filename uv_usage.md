在执行完 uv venv（创建虚拟环境）和 uv init（初始化项目结构）后，下载和管理依赖主要有两种方式，取决于你更倾向于传统的 pip 模式还是现代的项目管理模式：
## 1. 现代项目模式（推荐）
如果你使用 uv init 初始化了项目，通常会生成一个 pyproject.toml 文件。此时建议使用 uv add 来安装依赖，因为它会自动更新项目配置文件。

* 添加新包：

uv add requests

这会自动下载包并将其写入 pyproject.toml。
* 同步所有依赖：
如果你已经有了一个包含依赖定义的 pyproject.toml 或 uv.lock，只需运行：

uv sync

这会确保你的 .venv 环境与配置文件完全一致。 [1, 2] 

------------------------------
## 2. 兼容 pip 的传统模式
如果你习惯于使用 requirements.txt 文件，或者只想快速在当前虚拟环境中安装包，可以使用 uv pip 子命令。

* 从 requirements.txt 安装：

uv pip install -r requirements.txt

* 直接安装特定包：

uv pip install requests

注意：使用 uv pip install 时，uv 会自动识别当前目录下的 .venv 虚拟环境。 [3] 

## 总结对比

| 操作需求 [1, 2, 4, 5] | 推荐命令 | 说明 |
|---|---|---|
| 安装新包并保存到项目 | uv add <package> | 类似 npm install 或 cargo add，最省心 |
| 批量安装已有依赖 | uv sync | 基于 lock 文件一键同步环境 |
| 手动操作虚拟环境 | uv pip install <package> | 与原生 pip 用法几乎一致，速度极快 |

提示：在执行安装命令前，你不需要手动 source .venv/bin/activate。uv 的大多数命令（如 uv run 或 uv add）都能自动识别并使用当前项目目录下的虚拟环境.

