"""write_file 工具 — 写入（覆盖）文件，父目录不存在时创建。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from furflycode.tool import BaseTool, Result


class WriteFileTool(BaseTool):
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

    async def run(self, args: dict[str, Any]) -> Result:
        """写文件；缺参由基类兜，空 path 在此拦截，content 允许空串。"""
        path_str = args.get("path", "")
        content = args.get("content", "")
        if not path_str:
            return Result(is_error=True, content="缺少必填参数: path")
        try:
            path = Path(path_str)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return Result(is_error=True, content=f"写入失败: {e}")
        return Result(
            content=f"已写入 {path_str}（{len(content.encode('utf-8'))} 字节）"
        )
