"""FURFLY.md 项目规范加载器 — 叶子层，协议无关。

会话启动时从当前工作目录逐级向上查找所有 ``FURFLY.md``，到项目根（含 ``.git``
的目录）为止。找到的多份内容全部叠加，就近（更靠近 cwd 的）内容排列在序列后部，
让模型先看全局再看局部。文件缺失/读取失败静默跳过，大文件截断标注。
不 import anthropic/openai，可被任何层依赖。
"""

from __future__ import annotations

from pathlib import Path

from furflycode.tool import _truncate

# 规范文件名。
_FURFLY_MD = "FURFLY.md"
# 单份 FURFLY.md 内容的字符上限（超出截断标注，避免挤占消息通道）。
_MAX_CHARS = 8 * 1024


def _find_project_root(start: Path) -> Path:
    """从 *start* 逐级向上找到含 ``.git`` 的项目根；找不到则回退到 *start* 的根盘。

    用于限定 FURFLY.md 向上查找的边界，避免一路爬到盘根。
    """
    current = start.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    # 无 .git 时回退到起点本身（仅在起点目录及其下查找，实际向上至多到起点）。
    return start.resolve()


def _collect_furfly_md_paths(cwd: Path) -> list[Path]:
    """从项目根到 cwd 路径上收集所有 FURFLY.md，按从远到近顺序返回。

    返回顺序：项目根的 FURFLY.md 在前（全局），cwd 的在后（局部），
    便于后续叠加时就近内容排在序列后部。
    """
    root = _find_project_root(cwd)
    cwd_resolved = cwd.resolve()
    # 从 cwd 逐级向上收集到 root（含两端），得到就近在前的目录链。
    upward: list[Path] = []
    current: Path | None = cwd_resolved
    while current is not None:
        upward.append(current)
        if current == root:
            break
        current = current.parent
    # 反转为从远（项目根）到近（cwd），让叠加时就近内容排在后。
    downward = list(reversed(upward))
    return [p / _FURFLY_MD for p in downward if (p / _FURFLY_MD).exists()]


def load_furfly_md(cwd: Path) -> str:
    """从 *cwd* 向上查找并合并所有 FURFLY.md，返回合并后的内容字符串。

    多份内容叠加，就近（更靠近 cwd）内容排列在后；每份以来源路径标注分节；
    文件缺失/读取失败静默跳过；单份超 ``_MAX_CHARS`` 截断标注。无任何命中时
    返回空串。
    """
    paths = _collect_furfly_md_paths(cwd)
    sections: list[str] = []
    for p in paths:
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # 静默跳过读取失败，不阻断启动。
            continue
        body = _truncate(raw, max_lines=10_000, max_chars=_MAX_CHARS)
        sections.append(f"# 来源: {p}\n{body}")
    return "\n\n".join(sections)
