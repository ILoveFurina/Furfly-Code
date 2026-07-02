## Context

`restructure-system-prompt` 已落地「工具级硬约束落在 `ToolDefinition.hard_constraints`，适配器边界拼进 `description` 末尾，系统提示不再重复」的单一事实来源架构。该架构正确，本次不改它。问题在内容层：六个工具的 `description()` 普遍仅 2 句，未达准则 1 的「3-4 句 + 何时用/何时不用/注意事项」；且 read_file/bash/glob/grep 的截断上限只存在于实现常量里，对模型不可见。另 `bash.hard_constraints` 引用了不存在的 `grep_tool`。

当前实现约束（须遵守）：
- `test_read_only_tools_have_empty_or_no_constraints`（`test_system_prompt.py:96-101`）锁死 read_file/glob/grep 的 `hard_constraints == ""`。
- `test_bash_has_hard_constraints`（`test_system_prompt.py:89-93`）断言 bash 的 hard_constraints 含 `cat`/`grep`/`sed` 三词。
- 适配器拼接格式固定：`{description}\n\n硬性约束：{hard_constraints}`（`anthropic_provider.py:40` / `openai_provider.py:36`）。

## Goals / Non-Goals

**Goals:**
- 模型能从工具描述得知每个工具的截断上限，遇到 `[truncated]` 时能正确推断后续动作。
- `bash` 的路由指引指向真实存在的工具名。
- 六个工具描述达到准则 1 的详细度（功能/何时用/何时不用/关键限制）。
- 改动不破坏 `test_system_prompt.py` 现有断言。

**Non-Goals:**
- 不改工具执行行为、`Result` 形状、截断常量值。
- 不改 `hard_constraints` 架构与适配器拼接逻辑。
- 不统一工具命名空间（`read_file` vs `bash` 风格混用）——规模小且改名会破坏 Anthropic 缓存断点稳定性，留待接入远程工具时再议。
- 不引入 `input_examples`——六个工具均为扁平字符串参数，描述里举例已足够。

## Decisions

### D1：截断上限进 `description()`，不进 `hard_constraints`

**决策**：read_file/bash/glob/grep 的截断上限写进各自 `description()` 文本，不新增 `hard_constraints`。

**理由**：
- `hard_constraints` 语义是「工具级硬性规则/禁令」（如「编辑前必先读」「禁用 cat」），由 `test_read_only_tools_have_empty_or_no_constraints` 锁定只读工具为空串。截断上限是「能力说明」而非「禁令」，塞进 `hard_constraints` 既破坏该测试，也混淆语义。
- 截断上限属于「工具不会返回什么信息」的注意事项，正是准则 1 要求写进描述的内容。
- 适配器拼接格式 `{description}\n\n硬性约束：{hard_constraints}` 不变，模型最终看到的完整 description 自然包含截断说明。

**备选（否决）**：把截断上限塞进 `hard_constraints` 并放宽只读工具测试——语义错位且改动面更大。

### D2：`grep_tool` → `grep` 仅修 `bash.hard_constraints` 文案

**决策**：只改 `bash.py:27` 的字面 `grep_tool` 为 `grep`，不动 `GrepTool.name()`（已是 `grep`）、不动文件名 `grep_tool.py`、不动测试导入路径 `from furflycode.tool.grep_tool import GrepTool`。

**理由**：bug 在「给模型看的指引文案」里引用了错误工具名，修这一处即可让路由生效。文件名/类名/导入路径是工程内部标识，模型看不到，改名只增加 churn 并破坏缓存，无收益。

**备选（否决）**：把 `grep_tool.py` 文件改名为 `grep.py`——纯 churn，破坏 git 历史与测试导入。

### D3：描述重写遵循「功能 / 何时用 / 何时不用 / 关键限制」四段式

**决策**：每个工具 `description()` 至少覆盖四要素，3-4 句起步；复杂工具（bash/grep）可更多。不写步骤流水线（与 `prompt.py` 模块风格一致：写「目标 + 边界 + 验证标准」不写 how-to）。

**理由**：准则 1 明确「最重要的因素是描述详细度」，且要求包含「何时应使用以及何时不应使用」「重要的注意事项或限制」。

**备选（否决）**：仅补截断上限、不重写其余文案——达不到准则 1 的详细度，且「何时不用」边界缺失会让模型在 read_file vs grep vs glob 之间选择困难。

### D4：参数 `description` 同步润色

**决策**：重写工具描述时一并润色各参数的 `description` 字段，补「取值含义/默认值/对行为的影响」。

**理由**：准则 1 要求「每个参数的含义以及它如何影响工具的行为」。现状参数描述多为 5-8 字（如「要读取的文件路径」），未说明相对路径基准、默认值等。

## Risks / Trade-offs

- **[描述变长增加 prompt token]** → 六个工具 description 总计增加约 200-400 token，挂在 Anthropic 工具 Schema 缓存断点②之后属静态区域，首次请求后命中缓存，边际成本极低。收益（模型路由正确率 + 截断后续动作正确率）远大于此。
- **[重写文案可能引入新的工具名笔误]** → 实现后新增断言：bash 的 hard_constraints 不含字面 `grep_tool`；grep/glob/read_file/bash 的 description 含各自截断上限关键词。用测试兜住。
- **[描述与实际行为漂移]** → 截断常量（`_MAX_LINES` 等）与描述里的数字必须一致，tasks 里要求实现时双重核对。未来若调常量须同步改描述——在 `tool/__init__.py` 的 `ToolDefinition` docstring 补一句提示。
- **[不统一命名空间留技术债]** → 当前 6 个工具单服务，混用可接受；接入 MCP/远程工具时需统一前缀。记入 Non-Goals 显式承债。
