## Why

工具描述质量未达到「工具定义最佳实践」准则。两个硬伤已影响模型正确路由：① `bash` 的 `hard_constraints` 引用了不存在的工具名 `grep_tool`（实际工具名是 `grep`），模型按指引调用会收到「未知工具」；② 四个工具（read_file/bash/glob/grep）有截断上限但描述里从未提及，模型读到 `[truncated]` 尾注时无法正确推断「需要缩小范围或翻页重读」，易误以为已读到全部内容。其余工具描述普遍不足准则要求的 3-4 句，缺少「何时用 / 何时不用 / 注意事项」边界。

## What Changes

- **修 bug**：`bash` 的 `hard_constraints` 中 `grep_tool` → `grep`，使工具路由指引指向真实存在的工具。
- **补可见性**：把 read_file（2000 行 / 256KB）、bash（10000 行 / 30000 字符）、glob（100 条）、grep（100 命中）的截断上限写进各自 `description()`，让模型知道返回可能不完整。
- **重写描述**：按准则 1 把六个工具的 `description()` 扩到 3-4 句以上，补齐「功能 / 何时用 / 何时不用 / 关键限制」；同步润色各参数 `description`。
- **不动**：不改工具执行行为、不改 `Result` 形状、不改 `hard_constraints` 架构（单一事实来源 + 适配器边界拼接，由 `restructure-system-prompt` 已落地）、不改工具名、不改 `is_read_only` 归属。

## Capabilities

### New Capabilities
<!-- 无新能力 -->

### Modified Capabilities
<!-- 本次为工具描述质量修补，不改变 spec 级需求。
     tool-system spec 已要求「大文件/长输出 MUST 截断并标注 [truncated]」（第 191 行），
     但未要求「描述里告知模型截断上限」——后者属实现细节增强，不构成 spec delta。
     grep_tool→grep 为文案 bug 修复，不改 spec 行为。故无 Modified Capabilities。 -->

## Impact

- **代码**：`src/furflycode/tool/` 下 read_file / write_file / edit_file / bash / glob_tool / grep_tool 六个文件的 `description()` 与 `parameters()` 文案；`bash.py` 的 `hard_constraints()` 文案修一处工具名。
- **测试**：`tests/test_system_prompt.py` 现有断言需复核——`test_bash_has_hard_constraints` 仅断言 `cat`/`grep`/`sed` 三词存在，修 `grep_tool`→`grep` 不破；`test_read_only_tools_have_empty_or_no_constraints` 锁死 read_file/glob/grep 的 `hard_constraints == ""`，截断上限须进 `description()` 而非 `hard_constraints`，此约束不变。新增描述内容断言（截断上限可见、`grep_tool` 字面消失）。
- **API/依赖**：无。工具名、Schema 形状、`ToolDefinition` 字段均不变，对 `agent`/`llm` 适配器零影响。
