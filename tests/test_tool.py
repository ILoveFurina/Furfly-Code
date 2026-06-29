"""tool 包单测 — 注册中心与 6 个核心工具（AC1–AC6）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from furflycode.tool import Registry, new_default_registry
from furflycode.tool.bash import BashTool
from furflycode.tool.edit_file import EditFileTool
from furflycode.tool.glob_tool import GlobTool
from furflycode.tool.grep_tool import GrepTool
from furflycode.tool.read_file import ReadFileTool
from furflycode.tool.write_file import WriteFileTool


def _args(**kwargs: object) -> str:
    """用 json.dumps 安全构造工具参数（避免 Windows 路径反斜杠转义问题）。"""
    return json.dumps(kwargs)


# ────────────── 注册中心（AC1） ──────────────


def test_registry_definitions_six_ordered():
    """导出恰好 6 条工具定义且按注册顺序（AC1）。"""
    reg = new_default_registry()
    defs = reg.definitions()
    names = [d.name for d in defs]
    assert names == ["read_file", "write_file", "edit_file", "bash", "glob", "grep"]
    for d in defs:
        assert d.input_schema["type"] == "object"
        assert "properties" in d.input_schema


def test_registry_get_hit_and_miss():
    """按名查找命中/未命中。"""
    reg = new_default_registry()
    assert reg.get("read_file") is not None
    assert reg.get("nope") is None


def test_registry_duplicate_register_raises():
    """重名注册抛 ValueError。"""
    reg = Registry()
    reg.register(ReadFileTool())
    with pytest.raises(ValueError):
        reg.register(ReadFileTool())


# ────────────── read_file（AC2） ──────────────


async def test_read_file_with_line_numbers(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello\nworld\n", encoding="utf-8")
    r = await ReadFileTool().execute(_args(path=str(f)))
    assert not r.is_error
    assert r.content.splitlines()[0].startswith("     1\thello")


async def test_read_file_missing_is_error():
    r = await ReadFileTool().execute(_args(path="/no/such/file_xyz.txt"))
    assert r.is_error
    assert "不存在" in r.content


async def test_read_file_directory_is_error(tmp_path: Path):
    r = await ReadFileTool().execute(_args(path=str(tmp_path)))
    assert r.is_error
    assert "目录" in r.content


# ────────────── write_file（AC3） ──────────────


async def test_write_file_creates_nested(tmp_path: Path):
    f = tmp_path / "a" / "b" / "c.txt"
    r = await WriteFileTool().execute(_args(path=str(f), content="hi"))
    assert not r.is_error
    assert f.exists()
    assert f.read_text(encoding="utf-8") == "hi"


async def test_write_file_overrides(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_text("old", encoding="utf-8")
    await WriteFileTool().execute(_args(path=str(f), content="new"))
    assert f.read_text(encoding="utf-8") == "new"


# ────────────── edit_file（AC4） ──────────────


async def test_edit_file_unique_replace(tmp_path: Path):
    f = tmp_path / "e.txt"
    f.write_text("foo bar foo\n", encoding="utf-8")
    r = await EditFileTool().execute(
        _args(path=str(f), old_string="bar", new_string="baz")
    )
    assert not r.is_error
    assert f.read_text(encoding="utf-8") == "foo baz foo\n"


async def test_edit_file_no_match_distinguishable(tmp_path: Path):
    f = tmp_path / "e.txt"
    f.write_text("foo bar\n", encoding="utf-8")
    r = await EditFileTool().execute(
        _args(path=str(f), old_string="zzz", new_string="yyy")
    )
    assert r.is_error
    assert "未找到匹配" in r.content


async def test_edit_file_multiple_match_distinguishable(tmp_path: Path):
    f = tmp_path / "e.txt"
    f.write_text("foo foo foo\n", encoding="utf-8")
    r = await EditFileTool().execute(
        _args(path=str(f), old_string="foo", new_string="x")
    )
    assert r.is_error
    assert "3" in r.content
    assert "不唯一" in r.content
    # 三种情形文案互不相同
    assert r.content != "未找到匹配的内容"


# ────────────── bash（AC5/N1） ──────────────


async def test_bash_echo():
    r = await BashTool().execute('{"command":"echo hi"}')
    assert not r.is_error
    assert "hi" in r.content
    assert "exit_code: 0" in r.content


async def test_bash_timeout_via_registry():
    """注入极短超时跑 sleep，被超时终止并返回结构化错误。"""
    reg = Registry()
    reg.register(BashTool())
    r = await reg.execute("bash", '{"command":"sleep 5"}', timeout=0.5)
    assert r.is_error
    assert "超时" in r.content


# ────────────── glob / grep（AC6） ──────────────


async def test_glob_matches_py():
    r = await GlobTool().execute('{"pattern":"src/furflycode/tool/*.py"}')
    assert not r.is_error
    assert "read_file.py" in r.content


async def test_glob_no_match():
    r = await GlobTool().execute('{"pattern":"**/no_such_pattern_xyz.py"}')
    assert not r.is_error
    assert r.content == "无匹配"


async def test_grep_keyword_hit():
    r = await GrepTool().execute(
        '{"pattern":"DEFAULT_TIMEOUT","path":"src/furflycode/tool"}'
    )
    assert not r.is_error
    assert "DEFAULT_TIMEOUT" in r.content
    # file:line:content 形态
    assert r.content.splitlines()[0].count(":") >= 2


async def test_grep_bad_regex_is_error():
    r = await GrepTool().execute('{"pattern":"(unclosed","path":"."}')
    assert r.is_error
    assert "正则非法" in r.content
