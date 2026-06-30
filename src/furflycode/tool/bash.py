"""bash 工具 — 在工作目录执行 shell 命令，受超时约束。"""

from __future__ import annotations

import asyncio
from typing import Any

from furflycode.tool import BaseTool, Result, _truncate

# 命令输出上限。
_MAX_LINES = 10000
_MAX_CHARS = 30000


class BashTool(BaseTool):
    """执行 shell 命令，返回 stdout/stderr/exit_code。"""

    def name(self) -> str:
        return "bash"

    def is_read_only(self) -> bool:
        return False

    def hard_constraints(self) -> str:
        return (
            "禁止用 cat/grep/sed 等原始终端命令读取或编辑文件，改用专用工具："
            "读文件用 read_file、搜代码用 grep_tool、改文件用 edit_file。"
            "本工具仅用于执行专用工具无法覆盖的操作（如运行测试、构建、git 命令）。"
        )

    def description(self) -> str:
        return (
            "在工作目录下执行 shell 命令，返回标准输出、标准错误与退出码。"
            "受内置超时约束；超时或非零退出以结构化结果返回，不中断会话。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令",
                },
            },
            "required": ["command"],
        }

    async def run(self, args: dict[str, Any]) -> Result:
        """执行命令；超时由 Registry 层 asyncio.wait_for 兜底。

        非零退出按结果回灌让模型判断，不设 is_error。
        """
        command = args.get("command", "")
        if not command:
            return Result(is_error=True, content="缺少必填参数: command")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as e:
            return Result(is_error=True, content=f"无法启动进程: {e}")

        stdout_b, stderr_b = await proc.communicate()
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        exit_code = proc.returncode if proc.returncode is not None else -1
        text = f"exit_code: {exit_code}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        # 非零退出按结果回灌让模型判断，不设 is_error。
        return Result(content=_truncate(text, _MAX_LINES, _MAX_CHARS))
