# CLAUDE.md 同步 hooks 设计

日期：2026-07-01
状态：已获批，待实施
委托：用户全权委托按最佳实践执行，不再逐段确认。

## 1. 背景与问题

本项目 CLAUDE.md 容易与实际代码脱节。活体样本：

- §3「关键设计」曾有「单轮上限：续答请求#2 忽略工具调用」，但 `add-agent-loop` 变更已把 Agent 改成 ReAct 自主多轮循环，该条已被代码推翻，CLAUDE.md 未同步（当前未提交改动里正在删它）。
- §2 曾有「配置：复制 config.yaml.example」命令，也已过时。
- §3 模块清单遗漏了 `conversation.py`、`prompt.py`、`context/` 三个实际存在的模块——结构性遗漏。

两类痛点（用户确认）：
- **检测过时**：代码变了，文档描述没跟上。
- **沉淀新知**：踩到新坑/确立新约定，没记进 CLAUDE.md。

## 2. 决策记录

| 决策点 | 选择 | 依据 |
|---|---|---|
| 目标层面 | 本项目自己的 CLAUDE.md | 用户在 Claude Code 下开发 Furfly Code 时用 |
| 自动化强度 | hooks 自动触发 | 不靠纯纪律 |
| 介入程度 | 只提示，人决定改不改 | 不自动改、不阻断提交 |
| 触发时机 | Stop（检测过时）+ SubagentStop（提示沉淀） | 两痛点对应两时机 |
| hook 类型 | `type: "prompt"` | Claude Code 用 LLM 跑 prompt、读 transcript，无需自管 API key |
| 输出形式 | `hookSpecificOutput.additionalContext` | 官方明确：Stop/SubagentStop 接受此字段做非阻断反馈 |
| CLAUDE.md 结构 | 重构：§7 挪到 `.claude/rules/`、§3 瘦身为指针式 | 对齐官方「根文件小而稳 + pointer > copy」 |

## 3. CLAUDE.md 重构方案

### 3.1 改动 A：§7 Spec 驱动 → `.claude/rules/spec-workflow.md`

新建 `.claude/rules/spec-workflow.md`，带 path-scoped frontmatter：

```markdown
---
paths:
  - "openspec/**"
---
# Spec 驱动开发流程

项目用 openspec 做 spec-driven 开发（见 `openspec/`：specs 在 `openspec/specs/`，归档变更在 `openspec/changes/archive/`）。
新功能/模块开发可用 `furfly-spec` 或 `openspec-*` skills 走 spec → plan → task → checklist 流程。
```

- `paths: ["openspec/**"]`：只在 Claude 读写 `openspec/` 下文件时加载，平时不占会话上下文。
- CLAUDE.md §4 Conventions 加一句指针：「openspec 工作流见 `.claude/rules/spec-workflow.md`」。
- **已知风险**：GitHub issue #16299 报告某些版本 path-scoped rules 仍全局加载。最坏情况是没省到 token，不影响正确性，可接受。

### 3.2 改动 B：§3 Architecture 瘦身为指针式

**模块清单**：从「展开描述」改成「一句职责 + 源码路径指针」。同时补齐当前遗漏的模块（`conversation.py`、`prompt.py`、`context/`）。

瘦身前后对比：

```
# 瘦身前（展开式）
- `message.py` — 协议无关传输词汇（Message/ToolCall/ToolResult/StreamEvent/ROLE_*）。中性叶子模块，任何层可依赖而不引入方向倒置。

# 瘦身后（指针式）
- `message.py` — 协议无关传输词汇（叶子模块，零内部依赖）。详见 `src/furflycode/message.py`。
```

**「关键设计」子节**：保留不动。这些是跨模块架构约束（Provider 适配器、工具结果回灌形状、thinking 与工具历史互斥、StreamEvent 四态），是 CLAUDE.md 独有价值——源码里读不出来的「为什么这么设计」。

### 3.3 重构后章节结构（6 节）

| § | 标题 | 变化 |
|---|---|---|
| 1 | Project Overview | 不动 |
| 2 | Commands | 不动 |
| 3 | Architecture | 瘦身：模块清单改指针式并补齐遗漏模块；「关键设计」保留 |
| 4 | Conventions | 加一句指针指向 spec-workflow rule |
| 5 | Hard Constraints | 不动 |
| 6 | Gotchas | 不动 |
| ~~7~~ | ~~Spec 驱动~~ | 删除，挪到 rules/ |

## 4. Hooks 设计

### 4.1 配置位置

注入项目级 `.claude/settings.local.json`，与既有 `permissions` 合并。不污染全局配置。

**取舍说明**：`.claude/settings.local.json` 被 Claude Code 自动 gitignore，hooks 配置不随仓库分享给其他贡献者。这与项目现状一致——该文件已积累本机个人的 permissions（含 tvly 临时授权等），本就是「本机本地」性质。用户确认的目标层面是「本项目自己的 CLAUDE.md」（个人开发时用），非团队共享，故放 `settings.local.json` 合理。若日后需团队共享 hooks，应迁到进 git 的 `.claude/settings.json`。

### 4.2 Stop hook（检测过时）

时机：每轮 Claude 回答结束。
目标：判断本轮改动是否让 CLAUDE.md 某条描述过时/失真。

