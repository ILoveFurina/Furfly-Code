"""会话上下文注入模块 — 会话启动时一次性预读环境信息与 FURFLY.md，会话期间不重读。

协议无关叶子层（不 import anthropic/openai）。产出注入用消息内容字符串，
由编排层（agent）注入 messages 开头，不进 system 缓存区。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from furflycode.context.env_info import render_env_info
from furflycode.context.furfly_md import _collect_furfly_md_paths, load_furfly_md


@dataclass(frozen=True)
class SessionContext:
    """会话启动时预读的上下文快照，会话期间不可变、不重读。

    属性：
        cwd: 预读时的工作目录。
        env_info_block: ``<env_info>`` 标签包裹的环境信息（注入 messages 开头）。
        furfly_md_block: ``<furfly_md>`` 标签包裹的合并规范内容；无内容时为空串。
        furfly_md_paths: 实际加载到的 FURFLY.md 路径列表（供环境信息展示来源）。
    """

    cwd: Path
    env_info_block: str
    furfly_md_block: str
    furfly_md_paths: list[Path]


def build_session_context(cwd: Path) -> SessionContext:
    """会话启动时一次性预读环境信息与 FURFLY.md，返回不可变快照。

    会话期间复用此快照、不重读文件。FURFLY.md 缺失/读取失败静默跳过，
    不阻断启动。
    """
    furfly_md_paths = _collect_furfly_md_paths(cwd)
    content = load_furfly_md(cwd)
    furfly_md_block = f"<furfly_md>\n{content}\n</furfly_md>" if content.strip() else ""
    env_info_block = render_env_info(cwd, furfly_md_paths)
    return SessionContext(
        cwd=cwd,
        env_info_block=env_info_block,
        furfly_md_block=furfly_md_block,
        furfly_md_paths=furfly_md_paths,
    )


__all__ = [
    "SessionContext",
    "build_session_context",
    "load_furfly_md",
    "render_env_info",
]
