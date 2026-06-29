"""工具系统 — 统一抽象、注册中心与执行入口。

零外部依赖，不感知 LLM 协议。所有失败包成 ``Result(is_error=True)``
返回，从不抛 Python 异常给上层（F1/F9/N4）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from furflycode.llm import ToolDefinition

# 单个工具执行的默认超时秒数（N1，不可配）。
DEFAULT_TIMEOUT: float = 30.0


@dataclass
class Result:
    """工具执行结果——永远以值类型返回，从不抛异常给上层。

    属性：
        content: 回灌给模型的文本（已截断/带行号等）。
        is_error: True 表示结构化错误，content 即错误描述。
    """

    content: str
    is_error: bool = False


@runtime_checkable
class Tool(Protocol):
    """统一工具抽象（F1）。"""

    def name(self) -> str:
        """模型看到的工具名，如 "read_file"。"""
        ...

    def description(self) -> str:
        """给模型的用途说明。"""
        ...

    def parameters(self) -> dict[str, Any]:
        """手写 JSON Schema（type/properties/required/description）。"""
        ...

    async def execute(self, args: str) -> Result:
        """执行工具。args 为 raw JSON 字符串；超时由外部 asyncio.wait_for 控制。"""
        ...


def _truncate(s: str, max_lines: int, max_chars: int) -> str:
    """对 *s* 做行数与字符数双重上限截断，超出尾部追加 ``[truncated]`` 标注。"""
    if not s:
        return s
    lines = s.split("\n")
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True
    if truncated:
        text = text.rstrip() + "\n[truncated]"
    return text


class Registry:
    """集中登记、按名查找、导出定义、按名执行。"""

    def __init__(self) -> None:
        self._order: list[str] = []  # 保持注册顺序，导出稳定
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """登记一个工具；重名抛 ValueError。"""
        name = tool.name()
        if name in self._tools:
            raise ValueError(f"工具已注册: {name}")
        self._tools[name] = tool
        self._order.append(name)

    def get(self, name: str) -> Tool | None:
        """按名查找工具；未命中返回 None。"""
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """按注册顺序导出全部工具定义（F3/AC1）。"""
        return [
            ToolDefinition(
                name=n,
                description=self._tools[n].description(),
                input_schema=self._tools[n].parameters(),
            )
            for n in self._order
        ]

    async def execute(
        self, name: str, args: str, timeout: float = DEFAULT_TIMEOUT
    ) -> Result:
        """按名执行工具，受超时保护；任何失败都包成 Result 返回（F5/F9）。

        未知工具、超时、执行异常均转为 ``Result(is_error=True)``。
        """
        tool = self.get(name)
        if tool is None:
            return Result(is_error=True, content=f"未知工具: {name}")
        try:
            return await asyncio.wait_for(tool.execute(args), timeout)
        except asyncio.TimeoutError:
            return Result(is_error=True, content=f"工具 {name} 执行超时（{timeout}s）")
        except Exception as e:  # noqa: BLE001 — 所有失败包成结果回灌
            return Result(is_error=True, content=f"工具 {name} 异常: {e}")


def new_default_registry() -> Registry:
    """构造并注册 6 个核心工具，返回 Registry。"""
    from furflycode.tool.bash import BashTool
    from furflycode.tool.edit_file import EditFileTool
    from furflycode.tool.glob_tool import GlobTool
    from furflycode.tool.grep_tool import GrepTool
    from furflycode.tool.read_file import ReadFileTool
    from furflycode.tool.write_file import WriteFileTool

    registry = Registry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(BashTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    return registry


__all__ = [
    "Tool",
    "Result",
    "Registry",
    "new_default_registry",
    "DEFAULT_TIMEOUT",
    "_truncate",
]
