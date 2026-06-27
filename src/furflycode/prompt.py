"""furflycode 的内置系统提示与 ASCII 艺术 banner。"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are furflycode, a helpful AI assistant in the terminal. \
You answer questions concisely and accurately. \
When showing code, use fenced code blocks with language tags. \
Use markdown formatting where appropriate.
"""

# ruff: noqa: W291
# ASCII 猫艺术需要尾部空格以保持对齐，因此关闭本文件的 W291 检查。
CAT_BANNER = r"""
  / ᐢ⑅ᐢ \   ♡  ₊˚
꒰ ˶• ༝ •˶꒱      ♡‧₊˚    ♡
./づ~ :¨·.·¨:    ₊˚
      `·..·‘   ₊˚   ♡
"""


def render_banner(version: str, cwd: str) -> str:
    """渲染启动 banner，包含 ASCII 猫、版本号与当前工作目录。

    参数：
        version: 应用版本字符串（例如 "0.1.0"）。
        cwd: 当前工作目录。

    返回：
        格式化后的 banner 字符串。
    """
    lines = [
        CAT_BANNER,
        f"  furflycode v{version}",
        f"  cwd: {cwd}",
        "",
        "  Ready — type your message and press Enter to send.",
    ]
    return "\n".join(lines)
