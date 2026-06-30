"""环境信息组装 — 工作目录、平台、规范文件路径，用 ``<env_info>`` 标签包裹。

协议无关叶子层。与会话启动时一次性预读的 FURFLY.md 内容同在 messages 开头，
不进 system 缓存区，保核心提示跨项目纯净。
"""

from __future__ import annotations

import platform
from pathlib import Path


def render_env_info(cwd: Path, furfly_md_paths: list[Path]) -> str:
    """组装环境信息并用 ``<env_info>`` 标签包裹返回。

    参数：
        cwd: 当前工作目录。
        furfly_md_paths: 本次实际加载到的 FURFLY.md 路径列表（用于告知模型规范来源）。
    """
    lines = [
        f"工作目录: {cwd}",
        f"平台: {platform.system()} {platform.release()}",
    ]
    if furfly_md_paths:
        paths_text = ", ".join(str(p) for p in furfly_md_paths)
        lines.append(f"项目规范文件: {paths_text}")
    else:
        lines.append("项目规范文件: 无")
    body = "\n".join(lines)
    return f"<env_info>\n{body}\n</env_info>"
