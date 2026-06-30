## MODIFIED Requirements

### Requirement: 工具定义注入请求

发起对话请求时，系统 SHALL 将注册中心导出的工具定义随请求一起发送，使模型知道有哪些工具、各自的参数形态；内置 system prompt MUST 相应说明 Agent 角色与工具使用约定。`ToolDefinition` SHALL 提供 `hard_constraints` 字段承载该工具的硬性约束。适配器边界 MUST 将 `hard_constraints` 拼接进发往模型的工具 `description` 末尾，作为工具级规则的单一事实来源。内置 system prompt MUST NOT 出现工具级硬约束的字面表述，MUST NOT 列举工具名或工具摘要清单——工具清单由 `tools` 参数单一承载，系统提示的「工具路由原则」模块 ONLY 含跨工具路由哲学。

#### Scenario: 系统提示词体现 Agent 角色

- **WHEN** 用户询问「你能做什么」
- **THEN** 模型答复 SHALL 提及可用的工具能力（读/写/改文件、执行命令、查找/搜索代码），因 system prompt 已声明 Agent 角色与工具使用约定。

#### Scenario: 硬约束拼进工具 description 且不进系统提示

- **WHEN** 适配器将工具定义转为协议特定工具参数
- **THEN** 导出的工具 `description` 末尾 SHALL 包含该工具的 `hard_constraints` 内容；拼装后的 system prompt 中 MUST NOT 出现任一工具的硬约束字面，MUST NOT 列举工具名或摘要清单

#### Scenario: Anthropic tools 参数末个挂缓存断点

- **WHEN** 以 Anthropic 协议发起带工具的请求
- **THEN** `tools` 数组末个工具 SHALL 挂 `cache_control: {type: ephemeral}`，覆盖工具 Schema 静态区域
