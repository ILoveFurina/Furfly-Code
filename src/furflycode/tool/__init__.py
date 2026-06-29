"""工具系统 — 统一抽象、注册中心与执行入口。

零 furflycode 依赖，不感知 LLM 协议（``ToolDefinition`` 本地定义）。
所有失败包成 ``Result(is_error=True)`` 返回，从不抛 Python 异常给上层。
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# 单个工具执行的默认超时秒数（默认，不可配）。
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


@dataclass
class ToolDefinition:
    """注册中心导出的协议无关工具定义。

    属性：
        name: 工具名。
        description: 给模型的用途说明。
        input_schema: 完整 JSON Schema（type/properties/required）。
    """

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolInputError(ValueError):
    """工具入参 JSON 解析/类型校验失败（由 BaseTool.execute 捕获包成 Result）。"""


def _parse_args(args: str) -> dict[str, Any]:
    """解析 raw JSON 参数字符串；空串归一为 ``"{}"``。失败抛 ToolInputError。

    args.strip(): 删除字符串前后的空白（包括空格、制表符和换行符）
    json.loads(s) s如果是 "" 或者是 "  "会报错 JSONDecodeError
    """
    if not args or not args.strip():
        return {}
    try:
        data = json.loads(args)
    except json.JSONDecodeError as e:
        raise ToolInputError(f"参数 JSON 解析失败: {e}") from e
    if not isinstance(data, dict):
        raise ToolInputError("参数必须是 JSON 对象")
    return data


class BaseTool(ABC):
    """工具统一抽象与共享实现基类。

    子类实现 name/description/parameters/run；execute 由本类统一提供
    "解析参数 + 必填校验 + 分发到 run" 模板。所有失败包成 Result 返回，
    从不抛 Python 异常给上层。

    设计取舍：不再单设 Tool Protocol 层——契约职责由 ABC 的 @abstractmethod
    + mypy override 签名校验承担；全工程工具均继承本类，无鸭子类型工具。
    """

    @abstractmethod
    def name(self) -> str:
        """模型看到的工具名，如 "read_file"。"""
        ...

    @abstractmethod
    def description(self) -> str:
        """给模型的用途说明。"""
        ...

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """手写 JSON Schema（type/properties/required/description）。"""
        ...

    @abstractmethod
    async def run(self, args: dict[str, Any]) -> Result:
        """业务实现。

        基类 execute 已解析 raw JSON 并按 schema 的 required 校验缺失/null，
        故 args 必含所有必填键且非 None。子类只需做值校验（空串/格式/存在性等）
        与实际执行，返回 Result。
        """
        ...

    async def execute(self, args: str) -> Result:
        """模板：解析 raw JSON → 按 schema required 校验缺失/null → 分发到 run。

        解析失败、非对象、必填缺失/null 均包成 Result 返回（不外抛）。
        超时由 Registry 层 asyncio.wait_for 控制。
        """
        try:
            data = _parse_args(args)
        except ToolInputError as e:
            return Result(is_error=True, content=str(e))
        for key in self.parameters().get("required", []):
            if data.get(key) is None:
                return Result(is_error=True, content=f"缺少必填参数: {key}")
        return await self.run(data)


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
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """登记一个工具；重名抛 ValueError。"""
        name = tool.name()
        if name in self._tools:
            raise ValueError(f"工具已注册: {name}")
        self._tools[name] = tool
        self._order.append(name)

    def get(self, name: str) -> BaseTool | None:
        """按名查找工具；未命中返回 None。"""
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """按注册顺序导出全部工具定义。"""
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
        """按名执行工具，受超时保护；任何失败都包成 Result 返回。

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
    "BaseTool",
    "ToolInputError",
    "ToolDefinition",
    "Result",
    "Registry",
    "new_default_registry",
    "DEFAULT_TIMEOUT",
    "_truncate",
]
