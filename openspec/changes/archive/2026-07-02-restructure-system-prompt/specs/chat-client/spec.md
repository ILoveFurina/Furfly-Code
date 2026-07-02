## MODIFIED Requirements

### Requirement: 发起对话请求

系统 SHALL 将"内置系统提示词 + 当前完整对话历史"作为上下文，向活动 provider 发起一次对话请求，并按配置决定是否开启扩展思考。内置 system prompt MUST 由适配器注入，conversation 层保持纯 user/assistant/tool 消息。内置 system prompt SHALL 为七个固定模块（身份、系统约束、任务模式、动作执行、工具路由原则、语气风格、文本输出）按固定优先级拼装的产物，MUST NOT 为单段硬编码字符串。Anthropic 协议下 system prompt MUST 以带 `cache_control: {type: ephemeral}` 的 text 块注入，作为静态缓存断点。环境信息与 FURFLY.md 项目规范内容 SHALL 由编排/适配器层注入 `messages` 开头（分别以 `<env_info>`、`<furfly_md>` 标签包裹），MUST NOT 进入 `system` 字段；conversation 层仍保持纯 user/assistant/tool 消息语义。

#### Scenario: 请求包含模块化 system prompt 与完整历史

- **WHEN** 发起对话请求
- **THEN** 请求包含七模块拼装的内置 system prompt 与完整对话历史

#### Scenario: Anthropic 请求 system 字段挂缓存断点

- **WHEN** 以 Anthropic 协议发起对话请求
- **THEN** `system` 字段 SHALL 为含 `cache_control: {type: ephemeral}` 的 text 块，承载七模块拼装产物

#### Scenario: 环境信息与 FURFLY.md 注入 messages 开头

- **WHEN** 发起对话请求且会话已加载环境信息与 FURFLY.md
- **THEN** 环境信息以 `<env_info>` 包裹、FURFLY.md 内容以 `<furfly_md>` 包裹，二者 SHALL 位于 `messages` 数组开头，`system` 字段中 MUST NOT 出现这些动态内容

#### Scenario: 配置 thinking 为真时按协议正确开启扩展思考

- **WHEN** provider 配置 `thinking: true` 且协议为 anthropic
- **THEN** 请求按该协议正确开启扩展思考
