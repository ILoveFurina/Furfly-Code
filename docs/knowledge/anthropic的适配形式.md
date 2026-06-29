
## 1. Event Types — 事件类型一览

一次流式响应由以下事件按顺序组成。`ping` 事件可在任意位置穿插出现(用于保活),`error` 出现即代表流中断。

| 事件类型 | 出现位置 | 说明 |
|---------|---------|------|
| `message_start` | 流起始 | 初始消息对象,包含元数据 (id, model, role 等) |
| `content_block_start` | 内容块开始 | 标记一个新的内容块启动(text / tool_use / thinking) |
| `content_block_delta` | 内容块中段 | 内容块的增量更新,**携带实际数据** |
| `content_block_stop` | 内容块结束 | 标记当前内容块结束 |
| `message_delta` | 末尾 | 顶层消息更新 (stop_reason、usage 统计) |
| `message_stop` | 流终止 | 流式响应结束标志 |
| `ping` | 任意位置 | 保活事件,无需处理 |
| `error` | 任意位置 | 流式传输过程中发生错误 |

**典型事件时序:**

```text
message_start
├── content_block_start   (index 0)
│   ├── content_block_delta
│   ├── content_block_delta
│   └── content_block_stop
├── content_block_start   (index 1)
│   ├── content_block_delta
│   └── content_block_stop
├── message_delta
└── message_stop
         ↑ 期间任意位置可能出现 ping
         ↑ 任意位置若出现 error 则流中断
```

---

## 2. Delta Types — 增量内容类型

每个 `content_block_delta` 都包含一个 `delta` 对象,其 `type` 字段决定内容的具体形态。共三种类型。

### 2.1 文本增量 (Text Delta)

最基本的流式输出类型,直接拼接 `text` 字段即可还原完整内容。

```json
{
  "type": "content_block_delta",
  "index": 0,
  "delta": {
    "type": "text_delta",
    "text": "Hello world"
  }
}
```

**消费侧处理:**

```python
full_text = ""
for event in stream:
    if event.type == "content_block_delta" and event.delta.type == "text_delta":
        full_text += event.delta.text
```

### 2.2 工具调用增量 (Input JSON Delta)

当模型触发 Tool Use 时,工具的输入参数以**分片的 JSON 字符串**形式流式返回。**必须在收到 `content_block_stop` 后才能 `json.loads` 解析完整参数**。

```json
{
  "type": "content_block_delta",
  "index": 1,
  "delta": {
    "type": "input_json_delta",
    "partial_json": "{\"location\": \"San Fra"
  }
}
```

**消费侧处理:**

```python
json_buf = ""
for event in stream:
    if event.delta.type == "input_json_delta":
        json_buf += event.delta.partial_json
    elif event.type == "content_block_stop":
        tool_input = json.loads(json_buf)  # 此时才解析
```

### 2.3 思维链增量 (Thinking Delta)

Extended Thinking(扩展思维)模式下的中间推理过程,以增量形式推送,通常用于展示模型的"思考过程"。

```json
{
  "type": "content_block_delta",
  "index": 0,
  "delta": {
    "type": "thinking_delta",
    "thinking": "Let me solve this step by step..."
  }
}
```

---

## 3. 完整 Message 结构

将上述所有流式事件消费完毕后,可组装出一个完整的 `Message` 对象。其 `content` 数组内的 `tool_use.input` 已经是**解析好的字典**,不再保留 `partial_json` 字符串碎片。SDK 通常提供 `stream.get_final_message()` 一键获取该对象。

```json
{
  "id": "msg_01X...",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "好的,我这就帮您查询北京的天气。"
    },
    {
      "type": "tool_use",
      "id": "toolu_01A...",
      "name": "get_weather",
      "input": {"location": "北京"}
    }
  ],
  "model": "claude-3-7-sonnet-20250219",
  "stop_reason": "tool_use",
  "usage": {
    "input_tokens": 125,
    "output_tokens": 64
  }
}
```

> 📌 上例 `tool_use.input` 已经是**解析好的字典**(`{"location": "北京"}`),不再保留流式期间的 `partial_json` 字符串碎片,业务侧可直接 `.input["location"]` 访问。

**关键字段对照表:**

| 字段 | 来源事件 | 说明 |
|------|---------|------|
| `id` / `model` / `role` | `message_start.message` | 顶层消息元数据 |
| `content[].type = "text"` | `text_delta` 累积 | 普通文本回答 |
| `content[].type = "tool_use"` | `input_json_delta` 累积 + 块结束解析 | 工具调用,`input` 已是完整字典 |
| `content[].type = "thinking"` | `thinking_delta` 累积 | 扩展思维链(Extended Thinking) |
| `stop_reason` | `message_delta.delta.stop_reason` | 结束原因 (`end_turn` / `tool_use` / `max_tokens` …) |
| `usage` | `message_delta.usage` | 输入/输出 token 统计 |

### 3.1 工具声明侧(`tools` 元素)