输入可用字段：stdin JSON 含 `session_id`、`transcript_path`、`cwd`、`stop_hook_active`；环境变量 `$CLAUDE_PROJECT_DIR`。

输出契约：永远非阻断。无发现 → 空输出 + exit 0。有发现 → `{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "⚠️ ..."}}`。绝不返回 `decision: block`。

死循环防护：若 `stop_hook_active` 为 true，直接放行不判定（避免 hook 触发的续跑再次触发 hook 形成循环）。

### 4.3 SubagentStop hook（提示沉淀新知）

时机：子 agent 结束。
目标：判断子 agent 工作中是否产生值得沉淀进 CLAUDE.md 的新知识（§6 Gotchas / §5 Hard Constraints / §3 关键设计三类）。

输出契约同 Stop：永远非阻断，有发现走 `additionalContext`。

### 4.4 两 prompt 共性设计

- **变量引用**：prompt 内引用 `$TRANSCRIPT_PATH`、`$CLAUDE_PROJECT_DIR`，Claude Code 把实际值喂给 LLM。
- **永远 approve / 非阻断**：满足用户「只提示不阻断」硬要求；提示走 `additionalContext` 注入主会话，下一轮 Claude 可见，是否动 CLAUDE.md 由人决定。
- **严格输出 schema**：prompt 末尾钉死 JSON 形状，避免 LLM 自由发挥导致解析失败（解析失败→非阻断错误→提示丢失）。
- **timeout 30s**：prompt hook 默认 30s，够 LLM 读 transcript + CLAUDE.md + 出判断；超时算非阻断错误，最坏丢这次提示，不影响主流程。
- **按章节角色对照而非编号**：prompt 说「架构描述」「硬约束」「gotchas」等角色，不写死「§3」「§5」编号——以后章节调整不脆。

### 4.5 配置形状

```jsonc
{
  "permissions": { "allow": [ /* 既有，不动 */ ] },
  "hooks": {
    "Stop": [
      { "matcher": "*", "hooks": [
        { "type": "prompt", "prompt": "<stop prompt>", "timeout": 30 }
      ]}
    ],
    "SubagentStop": [
      { "matcher": "*", "hooks": [
        { "type": "prompt", "prompt": "<subagent prompt>", "timeout": 30 }
      ]}
    ]
  }
}
```

## 5. 错误处理与边界

| 情况 | 行为 |
|---|---|
| hook LLM 判断超时（>30s） | 非阻断错误，本次提示丢失，主流程继续 |
| hook 输出 JSON 解析失败 | 非阻断错误，提示丢失，主流程继续 |
| `stop_hook_active=true` | Stop hook 直接放行，不判定（防死循环） |
| transcript_path 不存在 | prompt 让 LLM 优雅降级：读不到就报无发现 |
| CLAUDE.md 读不到 | 同上，优雅降级 |
| path-scoped rules 撞 issue #16299 | 最坏 rules 全局加载没省 token，不影响正确性 |

## 6. 测试与验收

人工验收（hooks 是 LLM 行为，难自动化）：

1. **检测过时**：故意改一处架构（如调整模块职责），停轮后 Stop hook 应提示对应 CLAUDE.md 条目可能过时。
2. **沉淀新知**：派子 agent 探路踩一个新坑，结束后 SubagentStop 应提示可沉淀进 §6。
3. **不阻断**：两种情况下主流程都正常结束，不被 hook 拦截续跑。
4. **死循环防护**：连续多轮触发 Stop hook 不应卡死（block cap 8 次兜底 + `stop_hook_active` 判定）。
5. **重构正确性**：重构后 `uv run pytest` 全过、CLAUDE.md 行数下降、§7 内容在 rules 文件里完整保留。

## 7. 实施顺序

1. 写本设计文档并提交（已完成本步）。
2. 重构 CLAUDE.md：新建 `.claude/rules/spec-workflow.md`、瘦身 §3、删 §7、§4 加指针。
3. 跑 `uv run pytest` 确认重构未破坏测试（CLAUDE.md 不影响测试，但 spec 文件改动要验证）。
4. 改 `.claude/settings.local.json`：合并 hooks 配置。
5. 人工验收 1–4。
6. 提交。

## 8. 参考来源

- Anthropic 官方 Memory 文档：`code.claude.com/docs/en/memory`（CLAUDE.md 全文加载、>200 行降 adherence、`.claude/rules/` path-scoped、pointer > copy）
- Anthropic 官方 Hooks 文档：`code.claude.com/docs/en/hooks`（Stop/SubagentStop 接受 `hookSpecificOutput.additionalContext` 做非阻断反馈；`stop_hook_active` 防死循环；prompt-type hook）
- Anthropic 官方 hooks-guide：`code.claude.com/docs/en/hooks-guide`（prompt hook 用法、block cap）
- 本地 hook-development skill：`~/.claude/plugins/.../hook-development/SKILL.md`（prompt hook 配置形状）
- 社区共识：「5 个核心章节」（commands/architecture/hard rules/conventions/scope）— Medium/UX Planet/Dometrain 多篇趋同
- path-scoped rules bug：GitHub issue anthropics/claude-code#16299
