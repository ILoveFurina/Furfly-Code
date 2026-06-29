"""edit_file 工具 — 唯一匹配替换。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from furflycode.tool import Result
from furflycode.tool.read_file import _parse_args


class EditFileTool:
    """对原文片段做唯一匹配替换；匹配数不为 1 时返回可区分错误。"""

    def name(self) -> str:
        return "edit_file"

    def description(self) -> str:
        return (
            "对指定文件中的 old_string 做唯一匹配替换为 new_string。"
            "要求 old_string 在文件中恰好出现一次；匹配 0 次或多次时返回错误，"
            "请提供更长上下文使其唯一。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要修改的文件路径"},
                "old_string": {"type": "string", "description": "要被替换的原文片段"},
                "new_string": {"type": "string", "description": "替换为的新文片段"},
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, args: str) -> Result:
        """执行唯一匹配替换；0/多匹配返回可区分错误（AC4）。"""
        data = _parse_args(args)
        if isinstance(data, Result):
            return data
        path_str = data.get("path")
        old_string = data.get("old_string")
        new_string = data.get("new_string")
        if not path_str:
            return Result(is_error=True, content="缺少必填参数: path")
        if old_string is None:
            return Result(is_error=True, content="缺少必填参数: old_string")
        if new_string is None:
            return Result(is_error=True, content="缺少必填参数: new_string")

        path = Path(path_str)
        try:
            if not path.exists():
                return Result(is_error=True, content=f"文件不存在: {path_str}")
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return Result(is_error=True, content=f"读取失败: {e}")

        n = content.count(old_string)
        if n == 0:
            return Result(is_error=True, content="未找到匹配的内容")
        if n > 1:
            return Result(
                is_error=True,
                content=f"匹配到 {n} 处，old_string 不唯一，请提供更长上下文使其唯一",
            )
        new_content = content.replace(old_string, new_string, 1)
        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as e:
            return Result(is_error=True, content=f"写回失败: {e}")
        return Result(content=f"已修改 {path_str}（替换 1 处）")
