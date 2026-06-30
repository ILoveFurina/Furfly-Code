## Context

FurflyCode 当前系统提示是 `prompt.py` 里一段单字符串 `SYSTEM_PROMPT`，由两个适配器原样注入：Anthropic 当 `system` 字符串、OpenAI 当首条 system 消息。每轮请求对整段静态提示全额重算，工具级硬约束无处安放。研究文档（`docs/deep_search/现代Agent提示词研究.md`）系统论证了三大问题：

1. **过度规定**——步骤流水线式指令会劣化现代模型（Fable 5 / Opus 4.8）输出，触发注意力稀释与 `reasoning_extraction` 拒答。
2. **缓存物理约束**——Anthropic 提示词缓存是严格前缀匹配，动静不分则每轮击穿；合理运用可降 41%-80% 成本、缩 13%-31% TTFT。
3. **双重强化注意力陷阱**——同一规则在全局提示与工具描述里重复表述，反而让模型注意力偏离、产生幻觉或神经质过度反应。

现有架构已铺好基础设施：`Usage` 带了 `cache_read_tokens`/`cache_creation_tokens`、`is_read_only()` 给 Plan Mode 工具子集物理隔离、适配器边界模式天然支持 system 形状分叉。本次重构在此基础上完成动静分离、单一事实来源、事件驱动注入与 FURFLY.md 加载器。

## Goals / Non-Goals

**Goals:**

- 系统提示结构化为七模块拼装，模块内容写「目标 + 边界 + 验证标准」而非步骤流水线。
- 严格动静分离：静态系统提示 + 工具 Schema 走缓存通道（Anthropic 双断点），环境信息/FURFLY.md/对话历史/注入走消息通道。
- 单一事实来源：工具硬约束落在 `ToolDefinition.hard_constraints`，适配器边界拼进 `description`，全局提示不再重复。
- 事件驱动注入：`<system_reminder>` 末尾追加，两触发条件，砍掉冗余的 `MODE_DEVIATION`。
- FURFLY.md 加载器一步到位：项目内向上查找、主动预读、标签注入。
- 缓存可观测性：解析 `usage` 断言动静分离生效。

**Non-Goals:**

- 自动记忆、真实 MCP 接入、自动化评估。
- 全局用户级 FURFLY.md（`~/.furfly/`）分层——本次仅项目内向上查找。
- Plan Mode 升级为子代理隔离——已确认延后，靠首轮强提示 + 工具子集隔离维持。
- 真实 token 计数（tiktoken / Anthropic count_tokens API）——`CONTEXT_GROWTH` 用消息条数触发，零依赖协议无关。
- 上下文压缩 / 自动截断历史。

## Decisions

### D1. 缓存双轨：Anthropic 显式断点 vs OpenAI 隐式自动缓存

`cache_control: ephemeral` 是 Anthropic 专属机制。OpenAI 是隐式自动缓存（前缀达阈值自动缓存，无显式断点），且 `cache_creation` 字段恒为 None。

- **Anthropic 路径**：`system` 改为 `[{type:"text", text:<七模块拼装>, cache_control:{type:"ephemeral"}}]`（断点①）；`tools` 数组末个工具挂 `cache_control:{type:"ephemeral"}`（断点②）。两断点覆盖两个独立可缓存区域（Anthropic 允许最多 4 个断点）。
- **OpenAI 路径**：`system` 仍为首条 system 消息（字符串），无 `cache_control`；依赖隐式自动缓存。验收降级为 `cached_tokens > 0`。
- **agent 层协议无关**：缓存形状差异在适配器边界收敛，agent 不感知协议。

**为何不统一**：两协议机制本质不同，强行统一会丢失 Anthropic 显式断点的精确控制。双轨各自最优，agent 层只依赖 `Usage` 抽象。

**备选（否决）**：在 system 里塞一个动态 UUID 击穿缓存当基线对照——那是反模式，不是生产策略。

### D2. tools 是独立顶层参数，断点 2 个不是 1 个

Anthropic API 中 `tools` 是与 `system`/`messages` 平级的独立顶层参数，**不在 system 内**。研究文档"唯一断点"是简化表述。工程上 system 与 tools 是两个独立可缓存区域，各打一个断点才把静态前缀全覆盖：只打 1 个要么 system 缓存了 tools 没缓存（每轮重算 5 个 schema），要么反过来。

