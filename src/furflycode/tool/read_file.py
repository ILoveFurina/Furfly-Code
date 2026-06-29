"""read_file 工具 — 读取文件文本内容（带行号）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from furflycode.tool import Result, _truncate

# 读文件上限（N5/AC2/AC13）。
_MAX_LINES = 2000
_MAX_CHARS = 256 * 1024  # 256KB


class ReadFileTool:
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

    async def execute(self, args: str) -> Result:
        """读文件；空 args 当 ``"{}"``。"""
        data = _parse_args(args)
        if isinstance(data, Result):
            return data
        path_str = data.get("path")
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


def _parse_args(args: str) -> dict[str, Any] | Result:
    """
    解析 raw JSON 参数字符串；空串归一为 ``"{}"``。失败返回 Result 错误。
    args.strip(): 删除字符串前后的空白（包括空格、制表符和换行符）
    json.loads(s) s如果是 "" 或者是 "  "会报错 JSONDecodeError
    """
    if not args or not args.strip():
        args = "{}"
    try:
        data = json.loads(args)
    except json.JSONDecodeError as e:
        return Result(is_error=True, content=f"参数 JSON 解析失败: {e}")
    if not isinstance(data, dict):
        return Result(is_error=True, content="参数必须是 JSON 对象")
    return data
