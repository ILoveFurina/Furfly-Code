## ADDED Requirements

### Requirement: 工具抽象与注册中心

系统 SHALL 提供统一的工具抽象：每个工具暴露名称（给模型看的工具名）、描述（给模型的用途说明）、参数 Schema（完整 JSON Schema：type/properties/required）、异步执行入口。系统 MUST 提供一个注册中心集中登记所有工具，支持按名查找，并能按注册顺序把全部工具导出为协议无关的工具定义列表。

#### Scenario: 注册中心导出全部工具定义并按名查找

- **WHEN** 调用 `new_default_registry()` 构造默认注册中心并查询 `definitions()`
- **THEN** 返回恰好 6 条工具定义，名称有序（`read_file`/`write_file`/`edit_file`/`bash`/`glob`/`grep`），每条含 `name`/`description`/`input_schema`；`get("read_file")` 命中对应工具，`get("不存在的工具")` 返回空。

#### Scenario: 工具定义随请求发送

- **WHEN** 发起一次对话请求且注册中心非空
- **THEN** 抓取到的请求体 SHALL 包含与协议对应的工具定义数组（Anthropic 为 `tools` 数组、OpenAI 为 `tools` 中的 function 项），数量与注册中心导出一致。

### Requirement: 读取文件

系统 SHALL 提供 `read_file` 工具：给定路径，返回文件文本内容并带行号便于引用（如 `f"{n:6d}\t{line}"` 风格）；文件不存在、不可读或为目录时 MUST 返回结构化错误（`is_error=True`）而非崩溃。

#### Scenario: 读取存在文件得到带行号内容

- **WHEN** 调用 `read_file` 读取一个存在的文本文件
- **THEN** 返回的 `content` 每行带行号前缀，内容与磁盘文件一致；`is_error` 为假。

#### Scenario: 读取不存在文件返回结构化错误

- **WHEN** 调用 `read_file` 读取一个不存在的路径（或目录、无权限文件）
- **THEN** 返回 `Result(is_error=True)`，`content` 为说明性错误文本；不抛出未捕获异常，不中断会话。

### Requirement: 写入文件

系统 SHALL 提供 `write_file` 工具：给定路径与内容，写入（覆盖）文件；父目录不存在时 MUST 自动创建；返回成功（含路径与字节数）或结构化错误。

#### Scenario: 写入新文件与嵌套路径并校验磁盘

- **WHEN** 调用 `write_file` 写入一个嵌套路径（父目录尚不存在）的新文件
- **THEN** 父目录被自动创建，文件内容正确落地（读回一致），返回成功 `Result` 含字节数；写入失败时返回 `is_error=True`。

### Requirement: 编辑文件

系统 SHALL 提供 `edit_file` 工具：给定路径、原文片段、新文片段，对原文片段做唯一匹配替换；当匹配 0 次或多于 1 次时 MUST 返回清晰错误（说明匹配数），让模型据此重试。

#### Scenario: 唯一匹配时替换成功

- **WHEN** 调用 `edit_file` 且原文片段在文件中恰好出现 1 次
- **THEN** 该处被替换为新文片段并写回，返回成功 `Result`。

#### Scenario: 匹配 0 次返回未找到错误

- **WHEN** 调用 `edit_file` 且原文片段在文件中出现 0 次
- **THEN** 返回 `Result(is_error=True)`，`content` 说明「未找到匹配」。

#### Scenario: 匹配多于 1 次返回含计数的唯一性错误

- **WHEN** 调用 `edit_file` 且原文片段在文件中出现 N（N>1）次
- **THEN** 返回 `Result(is_error=True)`，`content` 含匹配数 N 并提示 old_string 不唯一、请提供更长上下文；与「未找到匹配」的文案可区分。

### Requirement: 执行命令

系统 SHALL 提供 `bash` 工具：给定 shell 命令，在工作目录下执行，受超时约束；返回标准输出、标准错误与退出码；超时或非零退出 MUST 以结构化结果返回，不中断会话。

#### Scenario: 执行命令返回输出与退出码

- **WHEN** 调用 `bash` 执行 `echo hi` 命令
- **THEN** 返回的 `content` 含退出码、stdout（含 `hi`）与 stderr；正常退出时 `is_error` 为假。

#### Scenario: 超时命令被终止并返回超时结果

- **WHEN** 调用 `bash` 执行一个长时间运行的命令（如 `sleep 10`）且执行超过超时上限
- **THEN** 该命令被终止，返回 `Result(is_error=True)` 含超时说明；会话不挂死、界面不冻结。

### Requirement: 按模式找文件

