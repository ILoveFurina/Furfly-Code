## Why

当前系统提示是 `prompt.py` 里一段单字符串 `SYSTEM_PROMPT`，由适配器原样塞进请求：Anthropic 当 `system` 字符串、OpenAI 当首条 system 消息。没有任何动静分离——每轮请求都对整段静态提示全额重算，且工具级硬约束（编辑前必先读、禁用原始终端命令）无处安放，只能漏掉或塞进全局提示造成双重强化。研究文档（`docs/deep_search/现代Agent提示词研究.md`）指出，这既浪费缓存经济性，又踩"过度规定"与"注意力陷阱"两大雷区。本次重构把系统提示升级为结构化、动静分离、单一事实来源的架构，并引入 FURFLY.md 项目规范主动预读注入，让 FurflyCode 从「能干活」变成「干得好」。

## What Changes

- 把单段 `SYSTEM_PROMPT` 按职责拆成七个固定模块（身份、系统约束、任务模式、动作执行、工具路由原则、语气风格、文本输出），在运行时按优先级拼装为静态系统提示。模块内容写「目标 + 边界 + 验证标准」，不写步骤流水线。
- **动静分离 + 双缓存断点**：Anthropic 适配器把拼装后的系统提示作为 `system` 字段的 text 块、末段挂 `cache_control: ephemeral`（断点①）；`tools` 顶层参数末个工具挂 `cache_control: ephemeral`（断点②）。环境信息、FURFLY.md 内容、对话历史、事件触发的注入全部走 `messages` 通道，绝不进 `system`/`tools`。
- **缓存机制双轨**：Anthropic 走显式 `cache_control` 严格前缀匹配；OpenAI 走隐式自动缓存（无显式断点），`cache_creation` 恒为 None，验收用 `cached_tokens > 0` 判定命中。agent 层保持协议无关，缓存形状差异在适配器边界收敛。
- **单一事实来源**：`ToolDefinition` 增加 `hard_constraints: str` 字段承载工具硬性约束（`EditFile` 编辑前必先 `read_file`、`BashTool` 禁用 `cat`/`grep`/`sed` 改用专用工具），适配器边界（`_to_anthropic_tools`/`_to_openai_tools`）把 `hard_constraints` 拼进 `description` 末尾。系统提示不再出现这些工具级规则字面，工具清单也不进系统提示（由 `tools` 参数单一承载）。
- **事件驱动注入**：用 `<system_reminder>` 标签包裹的 user 角色消息在运行中注入补充指令，追加于 `messages` 末尾。两触发条件：`CONTEXT_GROWTH`（消息深度 ≥8 回合，零依赖协议无关）、`TASK_BOUNDARY`（用户消息含模式关键词如 `/plan`/`/do`）。砍掉原设想的 `MODE_DEVIATION`——Plan Mode 工具子集隔离已物理阻断有害偏离。
- **FURFLY.md 加载器**（本次一步到位）：会话启动时从 cwd 逐级向上查找所有 `FURFLY.md`（到项目根/`.git` 为止），合并后用 `<furfly_md>` 标签包裹注入 `messages` 开头环境信息块。环境信息用 `<env_info>` 标签包裹同在 `messages` 开头。文件缺失/读取失败静默跳过，大文件截断标注。
- **缓存可观测性断言**：解析响应 `usage` 验证动静分离生效——Anthropic 第 1 轮 `creation>0, read=0`，第 2-N 轮 `creation=0, read≈第1轮 creation(±2%)`；OpenAI 降级断言 `cached_tokens` 第 2 轮起 >0。另备 5-6 个典型场景人工对比做定性评估。
- **Plan Mode 缓存代价点明**：模式切换会让 tools 数组从 6 个变 3 个，击穿 tools 缓存（一次 cache miss + rewrite），design 点明此代价，故 Plan Mode 不应频繁来回切。
- **BREAKING**：`ToolDefinition` 新增 `hard_constraints` 字段（有默认值，向后兼容）；`SYSTEM_PROMPT` 从单字符串改为模块化拼装产物，外部若直接引用该常量需适配。

## Capabilities

### New Capabilities

- `system-prompt-architecture`: 结构化系统提示架构——七模块拼装、动静分离双缓存断点、缓存机制双轨（Anthropic 显式 / OpenAI 隐式）、`hard_constraints` 单一事实来源、缓存可观测性断言。
- `context-injection`: 运行时上下文注入机制——`<system_reminder>` 事件驱动注入（`CONTEXT_GROWTH`/`TASK_BOUNDARY` 两触发）、FURFLY.md 加载器（项目内向上查找、主动预读、`<furfly_md>`/`<env_info>` 标签注入）。

### Modified Capabilities

- `chat-client`: 「发起对话请求」Requirement 改变——内置 system prompt 从单字符串改为七模块拼装产物并按协议挂缓存断点；环境信息与 FURFLY.md 内容由系统注入 `messages` 开头，conversation 层仍保持纯 user/assistant/tool 消息（注入由编排/适配器层负责）。
- `tool-system`: 「工具定义注入请求」Requirement 改变——`ToolDefinition` 增加 `hard_constraints` 字段，适配器边界拼进 `description`；工具级硬约束单一事实来源化，不再散落全局提示。

## Impact

- `src/furflycode/prompt.py`：从单段 `SYSTEM_PROMPT` 常量重构为七模块拼装函数/段落构建器，产出静态系统提示字符串。
- `src/furflycode/tool/__init__.py`：`ToolDefinition` 增加 `hard_constraints: str = ""` 字段；`Registry.definitions()`/`definitions_read_only()` 导出时携带该字段。
- `src/furflycode/tool/edit_file.py` + `bash.py`（+ 视情况其他工具）：各自声明 `hard_constraints`。
- `src/furflycode/llm/anthropic_provider.py`：`system` 从字符串改为 `[{text, cache_control: ephemeral}]`；`tools` 末个挂 `cache_control`；`_to_anthropic_tools` 拼接 `hard_constraints` 进 `description`。
- `src/furflycode/llm/openai_provider.py`：`_to_openai_tools` 拼接 `hard_constraints` 进 `description`；无显式缓存断点（隐式自动缓存）。
- 新增 `src/furflycode/context/`（或类似叶子模块）：FURFLY.md 加载器 + 环境信息组装 + 事件驱动注入判定，协议无关。
- `src/furflycode/agent/__init__.py`：在每轮请求前把环境信息/FURFLY.md 注入 `messages`、按触发条件追加 `<system_reminder>`；解析 `usage` 供可观测性。
- `src/furflycode/conversation.py` / `message.py`：可能新增承载注入消息的辅助（注入仍是 user 角色带标签文本，复用现有 `Message`）。
- `src/furflycode/cli.py`：启动时触发 FURFLY.md 加载器，把产物传入会话。
- 测试：缓存断言（mock usage）、`hard_constraints` 拼接、FURFLY.md 向上查找与合并、事件触发不重复、注入永远末尾追加。
