"""
将 Demonstration/mmd/ 下的 .mmd 文件通过 mermaid.ink 渲染为高清 PNG。
用法：python export_mermaid_png.py
输出：Demonstration/png/ 目录
"""

import base64
import json
import os
import sys
import urllib.request
import zlib

MMD_DIR = os.path.join(os.path.dirname(__file__), "Demonstration", "mmd")
PNG_DIR = os.path.join(os.path.dirname(__file__), "Demonstration", "png")


def mermaid_to_png(mmd_code: str, output_path: str, scale: int = 4) -> None:
    """通过 kroki.io 服务将 Mermaid 代码渲染为高清 PNG。"""
    # kroki.io API: POST JSON body with diagram source
    payload = json.dumps({
        "diagram_source": mmd_code,
        "diagram_type": "mermaid",
        "output_format": "png",
        "diagram_options": {"theme": "default"},
    }).encode("utf-8")
    url = "https://kroki.io/mermaid/png"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()

    with open(output_path, "wb") as f:
        f.write(data)
    print(f"  ✅ {os.path.basename(output_path)} ({len(data) // 1024} KB)")


def main() -> None:
    os.makedirs(PNG_DIR, exist_ok=True)

    if not os.path.isdir(MMD_DIR):
        print(f"❌ 目录不存在: {MMD_DIR}")
        sys.exit(1)

    mmd_files = sorted(f for f in os.listdir(MMD_DIR) if f.endswith(".mmd"))
    if not mmd_files:
        print("❌ 没有找到 .mmd 文件")
        sys.exit(1)

    print(f"🔄 共 {len(mmd_files)} 个 Mermaid 图需要导出...\n")

    for fname in mmd_files:
        src = os.path.join(MMD_DIR, fname)
        png_name = fname.replace(".mmd", ".png")
        dst = os.path.join(PNG_DIR, png_name)

        with open(src, encoding="utf-8") as f:
            code = f.read().strip()

        if os.path.exists(dst) and os.path.getsize(dst) > 1024:
            print(f"⏭️  跳过 {fname}（已存在 {os.path.getsize(dst) // 1024} KB）")
            continue

        print(f"🖼️  渲染 {fname} ...")
        success = False
        for attempt in range(3):
            try:
                mermaid_to_png(code, dst)
                success = True
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  ⚠️ 第 {attempt + 1} 次失败，重试中...")
                    import time
                    time.sleep(2)
                else:
                    print(f"  ❌ 失败: {e}")

    print(f"\n✨ 导出完成！PNG 文件位于 {PNG_DIR}")


if __name__ == "__main__":
    main()
