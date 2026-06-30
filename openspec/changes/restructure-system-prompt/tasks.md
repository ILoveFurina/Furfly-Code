# Implementation Tasks

按依赖自底向上：叶子数据结构 → prompt 模块化 → 工具 hard_constraints → 适配器缓存与拼接 → FURFLY.md 加载器与注入模块 → agent 编排接入 → cli 接线 → 测试 → 验收。引用 spec（`specs/system-prompt-architecture`、`specs/context-injection`、`specs/chat-client`、`specs/tool-system`）与 design（D1–D8）。

## 1. 叶子数据结构

- [x] 1.1 在 `src/furflycode/tool/__init__.py` 的 `ToolDefinition` 增加 `hard_constraints: str = ""` 字段（默认空串，向后兼容），更新 docstring。
- [x] 1.2 `Registry.definitions()` 与 `definitions_read_only()` 导出 `ToolDefinition` 时携带各工具的 `hard_constraints`（调用 `tool.hard_constraints()` 或在工具类暴露该属性——按现有 `description()`/`parameters()` 模式新增 `hard_constraints()` 抽象方法或属性，与既有抽象一致）。

## 2. 工具硬约束声明

- [x] 2.1 `src/furflycode/tool/edit_file.py`：声明硬约束「编辑前必须先调用 read_file 读取该文件，禁止凭记忆编辑」。
- [x] 2.2 `src/furflycode/tool/bash.py`：声明硬约束「禁止用 cat/grep/sed 等原始终端命令读取或编辑文件，改用专用工具 read_file/grep_tool/edit_file」。
- [x] 2.3 视情况给 `write_file`/`read_file`/`glob_tool`/`grep_tool` 声明各自 `hard_constraints`（无强约束则留空串）。

## 3. 系统提示模块化拼装

- [x] 3.1 重构 `src/furflycode/prompt.py`：从单段 `SYSTEM_PROMPT` 常量改为七模块段落构建器（身份、系统约束、任务模式、动作执行、工具路由原则、语气风格、文本输出），各模块内容写「目标 + 边界 + 验证标准」，不写步骤流水线（D1 去规定化）。
- [x] 3.2 实现拼装函数按固定优先级顺序合并七模块为单一静态系统提示字符串，模块间空行分隔，产出确定性（无随机/时间戳）。
- [x] 3.3 「工具路由原则」模块只放跨工具路由哲学（如「优先用专用工具而非 bash」「文件编辑类操作走专用工具」），绝不列举工具名或摘要清单（D3）。
- [x] 3.4 「系统约束」模块含 FURFLY.md 入口说明（告知模型项目规范已在 `<furfly_md>` 标签内提供，应遵守）。

## 4. 适配器缓存与硬约束拼接

- [x] 4.1 `src/furflycode/llm/anthropic_provider.py`：`system` 从字符串改为 `[{type:"text", text:<七模块拼装>, cache_control:{type:"ephemeral"}}]`（断点①，D1/D2）。
- [x] 4.2 `src/furflycode/llm/anthropic_provider.py`：`tools` 数组末个工具挂 `cache_control:{type:"ephemeral"}`（断点②）。
- [x] 4.3 `src/furflycode/llm/anthropic_provider.py`：`_to_anthropic_tools` 把 `hard_constraints` 拼进 `description` 末尾（如 `description + "\n\n硬性约束：" + hard_constraints`，D4）。
- [x] 4.4 `src/furflycode/llm/openai_provider.py`：`_to_openai_tools` 把 `hard_constraints` 拼进 `description` 末尾；不设显式 `cache_control`（隐式自动缓存，D1）。
- [x] 4.5 验证 `prompt.py` 拼装函数的调用点替换原 `SYSTEM_PROMPT` 常量引用（两适配器 + 任何外部引用）。

## 5. FURFLY.md 加载器与注入模块（叶子层）

