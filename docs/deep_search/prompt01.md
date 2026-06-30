# 系统提示词架构重构 propose 提示词

## 目标

把原来单段的 `SYSTEM_PROMPT` 展开成结构化、动静分离的系统提示架构：稳定指令走缓存通道省钱省时间，环境信息与动态指令走消息通道注入，FURFLY.md 项目规范由加载器主动预读注入。让 FurflyCode 从「能干活」变成「干得好」。

## 技术要求

- 全局指令按职责拆成模块（身份、系统约束、任务模式、动作执行、工具路由原则、语气风格、文本输出），按优先级拼装，方便以后插新模块。模块内容写「目标 + 边界 + 验证标准」，不写步骤流水线（避免过度规定触发注意力稀释）。代码规范不进系统提示，由 FURFLY.md 加载器按需注入。
- 严格动静分离，两个缓存断点：
  - 断点①：`system` 字段末段挂 `cache_control: ephemeral` —— 七模块拼装的静态系统提示。
  - 断点②：`tools` 顶层参数末个挂 `cache_control: ephemeral` —— 5 个工具完整 Schema。
  - 注意 `tools` 是 Anthropic API 的独立顶层参数，不在 `system` 内。
  - 消息通道（`messages` 数组）：环境信息、FURFLY.md 内容、对话历史、事件触发的注入。
- 缓存机制双轨：
  - Anthropic 走显式 `cache_control`（上述两断点），严格前缀匹配。
  - OpenAI 走隐式自动缓存（无显式断点），`cache_creation` 字段恒为 None，验收用 `cached_tokens > 0` 判定命中。
  - 适配器边界按协议各自处理，agent 层保持协议无关。
- 单一事实来源：每条规则只在最相关的地方说一次。
  - `ToolDefinition` 增加 `hard_constraints: str` 字段，承载该工具的硬性约束（如 `EditFile` 的「编辑前必须先调用 `read_file` 读取该文件」、`BashTool` 的「禁止用 `cat`/`grep`/`sed` 等原始终端命令读取或编辑文件，改用专用工具」）。
  - 适配器边界（`_to_anthropic_tools` / `_to_openai_tools`）把 `hard_constraints` 拼进 `description` 末尾。
  - 系统提示里不再出现这些工具级规则的字面。
  - 系统提示的「工具路由原则」模块只放跨工具的路由哲学（如「优先用专用工具而非 bash」），绝不列举工具清单 —— 工具清单由 `tools` 参数单一承载，避免双重强化。
- 用 `<system_reminder>...</system_reminder>` 包裹的 user 角色消息在运行中注入补充指令，放进 `messages` 末尾（不污染 `system`/`tools` 缓存区，绝不中间插入）。模型通过 XML 标签识别其系统意图。
- 事件驱动注入，两触发条件（砍掉 `MODE_DEVIATION`，因 Plan Mode 工具子集隔离已物理阻断有害偏离）：
  - `CONTEXT_GROWTH` —— 消息深度跨过阈值（≥8 个 user/assistant/tool 回合），零依赖协议无关，不用 token 计数。
  - `TASK_BOUNDARY` —— 用户消息含模式关键词（如 `/plan`、`/do`）。
  - 同一事件不重复触发。Plan Mode 不升级为子代理（已确认延后），靠首轮一次强提示 + 只读工具子集隔离维持；模式切换会击穿 tools 缓存（一次 cache miss + rewrite），design 点明此代价，故 Plan Mode 不应频繁来回切。
- 解析响应 `usage` 做缓存可观测性断言（仅 Anthropic 路径严格成立）：
  - 第 1 轮 `cache_creation_input_tokens > 0`，`cache_read_input_tokens = 0`。
  - 第 2-N 轮 `cache_creation_input_tokens = 0`，`cache_read_input_tokens ≈ 第 1 轮 cache_creation_input_tokens`（±2%）。
  - 严格动静分离预期下 read 跨轮稳定，误差留 2% 余量；实测漂移 >2% 是有用的动静分离漏点信号。
  - OpenAI 路径降级断言：`cached_tokens` 第 2 轮起 > 0 即视为隐式缓存命中。
  - 再准备 5-6 个典型场景做人工对比当定性评估。
- FURFLY.md 加载器本次做完整（一步到位）：
  - 会话启动时从 cwd 逐级向上查找所有 `FURFLY.md`（到项目根 / `.git` 为止），合并后用 `<furfly_md>...</furfly_md>` 标签包裹注入 `messages` 开头环境信息块（不进 `system` 缓存区，保核心提示跨项目纯净）。
  - 叠加全部、就近内容排列在后（让模型先看全局再看局部）。
  - 文件缺失 / 读取失败静默跳过不阻断启动；大文件截断标注。
  - 加载器协议无关、放叶子层，会话期间不重读。
  - 环境信息（工作目录、平台、规范文件路径）用 `<env_info>` 标签包裹，与 FURFLY.md 内容同在 `messages` 开头。

## 这一步先不做

自动记忆、真实 MCP 接入、自动化评估、全局用户级 FURFLY.md（`~/.furfly/`）分层。

## 系统提示结构

```text
┌─ 缓存区① system 字段 ───────────────────────────────────────┐
│ [身份]                                                      │
│ [系统约束]  ← 含 FURFLY.md 入口说明                          │
│ [任务模式]                                                  │
│ [动作执行]                                                  │
│ [工具路由原则]  ← 只放跨工具原则，不列工具清单               │
│ [语气风格]                                                  │
│ [文本输出]                                                  │
│ ─── cache_control: ephemeral ─── ← 断点①                  │
└──────────────────────────────────────────────────────────────┘
┌─ 缓存区② tools 顶层参数（Anthropic 独立参数）──────────────┐
│ [ToolDefinition × 5                                         │
│   name + description + input_schema]                        │
│   ← hard_constraints 在适配器边界拼进 description           │
│ ─── 末个挂 cache_control: ephemeral ─── ← 断点②           │
└──────────────────────────────────────────────────────────────┘
┌─ 消息通道 messages 数组 ────────────────────────────────────┐
│ [<env_info> 工作目录/平台/规范文件路径 </env_info>]         │
│ [<furfly_md> 合并后的项目规范内容 </furfly_md>]             │
│ [用户消息]                                                  │
│ [助手消息]                                                  │
│ [工具结果]                                                  │
│ [事件触发的 <system_reminder> 注入]  ← 仅触发时末尾追加     │
└──────────────────────────────────────────────────────────────┘
```
