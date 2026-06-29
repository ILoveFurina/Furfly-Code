## 1. Chunk 结构 — SSE 数据块一览

OpenAI 的 Chat Completions 流式响应 **没有事件类型**(`event: ...` 行固定为空白或不存在),整流是一串连续的 SSE 数据,每行形如:

```text
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk", ... }
```

每条数据都是一个完整的 `ChatCompletionChunk` 对象,顶层结构一致:

| 顶层字段 | 类型 | 说明 |
|---------|------|------|
| `id` | string | 同一响应中所有 chunk 的 `id` 相同 |
| `object` | `"chat.completion.chunk"` | 字面量,用于流式识别 |
| `created` | int | Unix 时间戳,**所有 chunk 共享同一值** |
| `model` | string | 实际返回的模型名(可能与请求时的别名不同) |
| `choices` | array | 增量数据,见下文;**最后一个 chunk 可能为空**(`include_usage` 场景) |
| `usage` | object \| null | **仅在**请求带 `stream_options: {"include_usage": true}` 时,**最后一个 chunk** 才携带 |
| `system_fingerprint` | string? | 后端指纹,与 `seed` 配合判断确定性 |
| `service_tier` | string? | `"auto"` / `"default"` / `"flex"` / `"scale"` / `"priority"` |

**`choices[]` 每个元素的字段:**

| 字段 | 类型 | 说明 |
|------|------|------|
| `index` | int | 多 `n` 场景下区分不同 choice(常用 0) |
| `delta` | object | 本块的增量内容,见第 2 节 |
| `finish_reason` | string? | **只在最后一个 chunk 出现一次**(`"stop"` / `"length"` / `"tool_calls"` / `"content_filter"` / `"function_call"`[deprecated]) |
| `logprobs` | object? | 仅在请求带 `logprobs: true` 时携带 |

**典型时序:**

```text
chunk 1   { choices: [{ delta:{role:"assistant", content:""},        finish_reason:null }] }
chunk 2   { choices: [{ delta:{content:"你"},                       finish_reason:null }] }
chunk 3   { choices: [{ delta:{content:"好"},                       finish_reason:null }] }
  ...     { choices: [{ delta:{content:"..."},                      finish_reason:null }] }
chunk N   { choices: [{ delta:{},                                   finish_reason:"stop" }] }
chunk N+1 { choices: [], usage: {prompt_tokens:..., completion_tokens:...} }    ← 仅当 include_usage
```

> ⚠️ OpenAI 流是**扁平的数据流**,没有 `start / delta / stop` 这种事件边界信号。判断"流是否结束"的唯一可靠标志是**连接关闭**(SSE 末尾的 `data: [DONE]` 行);判断"这一块是否是最后一个内容块"靠 `finish_reason != null`。

`data: [DONE]` 终止行:**所有**响应都以这一行收尾(即便中途出错也会发;但错误通常直接断流不发)。业务侧应识别它并立即停止解析。

---

## 2. Delta 字段 — 增量内容类型

每个 chunk 的 `choices[0].delta` 是核心负载,常见字段如下:

### 2.1 文本增量 (`delta.content`)

最基本的流式输出,直接拼接即可。

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "choices": [
    { "index": 0, "delta": { "content": "你好" }, "finish_reason": null }
  ]
}
```

**消费侧处理:**

```python
full_text = ""
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        full_text += delta.content
```

### 2.2 工具调用增量 (`delta.tool_calls[]`)

当模型触发 Tool Call 时,工具参数以**分片的 JSON 字符串**形式流式返回。关键点:

- 同一响应里 `tool_calls` 是**数组**,每个元素带 `index`(0、1、2 …)用以标识"第几个并行调用"
- **每个 tool_call 的第一个 chunk** 才携带 `id` 和 `function.name`;后续 chunk 只携带 `function.arguments` 片段
- `arguments` 必须累积到流结束后再 `json.loads` 解析

下面是同一个 tool_call 在流中的两个连续 chunk 示例。

**chunk A — 第 1 个 tool_call 的起始块**(携带 `id` 和 `function.name`):

```json
{
  "choices": [{
    "index": 0,
    "delta": {
      "tool_calls": [{
        "index": 0,
        "id": "call_abc123",
        "type": "function",
        "function": { "name": "get_weather", "arguments": "" }
      }]
    },
    "finish_reason": null
  }]
}
```

**chunk B — 后续参数增量块**(只携带 `arguments` 片段):

```json
{
  "choices": [{
    "index": 0,
    "delta": {
      "tool_calls": [{
        "index": 0,
        "function": { "arguments": "{\"location\":" }
      }]
    },
    "finish_reason": null
  }]
}
```

**消费侧处理(按 index 聚合):**

```python
import json

