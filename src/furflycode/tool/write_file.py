"""write_file 工具 — 写入（覆盖）文件，父目录不存在时创建。"""

from __future__ import annotations

from typing import Any

from furflycode.tool import Result
from furflycode.tool.read_file import _parse_args


class WriteFileTool:
    """写入（覆盖）文件；父目录不存在时自动创建。"""

    def name(self) -> str:
        return "write_file"

    def description(self) -> str:
        return (
            "将内容写入指定路径的文件（覆盖已有内容）。父目录不存在时自动创建。"
            "返回写入路径与字节数；写入失败返回结构化错误。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要写入的文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文本内容",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, args: str) -> Result:
        """写文件；解析失败、缺参、写入失败均包成 Result。"""
        data = _parse_args(args)
        if isinstance(data, Result):
            return data
        path_str = data.get("path")
        content = data.get("content")
        if not path_str:
            return Result(is_error=True, content="缺少必填参数: path")
        if content is None:
            return Result(is_error=True, content="缺少必填参数: content")
        try:
            from pathlib import Path

            path = Path(path_str)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return Result(is_error=True, content=f"写入失败: {e}")
        return Result(
            content=f"已写入 {path_str}（{len(content.encode('utf-8'))} 字节）"
        )
