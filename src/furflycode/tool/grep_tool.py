"""grep 工具 — 按正则搜代码内容，返回命中位置。"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from furflycode.tool import BaseTool, Result

# 命中上限。
_MAX_HITS = 100
# 单行长度上限，超出标注未完整搜索。
_MAX_LINE_LEN = 1024 * 1024


class GrepTool(BaseTool):
    """按 Python 正则在文件内容中检索，返回 file:line:content 命中列表。"""

    def name(self) -> str:
        return "grep"

    def is_read_only(self) -> bool:
        return True

    def description(self) -> str:
        return (
            "按 Python 正则表达式在文件内容中检索，返回命中位置（file:line:content）。"
            "可选 path 限定根目录、glob 限定文件名过滤（默认递归全部文件）。"
            "无命中返回空说明；正则非法返回结构化错误。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Python 正则表达式",
                },
                "path": {
                    "type": "string",
                    "description": "搜索根目录，默认当前目录",
                },
                "glob": {
                    "type": "string",
                    "description": "文件名过滤模式，如 *.py",
                },
            },
            "required": ["pattern"],
        }

    async def run(self, args: dict[str, Any]) -> Result:
        """执行 grep；正则非法为 is_error，无命中非 is_error。缺参由基类兜。"""
        pattern = args.get("pattern", "")
        if not pattern:
            return Result(is_error=True, content="缺少必填参数: pattern")
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return Result(is_error=True, content=f"正则非法: {e}")

        root = Path(args.get("path") or ".")
        if not root.exists():
            return Result(is_error=True, content=f"根目录不存在: {root}")
        name_glob = args.get("glob") or "*"

        hits: list[str] = []
        truncated = False
        try:
            iterator = root.rglob(name_glob)
            for file in iterator:
                if not file.is_file():
                    continue
                try:
                    with file.open("r", encoding="utf-8", errors="replace") as f:
                        for lineno, line in enumerate(f, 1):
                            if len(line) > _MAX_LINE_LEN:
                                # 避免超长行拖垮正则引擎
                                continue
                            if rx.search(line):
                                # rstrip()防止去掉代码缩进
                                hits.append(f"{file}:{lineno}:{line.rstrip()}")
                                if len(hits) >= _MAX_HITS:
                                    truncated = True
                                    break
                    await asyncio.sleep(0)
                except (OSError, UnicodeDecodeError):
                    continue
                if truncated:
                    break
        except OSError as e:
            return Result(is_error=True, content=f"grep 失败: {e}")

        if not hits:
            return Result(content="无命中")
        text = "\n".join(hits)
        if truncated:
            text = text.rstrip() + "\n[truncated]"
        return Result(content=text)