请求时把可用工具以"规格说明书"形式传给模型,`input_schema` 是 JSON Schema 子集:

```json
{
  "name": "get_weather",
  "description": "Get the current weather in a given location",
  "input_schema": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "The city and state, e.g. San Francisco, CA"
      },
      "unit": {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
        "description": "The unit of temperature, either 'celsius' or 'fahrenheit'"
      }
    },
    "required": ["location"]
  }
}
```

### 3.2 模型调用工具意图(`assistant` 消息)

模型决定调用工具时,会在 `assistant` 消息里输出 `tool_use` 块,同时可选地附带文本解释:

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "I'll help you check the current weather and time in San Francisco."
    },
    {
      "type": "tool_use",
      "id": "toolu_01A09q90qw90lq917835lq9",
      "name": "get_weather",
      "input": { "location": "San Francisco, CA" }
    }
  ]
}
```

注意 `tool_use.id` 是模型生成的唯一 ID,业务侧后续回传 `tool_result` 时必须原样对应。

### 3.3 工具结果回传(`user` 消息中的 `tool_result`)

业务侧执行完工具后,把结果作为一条 `role: "user"` 消息回传,通过 `tool_use_id` 与上一轮的 `tool_use.id` 对齐。同一消息里 `tool_result` 之后还可以再追加 `text`(用于追问、补充说明):

```json
{
  "role": "user",
  "content": [
    { "type": "tool_result", "tool_use_id": "toolu_01" },
    { "type": "text",        "text": "What should I do next?" }
  ]
}
```

> ✅ 上面第二段说明是:**在 `tool_result` 之后再追加一段 `text`,允许在同一轮 user 消息中混合工具结果与文本追问**。

> 💡 **适配要点**:内部业务代码通常直接消费这个最终组装好的 `Message`,而无需感知底层 SSE 事件流 — SDK 会在客户端完成上述装配工作。

---

## 4. 注意事项

| # | 说明 |
|---|------|
| 1 | **完整键值对输出**:模型每次完整输出一个 key-value 对,事件之间可能存在明显延迟(模型"思考"时间) |
| 2 | **增量解析**:若需访问部分字段值,使用支持 partial JSON 的库(如 Pydantic)或 SDK 内置辅助方法 |
| 3 | **细粒度工具流式**(Beta):可对工具参数值做更细粒度的流式推送,适用于长字符串/大对象场景 |
| 4 | **`ping` 忽略即可**:仅作连接保活,业务逻辑无需处理 |
| 5 | **`error` 立即中断**:收到 error 事件后应停止后续处理并按业务策略重试或降级 |

---

## 5. 速查表

### 5.1 事件层

| 事件 | 作用 | 携带核心字段 |
|------|------|------------|
| `message_start` | 流开始 | `message.id` / `message.model` |
| `content_block_start` | 内容块开始 | `index` / `content_block.type` |
| `content_block_delta` | 内容增量 | `index` / `delta` |
| `content_block_stop` | 内容块结束 | `index` |
| `message_delta` | 顶层更新 | `delta.stop_reason` / `usage` |
| `message_stop` | 流结束 | — |
| `ping` | 保活 | — |
| `error` | 错误中断 | `error.message` |

### 5.2 Delta 类型层

| `delta.type` | 字段 | 用途 | 解析时机 |
|--------------|------|------|---------|
| `text_delta` | `text` | 普通文本回答 | 收到即可拼接 |
| `input_json_delta` | `partial_json` | 工具调用参数 | 累积至 `content_block_stop` 后再 `JSON.parse` |
| `thinking_delta` | `thinking` | 扩展思维链内容 | 收到即可拼接(通常仅展示给用户) |

---

## 6. 完整处理示例(Python 伪代码)

```python
full_text    = ""
tool_inputs  = {}     # {block_index: json_string}
tool_results = {}     # {block_index: parsed_dict}
thinking     = ""
usage        = None
stop_reason  = None

for event in stream:
    # 1. 顶层消息开始
    if event.type == "message_start":
        msg_id = event.message.id

    # 2. 内容块开始
    elif event.type == "content_block_start":
        block_type = event.content_block.type
        if block_type == "tool_use":
            tool_name[event.index] = event.content_block.name

    # 3. 增量内容
    elif event.type == "content_block_delta":
        d = event.delta
        if d.type == "text_delta":
            full_text += d.text
        elif d.type == "input_json_delta":
            tool_inputs[event.index] = tool_inputs.get(event.index, "") + d.partial_json
        elif d.type == "thinking_delta":
            thinking += d.thinking

    # 4. 内容块结束 — 此时工具 JSON 才完整
    elif event.type == "content_block_stop":
        if event.index in tool_inputs:
            tool_results[event.index] = json.loads(tool_inputs[event.index])

    # 5. 顶层更新
    elif event.type == "message_delta":
        stop_reason = event.delta.stop_reason
        usage = event.usage

    # 6. 流结束
    elif event.type == "message_stop":
        break

    # 7. 错误中断
    elif event.type == "error":
        raise StreamingError(event.error.message)
```