tool_args_buf = {}   # {tool_index: arguments_string}
tool_meta     = {}   # {tool_index: {"id": ..., "name": ..., "type": ...}}

for chunk in stream:
    delta = chunk.choices[0].delta
    for tc in (delta.tool_calls or []):
        i = tc.index
        if tc.id:
            tool_meta[i] = {"id": tc.id, "type": tc.type, "name": tc.function.name}
        if tc.function and tc.function.arguments:
            tool_args_buf[i] = tool_args_buf.get(i, "") + tc.function.arguments

# 流结束后,逐个解析
tool_calls = [
    {**tool_meta[i], "arguments": json.loads(tool_args_buf[i])}
    for i in sorted(tool_meta)
]
```

### 2.3 拒绝内容 (`delta.refusal`)

模型拒绝响应时(违反策略),会在 `delta.refusal` 中流式输出拒绝文本,处理方式同 `content`。

### 2.4 角色标识 (`delta.role`)

**仅第一个 chunk 携带** `delta.role = "assistant"`,后续 chunk 该字段为 `null`。通常仅用于业务侧确认流类型。

### 2.5 Usage(`usage` 顶层)

需要请求带 `stream_options: {"include_usage": true}` 才会出现,且只在**最后一个 chunk**(此时 `choices` 为空数组)单独发一次。

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion.chunk",
  "choices": [],
  "usage": {
    "prompt_tokens": 125,
    "completion_tokens": 64,
    "total_tokens": 189,
    "prompt_tokens_details":     { "cached_tokens": 0, "audio_tokens": 0 },
    "completion_tokens_details": { "reasoning_tokens": 0, "audio_tokens": 0 }
  }
}
```

> 💡 OpenAI 的"思维链"在流式协议里**不暴露原文**,仅在 `usage.completion_tokens_details.reasoning_tokens` 给出 token 数。要在流里看到 reasoning 文本,需要使用 o-series 模型的 `reasoning_effort` + `summary` 参数(见第 4 节)。

### 2.6 finish_reason(`choices[].finish_reason`)

只在最后一个内容 chunk 出现一次:

| 值 | 含义 |
|----|------|
| `"stop"` | 自然停止(或命中 `stop` 序列) |
| `"length"` | 命中 `max_tokens` 上限被截断 |
| `"tool_calls"` | 模型调用了工具,业务侧需取出 `tool_calls` 并回传 `tool` 消息 |
| `"content_filter"` | 内容审核拦截 |
| `"function_call"` | 已废弃,等价于 `"tool_calls"` |

---

## 3. 完整 Choice 结构

将所有 chunk 合并后,得到等价于非流式 `ChatCompletion.choices[0]` 的对象:

```json
{
  "id": "chatcmpl-9X...",
  "object": "chat.completion",
  "created": 1737033600,
  "model": "gpt-4o-2024-08-06",
  "choices": [
    {
      "index": 0,
      "finish_reason": "tool_calls",
      "message": {
        "role": "assistant",
        "content": "好的,我这就帮您查询北京的天气。",
        "refusal": null,
        "annotations": [],
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"location\":\"北京\"}"
            }
          }
        ]
      },
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 125,
    "completion_tokens": 64,
    "total_tokens": 189,
    "completion_tokens_details": { "reasoning_tokens": 0 }
  },
  "system_fingerprint": "fp_xxx"
}
```