### D3. 砍掉系统提示里的工具清单模块，只留跨工具路由原则

模型从 `tools` 参数看到完整 `name + description + input_schema`。若 system 再列一份工具清单 = 同一信息两处说，正是研究文档反对的双重强化。

- 系统提示的「工具路由原则」模块**只放跨工具哲学**（如「优先用专用工具而非 bash」「文件编辑类操作走专用工具」），**绝不列举工具名/摘要清单**。
- 工具清单由 `tools` 参数单一承载。

**备选（否决）**：保留工具清单模块放「名称 + 一句话摘要」——仍构成双重强化，砍。

### D4. hard_constraints 落 ToolDefinition 新字段，适配器边界拼进 description

`ToolDefinition` 只有 `name/description/input_schema`，`input_schema` 是标准 JSON Schema——塞非标准 `hard_constraints` 字段进去模型可能忽略、Anthropic 校验可能报错。

- `ToolDefinition` 增加 `hard_constraints: str = ""` 字段（有默认值，向后兼容）。
- 适配器边界 `_to_anthropic_tools`/`_to_openai_tools` 把 `hard_constraints` 拼进 `description` 末尾（如 `description + "\n\n硬性约束：" + hard_constraints`）。
- 落标准字段、协议无关、单一事实来源。

**备选（否决）**：写进 `input_schema` 的非标准字段——风险高；纯写进 `description` 不加字段——则约束与用途描述混在一处，难维护。新字段 + 边界拼接最干净。

### D5. 事件驱动注入：两触发，砍 MODE_DEVIATION，末尾追加

- `CONTEXT_GROWTH`：消息深度 ≥8 个 user/assistant/tool 回合时触发。**用消息条数而非 token 计数**——零依赖、协议无关，避免重度工具场景（一次 read_file 大文件就破 10K）过早触发撞研究文档警告的"高频唤醒让模型进入防御姿态"。
- `TASK_BOUNDARY`：用户消息含模式关键词（`/plan`、`/do`）时触发。
- **砍 `MODE_DEVIATION`**：Plan Mode 工具子集隔离（`definitions_read_only()` 只给 3 个只读工具，`edit_file`/`write_file`/`bash` 物理拿不到）已阻断有害偏离；"输出含代码块"检测易误判且治无害行为（模型描述方案贴代码引用是合理的）。
- 同一事件不重复触发（带已触发标记）。
- `<system_reminder>` **永远追加于 messages 末尾**，绝不中间插入——否则击穿 messages 自动阈值缓存。

### D6. Plan Mode 切换击穿 tools 缓存——点明代价

`agent/__init__.py` 已实现 plan 模式用 `definitions_read_only()`（3 工具）、full 模式用 `definitions()`（6 工具）。切 `/plan` 时 tools 数组从 6 变 3，tools 缓存立即失效，下一轮全量重算 + 重新写入。

- design 点明此代价，故 Plan Mode 不应频繁来回切。
- 这支撑了"首轮一次强提示 + 工具子集隔离"的轻量路线——比子代理隔离便宜，符合已确认的"Plan Mode 不升级子代理"。

### D7. FURFLY.md 加载器：项目内向上查找，主动预读注入

- 会话启动时从 cwd 逐级向上查找 `FURFLY.md`，到项目根（含 `.git` 的目录）为止。
- 合并策略：**叠加全部、就近内容排列在后**（让模型先看全局再看局部，局部更具体优先级在序列后部更近 attention）。
- 注入位置：`messages` 开头环境信息块，用 `<furfly_md>...</furfly_md>` 包裹。**不进 system 缓存区**——保核心提示跨项目纯净。
- 环境信息（cwd/平台/规范文件路径）用 `<env_info>` 包裹，与 FURFLY.md 同在 messages 开头。
- 文件缺失/读取失败静默跳过，不阻断启动；大文件截断标注（复用 `_truncate` 或设上限如 8K chars）。
- 加载器协议无关、放叶子层（不 import anthropic/openai），会话期间不重读。

**为何不被动式入口指令**：原设想"系统提示加 1 条入口指令让模型自己 read_file"——依赖模型自觉、每会话多一轮工具往返、可能读到一半就答。主动预读零往返、首轮即有规范内容。加载器本次一步到位。

**为何不做全局 `~/.furfly/` 分层**：本次主体是系统提示架构，全局分层引入跨平台路径与用户级/项目级优先级合并子系统，工作量膨胀——明确推迟。

