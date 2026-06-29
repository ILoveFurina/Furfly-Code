## ADDED Requirements

### Requirement: ReAct 自主循环

系统 SHALL 以 ReAct 模式编排对话：每一轮向活动 provider 发起请求 → 收集模型请求的工具调用 → 执行工具 → 将结果回灌进对话历史 → 进入下一轮，如此循环直到模型不再请求工具或触达停止条件。一次用户提交 SHALL 触发一个完整的自主循环（可含多轮工具调用），无需用户在每步工具间反复催促。

#### Scenario: 多步工具任务在一次提交内自主完成

- **WHEN** 用户提交一个需要连续两步工具的任务（如「读 A 文件与 B 文件并对比」），且不再次提交
- **THEN** 模型先调用 `read_file`(A) → 结果回灌 → 模型再调用 `read_file`(B) → 结果回灌 → 模型给出体现两文件内容的最终文本答复；整个过程在一次提交内完成；`conv.messages()` 末尾序列含多组 assistant 工具调用回合与工具结果回合交替，以一条无工具调用的 assistant 回合收尾。

#### Scenario: 纯文本无需工具时单轮即止

- **WHEN** 用户提交一个不需工具的问题
- **THEN** 循环在首轮即收集不到工具调用，模型直接给出文本答复并结束循环。

### Requirement: 停止条件

系统 SHALL 在以下任一情形终止自主循环并产出循环结束事件：(a) 某轮模型未请求工具（正常完成）；(b) 循环轮次达到可配迭代上限（兜底安全网）；(c) 用户主动取消；(d) 连续不少于 2 轮中所有工具调用均命中的是未知工具；(e) provider 流出错。到达迭代上限时 SHALL 以明确文本提示非静默收尾，便于用户发「继续」推进。

#### Scenario: 迭代上限兜底收尾

- **WHEN** 模型在某任务上持续请求工具不主动收尾，且循环轮次达到配置的 `max_iterations`
- **THEN** 编排层停止发起新一轮，落明确占位提示（如「已达到迭代上限 N，可发送"继续"推进」）并结束循环；`registry.execute` 调用次数不超过上限对应轮次允许的范围。

#### Scenario: 连续未知工具早停

- **WHEN** 连续 2 轮中模型请求的所有工具调用都是注册中心里不存在的工具名
- **THEN** 编排层停止循环并提示，不无限重试未知工具。

#### Scenario: 流出错即止

- **WHEN** provider 流产出错误事件
- **THEN** 循环立即终止并产出错误事件，不继续后续轮次。

### Requirement: 迭代上限可配

`Config` SHALL 提供 `max_iterations` 字段（整数，默认 20），从 `.furflycode/config.yaml` 顶层读取；`cli` SHALL 将其传入 `Agent`。该上限是循环的兜底安全网，可调高以适配长任务。

#### Scenario: 配置 max_iterations 生效

- **WHEN** 配置文件设置 `max_iterations: 3` 并提交一个模型反复请求工具的任务
- **THEN** 循环在第 3 轮后停止并落占位提示。

#### Scenario: 未配置时用默认上限

- **WHEN** 配置文件未设置 `max_iterations`
- **THEN** 循环使用默认值 20 作为兜底上限。

### Requirement: 事件流扩展

Agent SHALL 对外产出异步事件流，事件类型包括：文本增量、工具调用开始/结束、一轮 LLM 调用完成（携带轮次号、本轮是否含工具调用、本轮 token 用量）、循环结束（携带结束原因）、错误。事件流 SHALL 使 Agent 与界面彻底解耦——界面仅消费事件，不感知循环内部步数。

#### Scenario: 多轮循环产出多轮完成事件与带原因的结束事件

- **WHEN** 跑一个含 2 轮工具调用的自主循环
- **THEN** 界面依次收到：文本增量 → 工具开始/结束 → 第 1 轮完成事件（iteration=1, has_tool_calls=true）→ 文本增量 → 工具开始/结束 → 第 2 轮完成事件（iteration=2, has_tool_calls=true）→ 文本增量 → 第 3 轮完成事件（iteration=3, has_tool_calls=false）→ 循环结束事件（reason=normal）。

#### Scenario: 循环结束事件携带原因

- **WHEN** 循环因迭代上限停止
- **THEN** 循环结束事件的 reason 字段为 `max_iterations`，与正常完成的 `normal` 可区分。

### Requirement: 流式双路收集

每轮流式接收中，Agent SHALL 既实时把文本增量推送给界面（供逐字呈现），又同时累积完整文本响应与工具调用列表供循环判断是否继续。两路收集 SHALL 在同一次流式遍历中合一完成，不缓冲至轮末才推送。

#### Scenario: 文本逐字实时呈现且循环据完整响应判断

- **WHEN** 一轮流式接收中模型先输出若干文本再发起工具调用
- **THEN** 文本增量在到达时即逐字呈现给界面（不等轮末），同时循环据累积的完整响应与工具调用列表判断进入工具执行。