> 📌 上例 `function.arguments` 在协议层仍是 JSON 字符串,但 OpenAI SDK 在客户端会把它**解析为 Python `dict`**,业务侧无需自行 `json.loads`。详见下文"适配要点"。

**关键字段对照表:**

| 字段 | 来源 chunk | 说明 |
|------|-----------|------|
| `id` / `model` / `created` / `system_fingerprint` | 所有 chunk 顶层 | 响应级元数据 |
| `message.role` | `delta.role`(只在首块) | `"assistant"` |
| `message.content` | `delta.content` 累积 | 普通文本 |
| `message.refusal` | `delta.refusal` 累积 | 拒绝文本 |
| `message.tool_calls[]` | `delta.tool_calls[]` 累积 + 流结束解析 | 工具调用,`arguments` 在 SDK 内已 `json.loads` |
| `message.annotations` | 通常只在非流式出现 | web_search 引用标注 |
| `finish_reason` | 最后一个内容 chunk | 结束原因 |
| `usage` | 终态 chunk(若 `include_usage`) | token 统计 |

> 💡 **适配要点**:OpenAI SDK 在客户端已经把 `tool_calls[*].function.arguments` 从 JSON 字符串解析成了 Python `dict`,业务侧可直接 `call.arguments["location"]`,无需自行 `json.loads`。

### 3.1 工具声明侧(`tools` 数组)

