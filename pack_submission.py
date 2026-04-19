# 提交打包脚本
# 用法：在项目根目录执行 python pack_submission.py
# 功能：清理临时文件，将源码、可执行文件和文档打包为提交用的 zip 文件

import shutil
import zipfile
from pathlib import Path

# ---------- 配置 ----------
PROJECT_ROOT = Path(__file__).parent
ARCHIVE_NAME = "第X组+端到端加密即时通讯软件设计与实现.zip"  # 按实际组号修改 X
OUTPUT_PATH = PROJECT_ROOT / ARCHIVE_NAME

# 需要清理的临时目录/文件
CLEANUP_DIRS = ["build", "__pycache__", "tests/__pycache__", ".specstory"]
CLEANUP_FILES = ["SecureChat.spec", "SecureChatServer.spec"]

# 打包时排除的路径模式
EXCLUDE_DIRS = {".git", ".vscode", "build", "__pycache__", ".specstory",
                "node_modules", ".conda", "Assistance"}
EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".zip"}
EXCLUDE_FILES = {"SecureChat.spec", "SecureChatServer.spec",
                 "pack_submission.py", ".gitattributes", ".python-version",
                 "uv.lock", "RSA_Encrypt_Decrypt_Tool.exe"}


def clean_temp_files() -> None:
    """清理构建产生的临时文件和目录。"""
    for d in CLEANUP_DIRS:
        p = PROJECT_ROOT / d
        if p.exists():
            shutil.rmtree(p)
            print(f"  已删除目录: {d}")
    for f in CLEANUP_FILES:
        p = PROJECT_ROOT / f
        if p.exists():
            p.unlink()
            print(f"  已删除文件: {f}")


def should_include(path: Path) -> bool:
    """判断文件是否应该包含在提交压缩包中。"""
    parts = path.relative_to(PROJECT_ROOT).parts
    # 排除目录
    for part in parts:
        if part in EXCLUDE_DIRS:
            return False
    # 排除文件
    if path.name in EXCLUDE_FILES:
        return False
    if path.suffix in EXCLUDE_EXTENSIONS:
        return False
    return True


def create_archive() -> None:
    """创建提交用的 zip 压缩包。"""
    file_count = 0
    with zipfile.ZipFile(OUTPUT_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(PROJECT_ROOT.rglob("*")):
            if item.is_file() and should_include(item):
                arcname = item.relative_to(PROJECT_ROOT)
                zf.write(item, arcname)
                file_count += 1
    print(f"  已打包 {file_count} 个文件 → {OUTPUT_PATH.name}")


def main() -> None:
    print("=" * 50)
    print("提交打包工具")
    print("=" * 50)

    print("\n[1/2] 清理临时文件...")
    clean_temp_files()

    print("\n[2/2] 创建提交压缩包...")
    create_archive()

    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\n完成! 压缩包大小: {size_mb:.1f} MB")
    print(f"路径: {OUTPUT_PATH}")
    print(f"\n提交邮箱: xiongf@bjtu.edu.cn")
    print(f"请确认压缩包命名符合「第X组+题目」规范后发送。")


if __name__ == "__main__":
    main()
