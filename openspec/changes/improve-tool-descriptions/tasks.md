## 1. 修复 bash 路由指引 bug

- [x] 1.1 修改 `src/furflycode/tool/bash.py` 的 `hard_constraints()`：将字面 `grep_tool` 改为 `grep`（第 27 行），保持 `cat`/`grep`/`sed` 三词均在以兼容 `test_bash_has_hard_constraints`。
- [x] 1.2 在 `tests/test_system_prompt.py` 新增断言：`defs["bash"].hard_constraints` 不含字面 `grep_tool`。

## 2. 补齐四工具截断上限可见性（进 description）

- [x] 2.1 `read_file.py`：在 `description()` 中加入「最多 2000 行 / 256KB，超出尾部标注 `[truncated]`」，数字与 `_MAX_LINES=2000`/`_MAX_CHARS=256*1024` 严格一致。
- [x] 2.2 `bash.py`：在 `description()` 中加入「stdout/stderr 合计最多 10000 行 / 30000 字符，超出标注 `[truncated]`」，数字与 `_MAX_LINES=10000`/`_MAX_CHARS=30000` 一致。
- [x] 2.3 `glob_tool.py`：在 `description()` 中加入「最多返回 100 条匹配，超出标注 `[truncated]`」，与 `_MAX_RESULTS=100` 一致。
- [x] 2.4 `grep_tool.py`：在 `description()` 中加入「最多 100 条命中，超出标注 `[truncated]`；超长行（>1MB）跳过不搜」，与 `_MAX_HITS=100`/`_MAX_LINE_LEN` 一致。
- [x] 2.5 新增测试：四个工具的 `description()` 各含其截断上限关键词（2000/10000/100 等）。

## 3. 按准则 1 重写六个工具 description 与参数描述

- [x] 3.1 `read_file.py`：description 扩到 3-4 句，补「何时用」（查看文件内容）「何时不用」（改文件用 edit_file、列路径用 glob、搜内容用 grep）「关键限制」（截断、目录/不存在返回错误）；参数 `path` 补相对路径基准说明。
- [x] 3.2 `write_file.py`：description 补「何时用」（创建新文件或整体替换）「何时不用」（局部修改用 edit_file）；参数 `path`/`content` 补说明。
- [x] 3.3 `edit_file.py`：description 补「何时用」（局部精确修改）「何时不用」（整体重写用 write_file）「关键限制」（0/多匹配返回错误，须提供更长上下文）；参数三个补说明。
- [x] 3.4 `bash.py`：description 补「何时用」（运行测试/构建/git 等专用工具无法覆盖的操作）「何时不用」（读改文件用专用工具，见硬性约束）「关键限制」（超时、输出截断、非零退出按结果回灌非 is_error）；参数 `command` 补说明。
- [x] 3.5 `glob_tool.py`：description 补「何时用」（按模式找文件路径）「何时不用」（按内容找用 grep）「关键限制」（100 条上限、跨层级 `**` 支持）；参数 `pattern`/`path` 补说明。
- [x] 3.6 `grep_tool.py`：description 补「何时用」（按正则找文件内容）「何时不用」（按路径模式找用 glob）「关键限制」（100 命中上限、超长行跳过、二进制/无法解码文件跳过）；参数 `pattern`/`path`/`glob` 补说明。

## 4. 验证与回归

- [x] 4.1 `uv run ruff check src/ tests/` 与 `uv run ruff format src/ tests/` 通过。
- [x] 4.2 `uv run pytest tests/test_system_prompt.py tests/test_tool.py -q` 通过（重点复核 `test_bash_has_hard_constraints`、`test_read_only_tools_have_empty_or_no_constraints`、`test_anthropic_tools_concat_hard_constraints`、`test_openai_tools_concat_hard_constraints` 不破）。
- [x] 4.3 `uv run pytest -q` 全量通过（Windows 下 `PytestUnraisableExceptionWarning ... unclosed transport` 噪声可忽略，见 CLAUDE.md §6）。
- [x] 4.4 `uv run mypy src/` 通过。
- [x] 4.5 人工复核：打印 `new_default_registry().definitions()`，确认六个 description 数字与实现常量一致、`grep_tool` 字面已消失、只读工具 `hard_constraints` 仍为空串。