- [x] 5.1 新增 `src/furflycode/context/`（或合适叶子模块），实现 FURFLY.md 加载器：从 cwd 逐级向上查找 `FURFLY.md` 至项目根（含 `.git` 的目录）为止，协议无关、不 import anthropic/openai（D7）。
- [x] 5.2 合并策略：叠加全部找到的内容，就近（更靠近 cwd）内容排列在后；文件缺失/读取失败静默跳过不抛异常；大文件截断标注（上限 ~8K chars，复用 `_truncate` 或对齐其参数）。
- [x] 5.3 实现环境信息组装：cwd、平台、规范文件路径，用 `<env_info>...</env_info>` 包裹；FURFLY.md 合并内容用 `<furfly_md>...</furfly_md>` 包裹。
- [x] 5.4 暴露一次性预读入口（会话启动时调用，会话期间不重读），产出注入用的消息内容字符串。

## 6. agent 编排接入注入与可观测性

- [x] 6.1 在 `src/furflycode/agent/__init__.py`（或编排层合适位置）每轮请求前确保环境信息与 FURFLY.md 内容位于 `messages` 开头（首轮注入，后续轮复用同一快照不重读）。
- [x] 6.2 实现事件驱动注入判定：`CONTEXT_GROWTH`（消息深度 ≥8 回合，基于 `Conversation` 消息条数，零依赖）、`TASK_BOUNDARY`（用户消息含 `/plan`/`/do` 等关键词）；带已触发标记保证同一事件不重复触发（D5）。
- [x] 6.3 注入消息以 `<system_reminder>` 包裹、user 角色、追加于 `messages` 末尾（绝不中间插入，D5）；不实现 `MODE_DEVIATION`。
- [x] 6.4 解析每轮 `Usage` 的 `cache_read_tokens`/`cache_creation_tokens` 供可观测性断言（D8）：Anthropic 首轮 `creation>0, read=0`，第 2-N 轮 `creation=0, read≈首轮 creation(±2%)`；OpenAI 降级判 `cached_tokens>0`。断言可作为测试钩子或日志，不阻断正常运行。

## 7. cli 接线

- [x] 7.1 `src/furflycode/cli.py`：启动时触发 FURFLY.md 加载器预读，把产物（环境信息 + FURFLY.md 内容）传入会话/agent，供首轮注入。

## 8. 测试

- [x] 8.1 单测：七模块按固定顺序拼装、模块间空行分隔、内容去规定化（不含步骤流水线字样）。
- [x] 8.2 单测：`hard_constraints` 拼进两适配器的工具 `description` 末尾；拼装后 system prompt 不含工具级硬约束字面与工具清单。
- [x] 8.3 单测：Anthropic 请求 `system` 为带 `cache_control` 的 text 块、`tools` 末个挂 `cache_control`；OpenAI 请求无 `cache_control` 字段。
- [x] 8.4 单测：FURFLY.md 加载器向上查找至 `.git` 项目根、多份叠加就近在后、缺失静默跳过、大文件截断标注、会话期间不重读。
- [x] 8.5 单测：环境信息与 FURFLY.md 内容以 `<env_info>`/`<furfly_md>` 包裹位于 `messages` 开头，不进 `system`/`tools`。
- [x] 8.6 单测：`CONTEXT_GROWTH` 在 ≥8 回合触发且基于消息条数（无 tokenizer 依赖）、`TASK_BOUNDARY` 按关键词触发、同一事件不重复触发、注入永远末尾追加。
- [x] 8.7 单测：缓存可观测性断言——mock Anthropic usage 满足首轮写入/后续命中（±2%）；OpenAI 降级 `cached_tokens>0`；前缀变动时检出 read 骤降偏离。
- [x] 8.8 单测：Plan Mode 模式切换时 tools 数组变化导致缓存失效的代价被体现（tools 断点 miss）；Plan Mode 不升级子代理。
- [x] 8.9 集成测：端到端多轮对话中静态前缀缓存命中、环境/FURFLY.md 注入正确、事件触发注入不击穿 system 缓存。

## 9. 验收

- [x] 9.1 `uv run ruff check src/ tests/` 与 `uv run ruff format --check src/ tests/` 通过。
- [x] 9.2 `uv run mypy src/` 通过（0 错误，注意 `ToolDefinition` 新字段与重复声明 no-redef 陷阱）。
- [x] 9.3 `uv run pytest` 全过（忽略 Windows unclosed transport 噪声）。
- [x] 9.4 准备 5-6 个典型场景人工对比定性评估（工具路由是否正确、注入是否末尾、模式切换代价、FURFLY.md 是否生效、缓存是否命中）。
