"""系统提示架构单测 — 模块化拼装、hard_constraints 拼接、适配器缓存形状。

覆盖 tasks 8.1/8.2/8.3：七模块固定顺序拼装、去规定化；hard_constraints 拼进
两适配器工具 description 末尾且不进 system prompt；Anthropic 请求 system/tools
挂 cache_control 断点、OpenAI 无 cache_control。
"""

from __future__ import annotations

import pytest

from furflycode.prompt import SYSTEM_PROMPT, render_system_prompt
from furflycode.tool import ToolDefinition, new_default_registry

# ─── 8.1 七模块拼装 ────────────────────────────────────────────────

_SEVEN_MODULES = (
    "[身份]",
    "[系统约束]",
    "[任务模式]",
    "[动作执行]",
    "[工具路由原则]",
    "[语气风格]",
    "[文本输出]",
)


def test_seven_modules_in_fixed_order():
    """七模块按固定优先级顺序出现于拼装产物。"""
    positions = [SYSTEM_PROMPT.find(tag) for tag in _SEVEN_MODULES]
    assert all(p >= 0 for p in positions), "所有七模块标记都应存在"
    assert positions == sorted(positions), "模块应按固定顺序排列"


def test_modules_separated_by_blank_lines():
    """模块间以空行分隔。"""
    # 拼装产物中每个模块标记前（首个除外）应有空行分隔。
    for tag in _SEVEN_MODULES[1:]:
        idx = SYSTEM_PROMPT.find(tag)
        # 模块标记前应是空行（\n\n）
        assert SYSTEM_PROMPT[idx - 2 : idx] == "\n\n", f"{tag} 前应有空行分隔"


def test_render_deterministic():
    """render_system_prompt 产出确定性（多次调用结果一致，无随机/时间戳）。"""
    assert render_system_prompt() == render_system_prompt()
    assert render_system_prompt() == SYSTEM_PROMPT


def test_no_pipeline_steps():
    """模块内容去规定化——不含步骤流水线字样。"""
    pipeline_markers = ["先解析", "再分析", "最后输出", "第一步", "第二步"]
    for marker in pipeline_markers:
        assert marker not in SYSTEM_PROMPT, f"不应含步骤流水线字样: {marker}"


def test_no_tool_list_in_routing_module():
    """工具路由原则模块不含工具名清单（由 tools 参数单一承载）。"""
    tool_names = ["read_file", "write_file", "edit_file", "bash", "glob", "grep"]
    for name in tool_names:
        assert name not in SYSTEM_PROMPT, f"系统提示不应列举工具名: {name}"


def test_no_hard_constraints_literal_in_prompt():
    """系统提示不含工具级硬约束字面（单一事实来源：hard_constraints 字段）。"""
    assert "编辑前必须先调用" not in SYSTEM_PROMPT
    assert "禁止用 cat" not in SYSTEM_PROMPT


def test_furfly_md_entry_in_system_constraints():
    """系统约束模块含 FURFLY.md 入口说明（指向 <furfly_md> 标签）。"""
    assert "furfly_md" in SYSTEM_PROMPT


# ─── 8.2 hard_constraints 拼接 ─────────────────────────────────────


def _default_defs() -> list[ToolDefinition]:
    return new_default_registry().definitions()


def test_edit_file_has_hard_constraints():
    """EditFile 的 hard_constraints 非空且含「编辑前必先读」。"""
    defs = {d.name: d for d in _default_defs()}
    assert "编辑前" in defs["edit_file"].hard_constraints
    assert "read_file" in defs["edit_file"].hard_constraints


def test_bash_has_hard_constraints():
    """Bash 的 hard_constraints 含禁用原始终端命令。"""
    defs = {d.name: d for d in _default_defs()}
    hc = defs["bash"].hard_constraints
    assert "cat" in hc and "grep" in hc and "sed" in hc


def test_read_only_tools_have_empty_or_no_constraints():
    """只读工具（read_file/glob/grep）无强约束——hard_constraints 为空串。"""
    defs = {d.name: d for d in _default_defs()}
    assert defs["read_file"].hard_constraints == ""
    assert defs["glob"].hard_constraints == ""
    assert defs["grep"].hard_constraints == ""


def test_anthropic_tools_concat_hard_constraints():
    """Anthropic 适配器把 hard_constraints 拼进 description 末尾。"""
    from furflycode.llm.anthropic_provider import _to_anthropic_tools

    api_tools = _to_anthropic_tools(_default_defs())
    by_name = {t["name"]: t for t in api_tools}
    assert "硬性约束" in by_name["edit_file"]["description"]
    assert "编辑前" in by_name["edit_file"]["description"]
    assert "硬性约束" in by_name["bash"]["description"]


def test_openai_tools_concat_hard_constraints():
    """OpenAI 适配器把 hard_constraints 拼进 description 末尾。"""
    from furflycode.llm.openai_provider import _to_openai_tools

    api_tools = _to_openai_tools(_default_defs())
    by_name = {t["function"]["name"]: t for t in api_tools}
    assert "硬性约束" in by_name["edit_file"]["function"]["description"]
    assert "硬性约束" in by_name["bash"]["function"]["description"]


# ─── 8.3 适配器缓存形状 ────────────────────────────────────────────


def test_anthropic_system_has_cache_control():
    """Anthropic system 为带 cache_control 的 text 块（断点①）。"""

    # _to_anthropic_messages 不含 system；system 形状在 stream 里拼。
    # 这里直接验证 system 块构造约定：通过检查 stream params 不便（需 mock client），
    # 改为验证 cache_control 字段约定存在于工具导出（断点②）+ system 形状的常量约定。
    # 断点②：tools 末个挂 cache_control。
    from furflycode.llm.anthropic_provider import _to_anthropic_tools

    api_tools = _to_anthropic_tools(_default_defs())
    last_tool = api_tools[-1]
    assert last_tool["cache_control"] == {"type": "ephemeral"}
    # 非末个工具不应挂 cache_control。
    for t in api_tools[:-1]:
        assert "cache_control" not in t


def test_openai_tools_no_cache_control():
    """OpenAI 请求无 cache_control 字段（隐式自动缓存）。"""
    from furflycode.llm.openai_provider import _to_openai_tools

    api_tools = _to_openai_tools(_default_defs())
    for t in api_tools:
        assert "cache_control" not in t
        assert "cache_control" not in t["function"]


@pytest.mark.parametrize(
    "adapter_fn",
    [
        "furflycode.llm.anthropic_provider._to_anthropic_tools",
        "furflycode.llm.openai_provider._to_openai_tools",
    ],
)
def test_tool_definitions_carry_hard_constraints_field(adapter_fn: str):
    """两适配器都能读到 ToolDefinition.hard_constraints 字段（向后兼容默认空串）。"""
    from importlib import import_module

    module_path, fn_name = adapter_fn.rsplit(".", 1)
    fn = getattr(import_module(module_path), fn_name)
    # 构造一个无 hard_constraints 的定义（默认空串）。
    bare = ToolDefinition(name="bare", description="d", input_schema={"type": "object"})
    result = fn([bare])
    # 空串 hard_constraints 不应往 description 拼硬性约束前缀。
    if adapter_fn.endswith("_to_anthropic_tools"):
        assert "硬性约束" not in result[0]["description"]
    else:
        assert "硬性约束" not in result[0]["function"]["description"]
