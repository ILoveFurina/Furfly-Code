## ADDED Requirements

### Requirement: 系统提示模块化拼装

系统 SHALL 将内置系统提示按职责拆分为七个固定模块（身份、系统约束、任务模式、动作执行、工具路由原则、语气风格、文本输出），在运行时按该固定优先级顺序拼装为单一静态系统提示字符串。模块内容 MUST 以「目标 + 边界 + 验证标准」形式表述，MUST NOT 包含步骤流水线式指令（如「先解析、再分析、最后输出」）。

#### Scenario: 七模块按固定顺序拼装

- **WHEN** 系统构造请求的系统提示
- **THEN** 产出的静态系统提示字符串 SHALL 包含全部七个模块，且按「身份 → 系统约束 → 任务模式 → 动作执行 → 工具路由原则 → 语气风格 → 文本输出」顺序排列，模块间以空行分隔

#### Scenario: 模块内容去规定化

- **WHEN** 审查任一模块文本
- **THEN** 该模块 SHALL 描述目标、系统边界与验证标准，MUST NOT 规定模型内部推理的固定步骤流水线

### Requirement: 动静分离与双缓存断点

系统 SHALL 严格分离静态内容与动态内容。静态系统提示（七模块拼装产物）与工具完整 Schema 走缓存通道，环境信息、FURFLY.md 内容、对话历史、事件触发的注入走消息通道（`messages` 数组）。Anthropic 协议下 MUST 设置两个缓存断点：断点①为 `system` 字段末段挂 `cache_control: ephemeral`，断点②为 `tools` 顶层参数末个工具挂 `cache_control: ephemeral`。`tools` 是 Anthropic API 的独立顶层参数，MUST NOT 被塞进 `system`。动态内容 MUST NOT 进入 `system` 或 `tools` 缓存区。

#### Scenario: Anthropic 请求挂两个缓存断点

- **WHEN** 以 Anthropic 协议发起请求
- **THEN** `system` 字段为含 `cache_control: {type: ephemeral}` 的 text 块，`tools` 数组末个工具挂 `cache_control: {type: ephemeral}`，且两个断点分别覆盖系统提示与工具 Schema 两个独立区域

#### Scenario: 动态内容不污染缓存区

- **WHEN** 工作目录、平台、FURFLY.md 内容、对话历史、事件触发的注入等动态内容被组装进请求
- **THEN** 这些内容 SHALL 全部位于 `messages` 数组，`system` 字段与 `tools` 参数中 MUST NOT 出现任何随会话或环境变化的内容

#### Scenario: 静态前缀确定性

- **WHEN** 同一会话连续发起多轮请求
- **THEN** `system` 字段与 `tools` 参数的字节序列在轮次间 MUST 保持完全一致（无随机串、无时间戳、无键序翻转），以维持缓存前缀哈希稳定

### Requirement: 缓存机制双轨

系统 SHALL 按协议分别处理缓存机制，agent 层保持协议无关。Anthropic 协议走显式 `cache_control` 断点（严格前缀匹配）；OpenAI 协议走隐式自动缓存（无显式断点，`cache_creation` 字段恒为 None）。缓存形状差异 MUST 在适配器边界收敛，agent 编排层 MUST NOT 直接依赖任一协议的缓存机制。

#### Scenario: OpenAI 路径无显式缓存断点

- **WHEN** 以 OpenAI 协议发起请求
- **THEN** 请求中 MUST NOT 包含 `cache_control` 字段，依赖端点隐式自动缓存，且解析的 `cache_creation_tokens` 恒为 None

#### Scenario: agent 层协议无关

- **WHEN** agent 编排层组装请求与解析用量
- **THEN** agent 层 SHALL 仅依赖协议无关的 `Usage` 抽象，MUST NOT import 或直接依赖 anthropic/openai 的缓存 API

### Requirement: 工具硬约束单一事实来源

系统 SHALL 将工具级硬约束集中在该工具的 `hard_constraints` 字段，作为单一事实来源。`ToolDefinition` MUST 提供 `hard_constraints` 字段承载该工具的硬性约束（如「编辑前必须先调用 read_file 读取该文件」「禁止用 cat/grep/sed 等原始终端命令，改用专用工具」）。适配器边界 MUST 将 `hard_constraints` 拼接进发往模型的 `description` 末尾。系统提示的「工具路由原则」模块 MUST ONLY 包含跨工具的路由哲学，MUST NOT 列举工具名或工具摘要清单——工具清单由 `tools` 参数单一承载。

#### Scenario: 硬约束拼进工具 description

- **WHEN** 适配器将 `ToolDefinition` 转为协议特定工具参数
- **THEN** 导出的工具 `description` 末尾 SHALL 包含该工具的 `hard_constraints` 内容

#### Scenario: 系统提示不含工具级规则字面与工具清单

- **WHEN** 审查拼装后的静态系统提示
- **THEN** 提示文本中 MUST NOT 出现任一工具的硬约束字面（如「编辑前必先读」「禁用 cat」），MUST NOT 列举工具名或工具摘要清单；「工具路由原则」模块 SHALL 仅含跨工具路由哲学（如「优先用专用工具而非 bash」）

### Requirement: 缓存可观测性断言

系统 SHALL 解析响应 `usage` 验证动静分离与缓存生效。Anthropic 协议下：第 1 轮 MUST 满足 `cache_creation_input_tokens > 0` 且 `cache_read_input_tokens = 0`；第 2 轮及以后 MUST 满足 `cache_creation_input_tokens = 0` 且 `cache_read_input_tokens ≈ 第 1 轮 cache_creation_input_tokens`（±2% 误差内）。OpenAI 协议下降级断言：第 2 轮及以后 `cached_tokens > 0` 即视为隐式缓存命中。严格动静分离预期下 `cache_read` 跨轮稳定；实测漂移超过 2% SHALL 视为动静分离漏点信号。

#### Scenario: Anthropic 首轮写入后续命中

- **WHEN** 以 Anthropic 协议在同一会话连续发起首轮与第 2 轮请求
- **THEN** 首轮 `cache_creation_input_tokens > 0` 且 `cache_read_input_tokens = 0`；第 2 轮 `cache_creation_input_tokens = 0` 且 `cache_read_input_tokens` 在第 1 轮 `cache_creation_input_tokens` 的 ±2% 内

#### Scenario: OpenAI 隐式缓存命中降级断言

- **WHEN** 以 OpenAI 协议在同一会话连续发起首轮与第 2 轮请求
- **THEN** 第 2 轮及以后解析的 `cached_tokens > 0` 即视为隐式缓存命中，不卡 `cache_creation` 字段

#### Scenario: 缓存击穿被可观测性暴露

- **WHEN** 动静分离被破坏导致前缀变动（如动态内容混入 system）
- **THEN** 可观测性断言 SHALL 检出 `cache_read_input_tokens` 骤降偏离第 1 轮 `cache_creation_input_tokens` 超过 2%，作为漏点信号
