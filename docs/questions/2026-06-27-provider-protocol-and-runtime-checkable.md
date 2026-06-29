---
status: answered
tags: [python, typing, protocol, runtime-checkable]
created: 2026-06-27
answered: 2026-06-27
related:
  - 2026-06-27-protocol-vs-abc-design-choice.md
  - 2026-06-27-backend-tui-decoupling-points.md
---

# `furflycode.llm` 这个模块里的 `Provider` 是什么？`@runtime_checkable` 是什么？

## 背景

第一次看 `src/furflycode/llm/__init__.py` 时，里面定义了好几个东西：
`Message`、`StreamEvent`、`Provider`、`new_provider`。一开始以为是个"类"，后来才意识到
这是个**协议层模块**。

## 当时的想法

- 以为 `Provider` 是一个抽象基类，要求具体类必须继承。
- 不理解 `@runtime_checkable` 装饰器的作用，看到名字猜是"运行时检查是不是实现了"。

## 解答

### 模块整体是协议层（4 个东西）

| 定义 | 作用 |
|---|---|
| `Message`（dataclass） | 一条聊天消息：`role` + `content` |
| `StreamEvent`（dataclass） | 流式输出的统一事件：`text / done / err` |
| `Provider`（Protocol） | 与协议无关的 provider **接口契约** |
| `new_provider()`（工厂函数） | 根据 `protocol` 字段分发到具体实现 |

关键价值是**解耦**：TUI 导入的是抽象的 `Provider`，**从来不导入** `AnthropicProvider` 或
`OpenAIProvider`。具体用哪个由 `new_provider()` 在运行时根据配置决定。

### `Provider` 是个 `Protocol`，不是类

`Protocol` 是 Python 的结构化类型（静态鸭子类型）：

> 一个类**不需要继承** `Provider`，只要它长着 `name`、`model` 属性和 `stream()` 方法，
> 类型检查器就认为它满足 `Provider`。`AnthropicProvider` 和 `OpenAIProvider` 都没继承它，
> 但都"长得像"，所以都算 `Provider`。

### `@runtime_checkable` 是什么

`Protocol` 默认**只在静态类型检查时有效**（mypy/pyright 能识别），运行时
`isinstance(x, Provider)` 会**报错**。`@runtime_checkable` 这个装饰器允许运行时做
`isinstance` 检查：加了之后，`isinstance(x, Provider)` 不会报错，而是按"有没有这些
属性/方法"来判断真假。

### 重要陷阱

`@runtime_checkable` 的运行时检查**只看属性/方法是否存在，不看签名**。即使 `stream` 的
签名完全不对，只要这个名字存在，`isinstance` 就返回 `True`。所以：

- 运行时检查只能确认"支持协议"，不能确认"协议正确"。
- 真正的签名校验只能靠 mypy/pyright 静态做。

### 本项目为什么加它？

1. **留个运行时自检的口子**：万一以后想做 `assert isinstance(p, Provider)`，加了就能用。
2. **表达意图 + 零成本**：声明"这个 Protocol 可能在运行时被查询"，几乎没副作用。

不过当前代码**没有真正用到** `isinstance(..., Provider)`。它现在主要是静态类型契约 +
解耦价值，运行时检查能力是预留的。

## 决策

- 不要去给 `Provider` 加继承关系或 `super()` 调用——它就是形状契约。
- 不要在生产路径里依赖 `isinstance(..., Provider)` 做契约校验。
- 签名相关的契约全部交给 mypy（在 `pyproject.toml:25` dev 依赖里有）。

## 参考

- `src/furflycode/llm/__init__.py:6, 28-53` —— Protocol + 装饰器定义
- `src/furflycode/llm/anthropic_provider.py:18-39` —— 满足形状的具体实现
- `src/furflycode/llm/openai_provider.py` —— 满足形状的具体实现
- `pyproject.toml:25` —— mypy dev 依赖