系统 SHALL 提供 `glob` 工具：给定 glob 模式（如 `**/*.py`），返回匹配的文件路径列表。

#### Scenario: glob 模式列出匹配文件

- **WHEN** 调用 `glob` 以 `**/*.py` 在项目根目录搜索
- **THEN** 返回匹配的文件路径列表，含 `src/furflycode/` 下的 `.py` 文件；无匹配时返回空说明（非 `is_error`）。

### Requirement: 搜代码内容

系统 SHALL 提供 `grep` 工具：给定搜索模式（Python 正则）与可选路径范围、可选文件名过滤，在文件内容中检索，返回命中位置（文件 / 行 / 内容）。

#### Scenario: grep 返回命中位置

- **WHEN** 调用 `grep` 以一个已知关键字在项目目录搜索
- **THEN** 返回的 `content` 含 `file:line:content` 形式的命中记录；无命中时返回空说明（非 `is_error`）。

#### Scenario: grep 正则非法返回结构化错误

- **WHEN** 调用 `grep` 传入一个非法的 Python 正则
- **THEN** 返回 `Result(is_error=True)`，`content` 说明「正则非法」并附原因；不抛出未捕获异常。

### Requirement: 工具定义注入请求

发起对话请求时，系统 SHALL 将注册中心导出的工具定义随请求一起发送，使模型知道有哪些工具、各自的参数形态；内置 system prompt MUST 相应说明 Agent 角色与工具使用约定。

#### Scenario: 系统提示词体现 Agent 角色

- **WHEN** 用户询问「你能做什么」
- **THEN** 模型答复 SHALL 提及可用的工具能力（读/写/改文件、执行命令、查找/搜索代码），因 system prompt 已声明 Agent 角色与工具使用约定。

### Requirement: 流式工具调用解析

流式接收回复时，系统 SHALL 正确识别模型发起的工具调用：拼接分片到达的工具名与 JSON 参数碎片，组装出完整的工具调用请求（工具名 + 参数对象）。正文文本增量、思考增量、工具调用三者 MUST 正确区分（思考增量沿用 step1 接收即丢弃）。模型一次回复中可请求一个或多个工具调用。

#### Scenario: 从流式回复拼接出完整工具调用

- **WHEN** 用户提出一个需要用工具的问题（如「读 X 文件」）且模型在流式回复中发起工具调用
- **THEN** 解析层拼装出完整的工具名与 JSON 参数（参数为合法 JSON 对象），与模型实际请求一致；正文文本增量与工具调用分开发出，思考增量被丢弃。

### Requirement: 工具执行

对模型请求的每个工具调用，系统 SHALL 按名从注册中心找到工具并执行；执行 MUST 受超时保护；无论成功或失败都产出结构化结果（成功内容 / 错误信息），不因单个工具失败而中断会话或崩溃。一次回复中的多个工具调用全部执行后，结果一并回灌。

#### Scenario: 工具执行产出结构化结果

- **WHEN** 模型请求执行一个工具调用
- **THEN** 注册中心按名查到工具并执行，返回 `Result(content, is_error)`；未知工具返回 `is_error=True` 的兜底结果；执行异常被捕获并转为结构化错误，不向上层抛 Python 异常。

### Requirement: 结果回灌与单轮闭环

系统 SHALL 将模型的工具调用与对应执行结果按协议格式追加进对话历史，再次发起请求，让模型基于工具结果生成最终文本答复。本轮 MUST 在这次最终答复后结束——即使模型在最终答复阶段又想调用工具，本章也不再发起新一轮工具执行（连环调用 / Agent Loop 留待下一章）。

#### Scenario: 单轮闭环端到端

- **WHEN** 用户问「读 X 文件并总结」
- **THEN** 模型调用 `read_file` → 结果回灌进历史 → 模型据此给出最终文本总结，答复体现文件内容；`conv.messages()` 末尾序列含 assistant 工具调用回合与工具结果回合。

#### Scenario: 单轮上限——不发起第二轮工具执行

- **WHEN** 给一个需要连续两步工具的任务，且第一轮结果回灌后模型在续答中仍请求工具
- **THEN** 编排层不再发起新一轮工具执行，本轮以最终答复（或单轮上限提示）结束；`registry.execute` 在本轮只被调用一次。

### Requirement: 跨协议一致

Anthropic 与 OpenAI 两种协议 SHALL 都支持上述全流程（工具定义注入、流式工具调用解析、结果回灌格式）。系统 MUST 对上层暴露与协议无关的统一接口；切换协议不改变工具系统的上层行为。

#### Scenario: 两协议跑同一组工具任务行为一致

