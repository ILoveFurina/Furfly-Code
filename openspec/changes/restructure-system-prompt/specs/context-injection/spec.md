## ADDED Requirements

### Requirement: 事件驱动注入

系统 SHALL 在运行中通过 `<system_reminder>...</system_reminder>` 标签包裹的 user 角色消息向 `messages` 末尾注入补充指令，模型通过 XML 标签识别其系统意图。注入 MUST 追加于 `messages` 数组末尾，MUST NOT 插入在历史消息中间。注入触发条件仅两个：`CONTEXT_GROWTH`（消息深度跨过阈值）与 `TASK_BOUNDARY`（用户消息含模式关键词）。系统 MUST NOT 实现 `MODE_DEVIATION` 类基于模型输出内容的偏离检测触发。同一事件 MUST NOT 重复触发。

#### Scenario: 注入永远末尾追加

- **WHEN** 任一触发条件命中并产生注入
- **THEN** 包裹 `<system_reminder>` 的 user 消息 SHALL 作为 `messages` 数组的最后一条追加，MUST NOT 插入在既有历史消息之间

#### Scenario: CONTEXT_GROWTH 按消息深度触发且不依赖 token 计数

- **WHEN** 会话消息深度达到 ≥8 个 user/assistant/tool 回合
- **THEN** 系统触发 `CONTEXT_GROWTH` 注入；触发判定 SHALL 基于消息条数，MUST NOT 依赖任何 token 计数器或外部 tokenizer 依赖

#### Scenario: TASK_BOUNDARY 按模式关键词触发

- **WHEN** 用户消息含模式关键词（如 `/plan`、`/do`）
- **THEN** 系统触发 `TASK_BOUNDARY` 注入，追加对应模式约束的 `<system_reminder>` 消息

#### Scenario: 同一事件不重复触发

- **WHEN** 同一触发条件在会话中已触发过一次后再次满足条件
- **THEN** 系统 MUST NOT 再次为该事件注入 `<system_reminder>` 消息

#### Scenario: 不实现基于输出内容的偏离检测

- **WHEN** 审查注入触发条件集合
- **THEN** 集合 SHALL 仅含 `CONTEXT_GROWTH` 与 `TASK_BOUNDARY`，MUST NOT 含基于模型输出内容（如「输出含代码块」）判定的偏离检测触发

### Requirement: Plan Mode 轻量维持与缓存代价

Plan Mode SHALL 靠首轮一次强提示 + 只读工具子集隔离维持，MUST NOT 升级为独立子代理上下文隔离。模式切换会让 tools 数组在只读子集与全量之间变化，从而击穿 tools 缓存（产生一次 cache miss 与 rewrite）。系统文档 SHALL 点明此代价，故 Plan Mode 不应频繁来回切换。

#### Scenario: Plan Mode 不升级子代理

- **WHEN** 用户进入 Plan Mode（`/plan`）
- **THEN** 系统 SHALL 通过首轮强提示与只读工具子集维持模式，MUST NOT 启动独立隔离的规划子代理

#### Scenario: 模式切换击穿 tools 缓存

- **WHEN** 用户在 Plan Mode 与全量模式之间切换
- **THEN** tools 数组内容发生变化，tools 缓存 SHALL 失效并产生一次 cache miss 与 rewrite；该代价被文档化为不应频繁切换的依据

### Requirement: FURFLY.md 项目规范加载

系统 SHALL 在会话启动时主动预读项目规范文件 `FURFLY.md`。加载器从当前工作目录逐级向上查找所有 `FURFLY.md`，直到项目根（含 `.git` 的目录）为止。找到的多份内容 SHALL 全部叠加，就近（更靠近 cwd 的）内容排列在序列后部。合并后的内容 MUST 用 `<furfly_md>...</furfly_md>` 标签包裹注入 `messages` 开头环境信息块，MUST NOT 进入 `system` 缓存区。加载器 MUST 协议无关、放叶子层（不 import anthropic/openai），会话期间 MUST NOT 重复读取。

#### Scenario: 向上查找并合并多份 FURFLY.md

- **WHEN** 会话启动且 cwd 位于项目子目录，该子目录与若干上级目录直至项目根各存在 `FURFLY.md`
- **THEN** 加载器 SHALL 收集从项目根到 cwd 路径上的所有 `FURFLY.md`，叠加全部内容，就近内容排列在后，合并后注入 `messages` 开头

#### Scenario: FURFLY.md 内容不进 system 缓存区

- **WHEN** FURFLY.md 内容被注入请求
- **THEN** 内容 SHALL 位于 `messages` 数组并包裹 `<furfly_md>` 标签，`system` 字段与 `tools` 参数中 MUST NOT 出现 FURFLY.md 内容

#### Scenario: 文件缺失或读取失败静默跳过

- **WHEN** 某级目录不存在 `FURFLY.md` 或读取失败
- **THEN** 加载器 SHALL 静默跳过该级，MUST NOT 抛出异常或阻断启动

#### Scenario: 大文件截断标注

- **WHEN** 某份 `FURFLY.md` 内容超过截断上限
- **THEN** 注入内容 SHALL 被截断并附截断标注，MUST NOT 无限制占据消息通道

#### Scenario: 会话期间不重读

- **WHEN** 会话启动后进行多轮对话
- **THEN** 加载器 MUST NOT 重新读取 `FURFLY.md`，注入内容在会话期内保持启动时快照

### Requirement: 环境信息注入

系统 SHALL 将环境信息（当前工作目录、平台、规范文件路径）用 `<env_info>...</env_info>` 标签包裹，注入 `messages` 开头环境信息块，与 FURFLY.md 内容同处 `messages` 开头。环境信息 MUST NOT 进入 `system` 缓存区。

#### Scenario: 环境信息标签注入 messages 开头

- **WHEN** 系统组装请求的 `messages`
- **THEN** 环境信息 SHALL 以 `<env_info>` 标签包裹出现在 `messages` 开头，MUST NOT 出现在 `system` 字段或 `tools` 参数中
