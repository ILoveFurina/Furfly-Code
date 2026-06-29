"""glob 工具 — 按模式列出匹配的文件路径。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from furflycode.tool import BaseTool, Result

# 结果上限。
_MAX_RESULTS = 100


class GlobTool(BaseTool):
    """按 glob 模式（如 ``**/*.py``）返回匹配的文件路径列表。"""

    def name(self) -> str:
        return "glob"

    def description(self) -> str:
        return (
            "按 glob 模式列出匹配的文件路径（支持 ** 跨层级）。"
            "可选 path 限定搜索根目录（默认当前目录）。返回排序后的相对路径列表。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 模式，如 **/*.py",
                },
                "path": {
                    "type": "string",
                    "description": "搜索根目录，默认当前目录",
                },
            },
            "required": ["pattern"],
        }

    async def run(self, args: dict[str, Any]) -> Result:
        """执行 glob；无匹配返回空说明（非 is_error）。缺参由基类兜。"""
        pattern = args.get("pattern", "")
        if not pattern:
            return Result(is_error=True, content="缺少必填参数: pattern")
        root = Path(args.get("path") or ".")
        if not root.exists():
            return Result(is_error=True, content=f"根目录不存在: {root}")

        matches: list[str] = []
        truncated = False
        try:
            for p in root.glob(pattern):
                if p.is_dir():
                    continue
                try:
                    rel = str(p.relative_to(root)) if root != Path(".") else str(p)
                except ValueError:
                    rel = str(p)
                matches.append(rel)
                if len(matches) >= _MAX_RESULTS:
                    # 继续计数以判断是否截断，但不再收集
                    truncated = True
                    break
                if len(matches) % 100 == 0:
                    await asyncio.sleep(0)
        except OSError as e:
            return Result(is_error=True, content=f"glob 失败: {e}")

        matches_sorted = sorted(matches)
        if not matches_sorted:
            return Result(content="无匹配")
        text = "\n".join(matches_sorted)
        if truncated:
            text = text.rstrip() + "\n[truncated]"
        return Result(content=text)