### Requirement: 工具安全分级标记

`BaseTool` SHALL 暴露 `is_read_only()` 标记，声明该工具是否只读无副作用（默认 `False`，即视为有副作用）。6 个内置工具 SHALL 按实际声明：`read_file`/`glob`/`grep` 为只读，`write_file`/`edit_file`/`bash` 为有副作用。

#### Scenario: 内置工具按副作用正确分级

- **WHEN** 查询各内置工具的 `is_read_only()`
- **THEN** `read_file`/`glob`/`grep` 返回真，`write_file`/`edit_file`/`bash` 返回假。

### Requirement: 多工具调用安全分批

当模型在一次回复中请求多个工具调用时，Agent SHALL 按安全性分批执行：只读工具用 `asyncio.gather` 并发执行，有副作用的工具按模型给出顺序串行执行。只读组先并发执行，副作用组随后串行。所有结果一并回灌进对话历史。

#### Scenario: 同轮多个只读工具并发执行

- **WHEN** 模型一次请求 2 个只读工具（如两个 `read_file`）
- **THEN** 两者并发执行，总用时近似单个较慢者而非两者之和。

#### Scenario: 同轮多个有副作用工具串行执行

- **WHEN** 模型一次请求 2 个有副作用的工具（如 `write_file` 与 `bash`）
- **THEN** 两者按模型给出顺序串行执行，不并发，避免副作用竞争。

### Requirement: Plan Mode 两段式

系统 SHALL 支持会话级 Plan Mode 开关：`/plan` 命令切入 plan 模式，此后每轮向 provider 发送的工具定义仅含只读工具子集，使模型只能探查不能修改，从而产出执行计划；`/do` 命令切回 full 模式，恢复全部工具供执行。Plan 模式下界面 SHALL 显示明显提示（如状态栏 `PLAN MODE`），防漏切回。

#### Scenario: /plan 后模型无法调用副作用工具

- **WHEN** 用户输入 `/plan` 后请求模型「重构某文件」
- **THEN** 模型只能调用只读工具（`read_file`/`glob`/`grep`）探查并产出计划文本，无法调用 `write_file`/`edit_file`/`bash`（因其定义未注入本轮请求）。

#### Scenario: /do 后恢复全工具执行

- **WHEN** 用户在 plan 模式下输入 `/do` 并要求模型执行计划
- **THEN** 模型恢复可用全部工具，可调用 `write_file`/`edit_file`/`bash` 落地修改。

#### Scenario: Plan 模式有界面提示

- **WHEN** 处于 plan 模式
- **THEN** 界面状态栏显示 `PLAN MODE` 提示，与 full 模式可区分。

### Requirement: Token 用量回传

provider SHALL 尽力在每轮流式结束时产出 token 用量（含输入/输出/缓存 tokens），Agent SHALL 经「一轮 LLM 调用完成」事件把用量回传给界面。当协议或端点不支持用量回传时，SHALL 降级为用量缺失且不崩溃。

#### Scenario: 一轮完成事件携带 token 用量

- **WHEN** provider 协议支持用量回传（如 Anthropic）且完成一轮
- **THEN** 该轮完成事件的 usage 字段含非零的输入/输出 token 计数。

#### Scenario: 端点不支持用量时降级不崩

- **WHEN** provider 协议或兼容端点不回传用量（如某些 OpenAI 兼容服务）
- **THEN** 完成事件的 usage 字段为空/None，界面不显示用量区，循环不受影响。

### Requirement: 循环健壮性与可取消

工具执行失败、参数错误、超时、未知工具等 SHALL 以结构化 `Result(is_error=True)` 回灌给模型，模型可据以调整并继续循环；循环自身 SHALL 不因单个工具失败而中断或抛未捕获异常。循环期间用户 SHALL 可中途取消（如按 Esc），取消后界面复位至可输入状态，不残留半截循环。

#### Scenario: 工具失败后循环继续

- **WHEN** 循环中某工具调用失败（如 `read_file` 读不存在的路径）
- **THEN** 失败以 `Result(is_error=True)` 回灌，模型据此调整并继续后续轮次，循环不中断、不抛未捕获异常。

#### Scenario: 用户中途取消循环

- **WHEN** 循环进行中用户按 Esc 取消
- **THEN** 循环终止，界面复位至可输入状态，不残留进行中指示。

### Requirement: 跨协议一致

ReAct 循环驱动、停止条件、事件流结构、安全分批、Plan Mode 在 Anthropic 与 OpenAI 两种协议下 SHALL 行为一致；Agent SHALL 只依赖 `llm.Provider` 接口，不 import `anthropic`/`openai`。

#### Scenario: 两协议跑同一多步任务行为一致

- **WHEN** 分别用 Anthropic 与 OpenAI（含兼容端点）配置跑同一个需要多轮工具的任务
- **THEN** 循环轮次、事件流类型、工具分批、停止条件行为一致，与单协议无可观察差异。