- **WHEN** 分别用 Anthropic 与 OpenAI（含兼容端点）配置跑同一组工具任务
- **THEN** 工具触发、UI 展示、结果回灌、错误反馈在两种协议下行为一致。

### Requirement: TUI 工具行呈现

在对话区，系统 SHALL 以可区分的「工具行」展示每次工具调用：工具名 + 关键参数（如 `● read_file(path)`、`● bash(cmd)`），其后展示结果摘要；结果过长时 MUST 截断/摘要呈现。工具行 SHALL 随流式实时出现，并纳入 scrollback 历史。

#### Scenario: 工具行 Claude Code 风格展示并纳入 scrollback

- **WHEN** 跑一次工具任务后查看对话区并回滚 scrollback
- **THEN** 出现 `● 工具名(关键参数)` 工具行 + 缩进结果摘要，过长结果被截断；回滚可见 preamble 文本 → 工具行 → 结果摘要 → 最终答复 按序出现不交错。

### Requirement: 结构化错误

工具执行失败（文件不存在、命令超时/非零退出、改文件匹配数不对、搜索无结果等）SHALL 以结构化结果回灌给模型，模型可据此调整；同时 MUST 在 UI 以可区分样式提示。程序 SHALL 不崩溃、会话 SHALL 不中断。

#### Scenario: 各类工具失败结构化回灌且 UI 可区分

- **WHEN** 故意触发各类工具失败（读不存在文件、edit 匹配不到、bash 非零退出）
- **THEN** 每类失败均以 `Result(is_error=True)` 结构化回灌给模型，UI 以可区分样式（如红色）提示；逐个触发后程序不崩溃、会话可继续（再正常发一条仍可应答）。

### Requirement: 执行超时

命令执行与潜在长耗时的工具 MUST 受超时约束；超时即终止该工具并返回超时结果，界面 SHALL 不冻结、会话 SHALL 不挂死。超时为内置合理默认值，本章不通过配置调整。

#### Scenario: 超时工具被终止并返回超时结果

- **WHEN** 一个工具执行时间超过内置默认超时（如 30 秒）
- **THEN** 该工具被终止并返回 `Result(is_error=True)` 含超时说明，界面不冻结、会话不挂死。

### Requirement: 界面不阻塞

工具执行与流式期间，界面 MUST 保持响应（可滚动、可见进行中指示），不冻结（沿用 step1 的非阻塞约束）。

#### Scenario: 工具执行期间界面持续响应

- **WHEN** 跑一个稍慢的 `bash` 命令
- **THEN** 动态区显示 `● 工具名(args)` + Running… 指示，界面持续刷新不冻结，asyncio event loop 不卡顿，界面可滚动。

### Requirement: 跨协议一致体验

工具调用的触发、UI 展示、结果回灌、错误反馈，在 Anthropic 与 OpenAI 两种协议下 SHALL 行为一致（沿用并扩展 step1 的跨协议一致约束）。

#### Scenario: 跨协议行为一致

- **WHEN** 在两种协议配置下分别执行相同的工具任务
- **THEN** 触发、展示、结果回灌、错误反馈行为一致，与单协议行为无可观察差异。

### Requirement: 健壮性

工具参数缺失/类型错误、路径非法、命令报错、JSON 参数解析失败等，均 MUST 以结构化错误处理，绝不抛未捕获异常或崩溃堆栈（沿用并扩展 step1 的健壮性约束）。

#### Scenario: 参数与路径异常被结构化处理

- **WHEN** 工具收到缺失参数、非法路径、非法 JSON 参数或命令报错
- **THEN** 均返回 `Result(is_error=True)` 含说明性文本，不抛出未捕获异常、不出现崩溃堆栈、不中断会话。

### Requirement: 结果体量控制

大文件/长输出 MUST 有上限或截断（如读文件行数上限、命令输出截断、搜索结果条数上限），避免撑爆上下文或界面；截断处 SHALL 标注（如 `[truncated]`）。

#### Scenario: 超大输入被截断并标注

- **WHEN** 读一个超过 2000 行的大文件、跑一个超长输出的命令或产生海量搜索结果
- **THEN** 结果被工具级上限截断并在尾部标注 `[truncated]`，不撑爆界面或上下文。

### Requirement: 密钥安全

API 密钥 MUST 不回显、不打印到对话区或任何输出中（沿用 step1 的密钥安全约束）。

#### Scenario: 密钥不出现在任何输出

- **WHEN** 通读运行输出与对话区、并检索明文 key
- **THEN** `api_key` 不出现在任何输出中。
