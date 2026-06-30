## RENAMED Requirements

- FROM: `### Requirement: 结果回灌与单轮闭环`
- TO: `### Requirement: 结果回灌与 ReAct 循环`

## MODIFIED Requirements

### Requirement: 结果回灌与 ReAct 循环

系统 SHALL 将模型的工具调用与对应执行结果按协议格式追加进对话历史，再次发起请求；当模型在续答中仍请求工具时，SHALL 继续执行并回灌、进入下一轮，形成 ReAct 自主循环，直到模型不再请求工具或触达停止条件（见 `agent-loop` 能力）。循环 MUST 受可配的迭代上限约束作为兜底安全网；到达上限时 SHALL 以明确文本提示非静默收尾，不再强制单轮停机。

#### Scenario: 连环工具调用端到端

- **WHEN** 用户问「读 X 文件并总结」且该任务需连续两步工具（如先读 A 再读 B 再综合）
- **THEN** 模型调用 `read_file` → 结果回灌进历史 → 模型据此继续请求下一步工具 → 再回灌 → …… → 最终给出体现全部工具结果的文本总结；`conv.messages()` 末尾序列含多组 assistant 工具调用回合与工具结果回合交替，以一条无工具调用的 assistant 最终回合收尾；`registry.execute` 在本轮被调用多次。

#### Scenario: 迭代上限兜底收尾

- **WHEN** 模型在某任务上持续请求工具不主动收尾，且循环轮次达到配置的迭代上限
- **THEN** 编排层停止发起新一轮，以明确占位提示（非静默）收尾；`registry.execute` 调用次数不超过上限对应轮次允许的范围。