OpenAI 的工具声明结构是 `tools: [{"type": "function", "function": {...}}]`:

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Get the current weather in a given location",
    "strict": true,
    "parameters": {
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
      "required": ["location"],
      "additionalProperties": false
    }
  }
}
```

**字段说明:**

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | ✅ | 当前仅支持 `"function"`(未来可能支持 `"custom"` 用于 freeform 工具) |
| `function.name` | ✅ | 函数名,`a-zA-Z0-9_-`,**最长 64 字符** |
| `function.description` | 推荐 | 模型选择该函数的依据,应尽量具体 |
| `function.parameters` | ❌ | JSON Schema 对象;省略或 `{}` 表示无参;**`strict: true` 时必须满足严格模式(见下)** |
| `function.strict` | ❌ | 是否启用 Structured Outputs 严格模式,推荐 `true` |

**`strict: true` 下的硬约束:**

- 顶层 `parameters` 必须为 `object`,且 `additionalProperties: false`
- 所有字段都必须出现在 `required` 数组里(可选字段也得列出)
- 可空字段用 `anyOf` 表示,例如:

  ```json
  "optional_field": {
    "anyOf": [
      { "type": "string" },
      { "type": "null" }
    ]
  }
  ```
- 支持 `enum` / `const` / `$ref` / `$defs` / `$schema` / `definitions`
- ❌ 不支持: 任意键值、unevaluatedProperties、`patternProperties`、正则表达式

### 3.2 强制选择工具(`tool_choice`)

四种取值示意(实际请求中只能选其一):

| 取值 | 行为 |
|------|------|
| `"none"` | **禁止**调用任何工具 |
| `"auto"`(默认) | 模型自行决定 |
| `"required"` | **必须**调用至少一个工具(不限定哪个) |
| `{"type":"function", "function":{"name":"..."}}` | **必须**调用指定函数 |

对应的请求字段示例:

```text
tool_choice = "none"        → { "tool_choice": "none" }
tool_choice = "auto"        → { "tool_choice": "auto" }
tool_choice = "required"    → { "tool_choice": "required" }
tool_choice = 强制指定函数  → {
  "tool_choice": {
    "type": "function",
    "function": { "name": "get_weather" }
  }
}
```

> ⚠️ `"required"` 会让 `finish_reason` 固定为 `"tool_calls"`(只要开了工具)。OpenAI **没有** Anthropic 那种 `"any"` + `"tool"` 区分 — `"required"` 兼二者之职。

### 3.3 模型调用工具意图(`assistant` 消息 + `tool_calls`)

模型决定调用工具时,会在 `message.tool_calls` 数组里输出,可选地在 `message.content` 里附带文本解释:

```json
{
  "role": "assistant",
  "content": "I'll help you check the current weather and time in San Francisco.",
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "get_weather",
        "arguments": "{\"location\":\"San Francisco, CA\"}"
      }
    }
  ]
}
```

注意每个 `tool_call` 都有独立的 `id`,**业务侧后续必须原样回传到 `tool` 消息的 `tool_call_id`**。

### 3.4 工具结果回传(`role: "tool"` 消息)

业务侧执行完工具后,把结果作为一条 **`role: "tool"`** 消息回传(注意不是 `user`!),通过 `tool_call_id` 对齐:

```json
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "San Francisco: 65°F, partly cloudy."
}
```

**多个并行工具调用的回传:** 每个 tool_call 必须回传一条独立的 `tool` 消息,**顺序与调用顺序一致**:

```json
[
  { "role": "assistant", "content": null, "tool_calls": [
      { "id": "call_001", "type": "function", "function": { "name": "get_weather", "arguments": "{\"location\":\"北京\"}" } },
      { "id": "call_002", "type": "function", "function": { "name": "search_docs",  "arguments": "{\"query\":\"北京 天气\"}" } }
  ]},
  { "role": "tool", "tool_call_id": "call_001", "content": "晴,22°C" },
  { "role": "tool", "tool_call_id": "call_002", "content": "找到 5 条相关文档..." },
  { "role": "assistant", "content": "北京今天晴,22°C;相关文档显示近期有轻度污染。" }
]
```

> 与 Anthropic 不同:**OpenAI 的 tool 结果消息是独立的一条 `role: "tool"`,不能在同一条消息里再追加 `text` 追问**。追问需要再发一条 `role: "user"` 消息。

---

## 4. 注意事项

| # | 说明 |
|---|------|
| 1 | **`data: [DONE]` 是流的结束信号**,业务侧应在收到后立即停止解析,不要继续等待 |
| 2 | **工具参数是字符串**:即便后续 SDK 已解析,在线协议层 `function.arguments` 始终是 JSON 字符串;若自行解析需在**流完全结束**后再做 |
| 3 | **`finish_reason` 仅在最后一个内容 chunk 出现一次**,不要在每个 chunk 里都期望它存在 |
| 4 | **空 `choices` 的 usage chunk**:开了 `include_usage` 时,最后一个 chunk 的 `choices: []`,要靠 `chunk.usage` 而非 `chunk.choices[0]` 取 token |
| 5 | **`tool_calls` 第一个 delta 才有 `id` 和 `name`**:后续 delta 只携带 `arguments` 片段,**按 `index` 聚合**而非按"对象相等" |
| 6 | **`strict: true` 的 schema 约束**:所有字段(包括可选)都必须列在 `required`,nullable 字段用 `anyOf` 双类型表示 |
| 7 | **`reasoning_tokens` 仅是计数**:o-series 模型(o1/o3 等)的内部推理在流式协议里**不暴露文本**;如要看 reasoning 摘要,需要 `summary: "auto"` 参数,且仅在响应完成后才有 |
| 8 | **`refusal` 走独立字段**:拒绝响应**不写入 `content`**;业务侧需同时检查 `delta.content` 与 `delta.refusal` |
| 9 | **多 choice 场景**:请求带 `n > 1` 时,每个 chunk 的 `choices` 数组会包含多条,各条带独立 `index`;聚合时要按 `choices[i].delta.content` 分流 |
| 10 | **请求侧可关并行**:顶层 `parallel_tool_calls: false` 强制模型每次只调一个工具(默认允许并行) |

---

## 5. 速查表

### 5.1 Chunk 顶层

| 字段 | 出现位置 | 用途 |
|------|---------|------|
| `id` | 所有 chunk | 响应唯一 ID,跨 chunk 一致 |
| `object` | 所有 chunk | 字面量 `"chat.completion.chunk"` |
| `created` | 所有 chunk | Unix 时间戳,跨 chunk 一致 |
| `model` | 所有 chunk | 模型名 |
| `choices` | 所有内容 chunk | 增量数据,终态 chunk 可能为空 |
| `usage` | 最后一个 chunk(若 `include_usage`) | token 统计 |
| `system_fingerprint` | 所有 chunk | 后端指纹(可选) |
| `service_tier` | 所有 chunk | 服务层级(可选) |

### 5.2 Delta 字段层

| `delta.*` 字段 | 类型 | 用途 | 出现规则 |
|---------------|------|------|---------|
| `role` | `"assistant"` | 角色标识 | **仅首块** |
| `content` | string | 文本增量 | 文本生成期间持续出现 |
| `refusal` | string | 拒绝内容 | 仅在拒绝时出现 |
| `tool_calls` | array | 工具调用增量 | 工具调用期间持续,按 `index` 分片 |

### 5.3 Delta.tool_calls 元素层

| 字段 | 出现规则 |
|------|---------|
| `index` | 每个 tool_call 自始至终**固定** |
| `id` | **仅首 chunk** 携带 |
| `type` | `"function"` |
| `function.name` | **仅首 chunk** 携带 |
| `function.arguments` | JSON 字符串,**分片流式** |

### 5.4 终止信号

| 信号 | 来源 | 处理 |
|------|------|------|
| `choices[0].finish_reason != null` | 最后一个内容 chunk | 标记本轮业务侧需执行工具或结束 |
| `chunk.choices == []` + `chunk.usage` | 终态 usage chunk(若开启) | 提取 token 统计 |
| `data: [DONE]` | SSE 末尾 | 立即停止解析 |

---

## 6. 完整处理示例(Python 伪代码)

```python
import json

