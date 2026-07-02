# chat-client Specification

## Purpose
chat-client 规格定义 Furfly Code 的多协议 LLM 终端对话客户端：配置加载与校验、provider 选择、Anthropic / OpenAI 协议适配、流式接收、多轮上下文、终端界面布局与交互、错误反馈与退出。
## Requirements
### Requirement: 配置加载

系统 SHALL 从项目内的 YAML 配置文件（`.furflycode/config.yaml`）读取一个 providers 列表（可含多项）。每项 MUST 包含：可读名称、协议类型、可选的自定义端点地址、密钥、模型名、是否开启扩展思考。系统 SHALL 逐项校验必要项（如密钥），缺失时 MUST 给出清晰的启动期错误（指明哪个 provider 的哪个字段）并终止，而非崩溃堆栈。

#### Scenario: 合法配置解析为 providers 列表

- **WHEN** 存在合法的 `.furflycode/config.yaml` 且每项字段齐全、protocol 合法
- **THEN** 系统解析出正确条数的 providers 列表并继续启动

#### Scenario: 缺少密钥等必要项时给出清晰错误并退出

- **WHEN** 配置中某 provider 缺少 `api_key` 等必要字段
- **THEN** 启动给出清晰的错误信息（指明 `providers[i].字段`）并以非零退出码终止，不抛出未捕获堆栈

#### Scenario: 配置文件缺失或 YAML 格式错误时给出可读错误

- **WHEN** 配置文件不存在或 YAML 格式错误
- **THEN** 系统给出明确可读的错误提示并以非零退出码终止，而非崩溃堆栈

### Requirement: provider 选择

系统 SHALL 根据配置数量决定启动路径：若仅有一个 provider，MUST 直接采用它进入对话；若有多个，MUST 启动后先呈现一个方向键选择界面（列出各 provider 的名称与模型），用户选定一项后再进入对话。被选定者即本次会话的活动 provider。

#### Scenario: 仅一份配置时直接进入对话

- **WHEN** 配置中仅有一个 provider
- **THEN** 启动直接进入对话，无需选择

#### Scenario: 多份配置时出现方向键列表供选择

- **WHEN** 配置中有多个 provider
- **THEN** 启动后出现方向键 `OptionList` 供选择，列出各 provider 的名称与模型；用户选定后进入对话，底部状态栏显示所选 provider 的名称与模型

### Requirement: 多协议适配

系统 SHALL 根据活动 provider 的"协议类型"选择对应的请求构造与响应解析方式，统一支持 Anthropic 与 OpenAI 两种协议。若配置了自定义端点地址，MUST 覆盖该协议的默认端点（从而可接入各类兼容服务）。系统 MUST 对上层暴露与协议无关的统一对话接口。

#### Scenario: 同一组对话在两种协议下均能正常收发

- **WHEN** 同一组对话分别用 anthropic 协议与 openai 协议（含自定义 base_url）配置运行
- **THEN** 两者均能正常收发，且切换配置不改变上层交互行为

#### Scenario: 自定义 base_url 覆盖默认端点接入兼容服务

- **WHEN** 为某 provider 配置自定义 `base_url`
- **THEN** 系统覆盖该协议默认端点，可正常收发

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

### Requirement: 流式接收

系统 SHALL 以流式方式接收回复，实时解析出正文文本增量并向界面输送。对扩展思考产生的思考增量 MUST 正确识别但不渲染（接收即丢弃），不得混入正文。

#### Scenario: 回复以逐字流式出现

- **WHEN** 收到回复流
- **THEN** 正文文本以纯文本逐字实时呈现

#### Scenario: 开启 thinking 时界面不出现思考文本

- **WHEN** 开启扩展思考接收回复
- **THEN** 界面不出现任何思考文本，仅显示最终回复

### Requirement: 多轮上下文

系统 SHALL 在单次会话内维护完整对话历史（用户与助手消息交替追加）。每一轮新请求 MUST 携带此前全部上下文，实现连续多轮对话。程序退出后历史 MUST 不保留。

#### Scenario: 连续多轮对话模型能引用前文

- **WHEN** 先告知信息、后追问
- **THEN** 模型能正确引用前文回答，证明上下文被携带

#### Scenario: 退出再启动后历史为空

- **WHEN** 退出程序后重新启动
- **THEN** 对话历史为空

### Requirement: 终端界面布局

系统启动后 MUST 呈现一个全功能终端界面，自上而下包含：(a) 启动横幅：ASCII 猫咪图案 + 应用名与版本号 + 当前工作目录；(b) 一行就绪提示信息；(c) 对话区：依时间顺序展示历次用户输入与助手回复；(d) 底部带边框的输入框，含 ❯ 提示符与占位文字（如 "Send a message..."）；(e) 底部状态栏：左侧显示活动 provider 的名称，右侧显示其模型名。

#### Scenario: 启动界面包含全部布局要素

- **WHEN** 启动应用
- **THEN** 界面包含猫咪 banner、应用名与版本、工作目录、就绪提示行、带 ❯ 与占位符的输入框、底部状态栏（左侧 provider 名、右侧模型名）

### Requirement: 流式呈现与渲染

助手回复在流式期间 MUST 以纯文本逐字实时显示；该轮回复结束后，MUST 将其整段以 markdown 形式重新渲染美化（代码块、列表、强调等）后定型展示。

#### Scenario: 流式期间纯文本逐字实时显示

- **WHEN** 流式期间接收文本增量
- **THEN** 正文以纯文本逐字实时显示

#### Scenario: 回复结束后整段以 markdown 美化显示

