---
status: answered
tags: [python, design, protocol, abc, oop]
created: 2026-06-27
answered: 2026-06-27
related:
  - 2026-06-27-provider-protocol-and-runtime-checkable.md
---

# 为什么不把 `Provider` 做成抽象基类（ABC）？

## 背景

看到 `Provider` 用 `Protocol` 实现，第一反应是"ABC 不是更强制、更安全吗？"

## 当时的想法

直觉：

- ABC 有 `@abstractmethod`，子类不实现就连实例化都报错——更强。
- Protocol 的"鸭子类型"太松散，没继承也能算实现。
- 既然要"强制契约"，选 ABC 不是更稳？

## 解答

### 核心区分

- **Protocol = 形状契约**。认"**长得像不像**"，不要求继承。
- **ABC = 血缘契约**。认"**是不是一家人**"，必须显式继承。

### 为什么这个项目用 Protocol 更合适

**1. Provider 是"形状契约"，不是"身份"**

TUI 只关心对象能 `.stream()`、有 `.name`/`.model`。它在不在乎对象是不是继承自某个祖宗，
这正是 Protocol 表达的。Protocol 让 provider 实现可以完全独立——甚至把第三方 SDK 的
client 直接包一层就能用，不需要 `class XxxProvider(Provider)`。

**2. 强制力用静态检查就够，而且更准**

| 检查方式 | ABC (`@abstractmethod`) | Protocol (mypy) |
|---|---|---|
| 何时暴露问题 | 实例化时 `TypeError` | 写代码/CI 时 mypy 报错 |
| 检查"有没有"方法 | ✅ | ✅ |
| 检查"签名对不对" | ❌ 只看名字 | ✅ 参数/返回类型都查 |

项目装了 mypy（`pyproject.toml:25`），走静态检查路线更一致。ABC 的 `@abstractmethod`
反而只能在运行时、且只验"有没有"——比 mypy 弱。

**3. `@runtime_checkable` 已覆盖运行时自检需求**

万一以后要 `isinstance(p, Provider)`，Protocol 加装饰器就能用；ABC 在这点上没优势。

**4. 风格统一**

文件用 `@dataclass` 定义数据，`Protocol` 定义行为——都是声明式、轻量的现代 Python。
引入 ABC 会让风格变重。

### 什么时候 ABC 更好（诚实补充）

ABC 的真正优势是**能放共享实现**（混入逻辑、`super()` 调用链、MRO）。当前两个 provider
**有一点点重复**——`name` / `model` 两个 property 在 `anthropic_provider.py:33-39` 和
`openai_provider.py` 里是完全相同的两行代码。但这点重复**太小**，不值得为了它引入基类。
真正的差异（`stream()` 内部）因 SDK 而异，基类帮不上忙。

### 进阶方案：如果将来要演进

社区里常见的最佳实践是**两者结合**：

```python
# 对外契约：上层只认这个，不关心继承关系
@runtime_checkable
class Provider(Protocol):
    @property
    def name(self) -> str: ...
    def stream(self, msgs): ...

# 对内基类：放共享实现（name/model property、重试、计时、system prompt 注入）
class BaseProvider(ABC):
    def __init__(self, config):
        self._config = config
    @property
    def name(self) -> str:
        return self._config.name          # 写一次，所有子类复用
    @abstractmethod
    def stream(self, msgs): ...

# 具体实现：继承 BaseProvider 复用实现，自动满足 Provider 形状
class AnthropicProvider(BaseProvider):
    def stream(self, msgs): ...
```

## 决策

- 当前保持 Protocol。
- 触发改动的信号：**当在两个 provider 里第二次复制同一段逻辑时**，就抽 `BaseProvider`。
  在那之前，Protocol 是最轻、最契合现状的选择。

## 参考

- `src/furflycode/llm/__init__.py:28-53` —— `Provider` Protocol 定义
- `src/furflycode/llm/anthropic_provider.py:33-39` —— 重复的 `name`/`model` property
- `src/furflycode/llm/openai_provider.py` —— 同上
- `pyproject.toml:25` —— mypy dev 依赖
- 对照笔记：Protocol vs ABC 笔记（已合并到本疑问的解答里）