full_text     = ""
tool_args_buf = {}   # {tool_index: arguments_string}
tool_meta     = {}   # {tool_index: {id, name, type}}
refusal       = ""
finish_reason = None
usage         = None

for line in stream.iter_lines():
    if not line or not line.startswith("data: "):
        continue
    payload = line[len("data: "):]
    if payload.strip() == "[DONE]":
        break

    chunk = json.loads(payload)

    # 1. usage 仅在终态 chunk(且 choices 为空)出现
    if chunk.get("usage"):
        usage = chunk["usage"]
        continue

    if not chunk["choices"]:
        continue

    delta = chunk["choices"][0]["delta"]
    fr    = chunk["choices"][0].get("finish_reason")
    if fr:
        finish_reason = fr

    # 2. 文本增量
    if delta.get("content"):
        full_text += delta["content"]

    # 3. 拒绝内容
    if delta.get("refusal"):
        refusal += delta["refusal"]

    # 4. 工具调用增量(按 index 聚合)
    for tc in (delta.get("tool_calls") or []):
        i = tc["index"]
        if tc.get("id"):
            tool_meta[i] = {
                "id":   tc["id"],
                "type": tc.get("type", "function"),
                "name": tc["function"]["name"],
            }
        if tc.get("function", {}).get("arguments"):
            tool_args_buf[i] = tool_args_buf.get(i, "") + tc["function"]["arguments"]

# 5. 流结束后,解析每个 tool_call 的参数
tool_calls = [
    {**tool_meta[i], "arguments": json.loads(tool_args_buf[i])}
    for i in sorted(tool_meta)
]

# 6. 业务侧处理
if finish_reason == "tool_calls":
    for tc in tool_calls:
        result = execute(tc["name"], **tc["arguments"])  # ← 真正执行
        # 然后把 {"role":"tool","tool_call_id":tc["id"],"content":result}
        # 追加到 messages 后再次请求
elif finish_reason == "stop":
    display(full_text)
elif finish_reason == "length":
    warn("输出被 max_tokens 截断")
elif finish_reason == "content_filter":
    fallback_to_safe_response()
```