"""read_file 工具 — 读取文件文本内容（带行号）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from furflycode.tool import BaseTool, Result, _truncate

# 读文件上限。
_MAX_LINES = 2000
_MAX_CHARS = 256 * 1024  # 256KB


class ReadFileTool(BaseTool):
    """读取指定路径的文件文本，带行号返回。"""

    def name(self) -> str:
        return "read_file"

    def description(self) -> str:
        return (
            "读取指定路径文件的文本内容，返回带行号的文本（行号与内容以制表符分隔）。"
            "用于查看文件内容。文件不存在、是目录或不可读时返回结构化错误。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要读取的文件路径",
                },
            },
            "required": ["path"],
        }

    async def run(self, args: dict[str, Any]) -> Result:
        """读文件；缺参由基类兜，此处只做值校验与读取。"""
        path_str = args.get("path", "")
        if not path_str:
            return Result(is_error=True, content="缺少必填参数: path")
        path = Path(path_str)
        try:
            if not path.exists():
                return Result(is_error=True, content=f"文件不存在: {path_str}")
            if path.is_dir():
                return Result(
                    is_error=True, content=f"路径是目录，不是文件: {path_str}"
                )
            text = path.read_text(encoding="utf-8", errors="replace")
        except PermissionError as e:
            return Result(is_error=True, content=f"无读取权限: {e}")
        except OSError as e:
            return Result(is_error=True, content=f"读取失败: {e}")

        lines = text.split("\n")
        # 生成器表达式
        numbered = "\n".join(f"{n:6d}\t{line}" for n, line in enumerate(lines, 1))
        return Result(content=_truncate(numbered, _MAX_LINES, _MAX_CHARS))