- **WHEN** 一轮回复结束
- **THEN** 整段以 markdown 美化显示，代码块、列表、强调等正确渲染

### Requirement: 输入与提交

用户 SHALL 在输入框键入文本，可用 Alt+Enter 插入换行进行多行编辑；按 Enter 提交。提交后 MUST 清空输入框，界面进入等待/流式状态，期间 MUST 不接受新的提交，直至本轮回复结束。

#### Scenario: 多行编辑与提交

- **WHEN** 用户在输入框用 Alt+Enter 换行编辑多行内容后按 Enter 提交
- **THEN** 输入框清空，界面进入等待/流式状态

#### Scenario: 流式期间不接受新提交

- **WHEN** 一轮回复进行中用户尝试提交
- **THEN** 界面不接受新提交，直至本轮回复结束

### Requirement: 退出

系统 MUST 提供明确的退出方式：输入 `/exit` 命令，或按 Ctrl+C，均可安全退出程序。

#### Scenario: /exit 与 Ctrl+C 均能安全退出

- **WHEN** 用户输入 `/exit` 或按 Ctrl+C
- **THEN** 程序安全退出，终端恢复正常（无残留 raw mode / 错乱）

### Requirement: 错误反馈

当请求失败（鉴权失败、限流、网络中断、模型不存在等）时，系统 MUST 在对话区以可区分的样式展示错误信息，程序 MUST 不退出，用户可继续下一轮对话。

#### Scenario: 请求失败时对话区显示可区分错误且不退出

- **WHEN** 用错误密钥或不存在的模型触发请求失败
- **THEN** 错误在对话区以可区分样式（红色）显示，程序不退出，用户可继续下一轮对话

### Requirement: 响应计时

系统 SHALL 自请求发出（开始等待模型）即启动计时，以"进行中"指示实时显示已用秒数（形如 `Imagining… (5s)`，秒数随时间递增）；收到首个增量后继续计时；本轮回复结束后 MUST 定型显示该轮总耗时。

#### Scenario: 发出请求即开始计时并实时显示秒数

- **WHEN** 发出请求并开始等待模型
- **THEN** 立即显示 `Imagining… (Ns)` 形式的进行中指示，秒数随时间递增，且首个增量到达前即可见

#### Scenario: 本轮结束后显示总耗时

- **WHEN** 一轮回复结束
- **THEN** 定型显示该轮总耗时

### Requirement: 界面不阻塞

网络请求与界面渲染 MUST 互不阻塞。流式数据以异步方式驱动界面更新，等待与流式期间界面 SHALL 始终保持响应（可滚动、可见进行中指示），不得冻结。

#### Scenario: 等待与流式期间界面保持响应

- **WHEN** 等待与流式期间
- **THEN** 界面保持可响应（可滚动、不冻结）

### Requirement: 流式实时性与等待反馈

在收到首个文本增量前，系统 MUST 显示带动画与实时秒数的"处理中"指示（如 `Imagining… (5s)`），让用户明确知道正在等待模型；文本增量到达后 SHALL 尽快逐字呈现，给用户"实时打字"的观感。

#### Scenario: 首个增量前显示处理中指示

- **WHEN** 已发出请求但尚未收到首个文本增量
- **THEN** 显示带动画与实时秒数的处理中指示

#### Scenario: 增量到达后逐字呈现

- **WHEN** 文本增量到达
- **THEN** 尽快逐字呈现，给用户实时打字的观感

### Requirement: 跨协议一致体验

无论使用 Anthropic 还是 OpenAI 协议，用户感知的输入、流式输出、多轮上下文与错误反馈行为 MUST 保持一致。

#### Scenario: 切换协议不改变上层交互行为

- **WHEN** 分别用 anthropic 与 openai 协议配置跑同一组对话
- **THEN** 输入、流式输出、多轮上下文与错误反馈行为一致

### Requirement: 配置健壮性

配置文件缺失、YAML 格式错误、必要字段缺失等情况，系统 MUST 给出明确可读的错误提示，而非崩溃堆栈。

#### Scenario: 配置异常给出可读错误

- **WHEN** 配置文件缺失、YAML 格式错误或必要字段缺失
- **THEN** 系统给出明确可读的错误提示，而非崩溃堆栈

### Requirement: 密钥安全

API 密钥 MUST 不在界面回显，不打印到对话区或任何日志输出中。

#### Scenario: 密钥不回显不打印

- **WHEN** 程序运行并产出界面与日志输出
- **THEN** 对话区与任何输出均不出现 `api_key` 明文

### Requirement: 终端兼容与自适应

系统 MUST 在常见终端下正常显示；markdown 渲染与界面布局 SHALL 对终端宽度自适应，窄屏不错版。

#### Scenario: 缩放终端宽度后不错版

- **WHEN** 运行中调整终端宽度
- **THEN** 输入框、对话区与 markdown 渲染不错版

### Requirement: 退出整洁

退出时系统 MUST 恢复终端状态（清理 raw mode 等），不残留损坏的终端环境。

#### Scenario: 退出后终端恢复正常

- **WHEN** 退出程序
- **THEN** 终端状态恢复（无残留 raw mode / 错乱）

### Requirement: 完成消息持久追加与可回看

完成的消息（用户输入、渲染后的助手回复、错误）MUST 持久追加到对话区（`RichLog`），可用终端原生滚轮或 Textual 滚动回看，退出后内容保留在终端历史中；动态区 SHALL 仅含输入框、正在流式的回复与状态栏。

#### Scenario: 完成消息追加到对话区并可回看

- **WHEN** 多轮对话完成
- **THEN** 完成的消息追加到 `RichLog`，可滚动回看，退出后历史仍在终端中