### D8. 缓存可观测性断言：自洽参照 + 双轨降级

- **Anthropic 严格断言**：第 1 轮 `cache_creation_input_tokens > 0, cache_read_input_tokens = 0`；第 2-N 轮 `cache_creation_input_tokens = 0, cache_read_input_tokens ≈ 第 1 轮 cache_creation_input_tokens`（±2%）。
- **参照值自洽**："read ≈ 第 1 轮 creation"是缓存生效的物理含义，无需预知前缀 token 数。原"read ≈ static_prefix_tokens"的参照值无来源、不可断言。
- **误差收到 ±2%**：严格动静分离预期下 read 跨轮稳定，本该接近 0 漂移。留 2% 余量兜底测量噪声；实测漂移 >2% 是有用的动静分离漏点信号（哪里漏了分离）。
- **OpenAI 降级断言**：`cached_tokens` 第 2 轮起 > 0 即视为隐式缓存命中，不卡 `creation=0`（OpenAI 不返此字段）。
- 另备 5-6 个典型场景人工对比做定性评估（工具路由是否正确、注入是否末尾、模式切换是否触发等）。

## Risks / Trade-offs

- **[Anthropic 前缀匹配脆弱]** 任何静态前缀 token 变动（模块拼装顺序、工具 schema JSON 键序翻转、动态时间戳混入）都击穿缓存。→ 缓解：模块拼装确定性（固定顺序、无随机/时间戳）；工具导出按注册顺序；环境信息严格走 messages 不进 system。可观测性断言会立刻暴露击穿（read 骤降为 0）。
- **[Plan Mode 切换击穿 tools 缓存]** 每次 `/plan`↔`/do` 切换都是一次 cache miss + rewrite。→ 缓解：design 点明代价，文档化"不应频繁来回切"；首轮强提示 + 工具隔离已够维持模式，无需额外注入。
- **[消息条数触发粗度]** ≥8 回合是经验阈值，不精确反映真实上下文压力。→ 缓解：本阶段是事件驱动注入最小可验证版，粗触发可接受；后续接真实 token 计数时可平滑替换触发度量，注入机制本身不变。
- **[FURFLY.md 大文件占 messages]** 项目规范过大可能挤占消息通道。→ 缓解：截断标注（如 8K chars 上限）；会话期间不重读故只付一次成本。
- **[`hard_constraints` 拼进 description 增加 token]** 每工具 description 变长。→ 缓解：tools 走缓存断点②，只首轮付写入成本，后续命中读；且约束本就该让模型看到，非冗余。
- **[OpenAI 隐式缓存不可控]** 无法显式打断点，命中靠前缀达阈值自动触发，短提示可能不缓存。→ 缓解：降级断言只判 `cached_tokens > 0`，不强制等价于 Anthropic 严格断言；agent 层不依赖 OpenAI 缓存生效。
- **[BREAKING: SYSTEM_PROMPT 形状改变]** 外部若直接引用 `SYSTEM_PROMPT` 常量需适配。→ 缓解：内部重构，外部无引用（已确认）；`ToolDefinition.hard_constraints` 有默认值向后兼容。

## Migration Plan

无外部数据迁移。部署步骤：

1. 引入 `ToolDefinition.hard_constraints` 字段（默认空串，向后兼容）。
2. 重构 `prompt.py` 为七模块拼装，产出静态系统提示字符串。
3. 适配器边界改 system 形状（Anthropic 加 cache_control 块）+ tools 拼接 hard_constraints + tools 末个挂 cache_control。
4. 新增 FURFLY.md 加载器与注入模块，cli 启动时触发。
5. agent 层接入注入与可观测性断言。
6. 测试覆盖：缓存断言、hard_constraints 拼接、FURFLY.md 向上查找合并、事件触发不重复、注入末尾追加。

回滚：本变更纯内部重构，回滚即还原 `prompt.py` 单字符串与适配器 system 注入形状；无持久状态需迁移。

## Open Questions

- FURFLY.md 截断上限具体值（8K chars？与 `_truncate` 现有参数对齐？）→ 实现阶段定，design 给 8K 参照。
- 「工具路由原则」模块跨工具哲学的具体措辞（去规定化前提下）→ 写 spec/实现时定，遵循"目标+边界"非流水线。
- `CONTEXT_GROWTH` 注入的具体提示内容 → 实现阶段定，精简版模式约束。
