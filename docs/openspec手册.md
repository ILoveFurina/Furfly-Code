# Furfly Code 的 OpenSpec 手册（从零到能加 agent loop）

> 写给完全不懂 openspec 的你。你在 Claude Code 里用 `/opsx:` 系列技能干活，**全程不用手敲 openspec 命令**。这份手册告诉你：想加一个功能（比如 agent loop）时**对 Claude 说什么话**、**该用哪个 `/opsx:` 技能**、**这个技能背后替你跑了什么**、以及**怎么看懂它吐出来的东西**。
>
> 本手册所有"幕后命令"都在本项目（`E:\Furfly-Code`，schema = `spec-driven`）实测过，但**你不需要敲它们**——技能会替你跑。列出来只是为了让你看懂输出。

---

## 0. 一句话理解 openspec

**openspec = "先写规格，再写代码"的工作流工具。**

你不直接让 AI 敲代码，而是先用 `/opsx:propose` 让 AI 把"要做什么"写成一套**规格文档**，审一遍，再用 `/opsx:apply` 按 tasks 一步步实现，最后用 `/opsx:archive` 归档并把规格合并进项目的"主规格库"。

好处：每个功能都有一份可追溯的规格，半年后还能看懂"当时为什么这么设计"；新功能要改老行为时，能对着主规格精确说"改这一条"。

---

## 1. 你只有 4 个技能要用（记住这四个就够）

| 技能 | 你什么时候用 | 一句话作用 |
|---|---|---|
| `/opsx:explore` | 还没想清楚，想先理一理 | 思考搭档，不建文件 |
| `/opsx:propose` | 想清楚了，要立提案 | **一次性**建 change 并生成全部规格文档（proposal+spec+design+tasks） |
| `/opsx:apply` | 提案审过了，要写代码 | 按 tasks 逐条实现，边做边勾 |
| `/opsx:archive` | 代码写完了，要收尾 | 校验 + 归档 + 把规格合并进主规格库 |

> 还有个 `/opsx:sync`（只合并规格、不归档），少见，先不用管。
>
> **正常流程就是 `propose → (审) → apply → archive` 四步**，对应 4 个技能。下文每步都展开。

---

## 2. 心智模型：三个层（先记住这张图）

openspec 在你仓库的 `openspec/` 目录下分三层，**别混**：

```
openspec/
├── specs/                          ← ① 主规格库（系统"现在"的完整规格，长期存在）
│   ├── chat-client/spec.md
│   └── tool-system/spec.md
├── changes/                        ← ② 变更工作区（正在做或已做完的"提案"）
│   ├── <某个正在做的 change>/      ← 活跃 change（还没归档）
│   └── archive/                    ← 已归档的历史提案
│       ├── 2026-06-29-multi-protocol-chat-client/
│       ├── 2026-06-29-tool-system/
│       └── 2026-06-29-refactor-tool-types/
└── config.yaml                     ← 配置：用哪个 schema（我们用 spec-driven）
```

- **① 主规格库 `specs/`**：一个 capability（能力）= 一个文件夹 = 一份 `spec.md`。它是**归档时自动合并出来的**，归档后永久待在这。⚠️ 看到它在这别以为"没归档"——它正是归档成功的产物。
- **② 变更工作区 `changes/`**：你要加/改功能，`/opsx:propose` 就在这建一个 change 文件夹，里面放规格文档。归档后整个文件夹被挪进 `archive/`。
- **③ 归档区 `changes/archive/`**：历史提案，命名固定 `YYYY-MM-DD-<change名>/`，纯存档不再变动。

> **一句话区分**：`specs/` 是"现在的规格"，`changes/archive/` 是"过去的提案"。归档时把提案里的"改动清单（delta）"合并进 specs。

---

## 3. 一个 change 里的四种文档（spec-driven schema）

`/opsx:propose` 一次性在 change 文件夹里生成 4 个文档，有依赖关系：

```
proposal.md  ──┬──> specs/<cap>/spec.md   ──┐
               └──> design.md              ─┴──> tasks.md
```

| 文档 | 回答什么 | 你审的时候关注什么 |
|---|---|---|
| `proposal.md` | **为什么**做 | `Capabilities` 节：声明新建还是修改哪个 capability（这是契约，后面 spec 照着建） |
| `specs/<cap>/spec.md` | 系统该做**什么**（需求+场景） | **最严格**，格式错了会静默失败（见第 7 节坑） |
| `design.md` | **怎么**实现（架构/决策） | Context / Goals-Non-Goals / Decisions / Risks |
| `tasks.md` | 实现任务**清单**（checkbox） | 每条 `- [ ]`，apply 阶段靠它追踪 |

### 3.1 spec.md 的格式铁律（最容易踩坑，背下来）

```markdown
## ADDED Requirements          ← 顶层用 delta 操作标记（见 3.2）

### Requirement: 配置加载      ← 恰好 3 个 #，需求名
系统 SHALL 从 YAML 配置读取 providers 列表……   ← 用 SHALL/MUST，不用 should/may

#### Scenario: 合法配置解析为 providers 列表   ← 恰好 4 个 #！不能是 3 个或 bullet！
- **WHEN** 存在合法的 config.yaml 且字段齐全
- **THEN** 系统解析出正确条数的 providers 并继续启动
```

**硬规则：**
1. 每条 Requirement **必须有至少 1 个 Scenario**。
2. Scenario **必须正好 4 个 `#`**（`####`）。写成 3 个 `#` 或 bullet 会**静默失败**（openspec 不报错但不认这条场景）。
3. 规范语气用 **SHALL / MUST**，不要用 should / may。
4. 每个 Scenario 是一个潜在测试用例，要可测。

> 这些规则你不用背到能写——`/opsx:propose` 替你按规矩写。但你要会**审**：review 时看到 `###` 数错或没 Scenario，就让它改。

### 3.2 delta 操作（spec 变更的四种动作）

`specs/<cap>/spec.md` 顶层用 `## XXX Requirements` 声明这次对 capability 做什么：

| 标记 | 含义 | 注意 |
|---|---|---|
| `## ADDED Requirements` | 新增需求 | 新 capability 用这个 |
| `## MODIFIED Requirements` | 改了既有需求的行为 | **必须贴整条更新后的内容**（不是只写改了哪句）；header 文本要和主 spec 里的一致 |
| `## REMOVED Requirements` | 删除需求 | 必须写 **Reason** 和 **Migration** |
| `## RENAMED Requirements` | 只改名 | 用 `FROM:` / `TO:` 格式 |

> step1/step2 是新 capability，全用 `ADDED`。下面 agent loop 会用到 `MODIFIED`（把"单轮闭环"改成"多轮 loop"）。

---

## 4. 完整工作流（skill 驱动，4 步）

你正常加一个功能就这 4 步。每步标了：**你说什么** / **技能干了啥** / **openspec 幕后跑什么**（不用你敲，看懂即可）/ **怎么看输出**。

### Step 1（可选）探索澄清 —— `/opsx:explore`
- **你说**：`/opsx:explore 我想加 agent loop，先帮我把边界理清楚`（或直接用自然话说"用 openspec 探索一下 agent loop"）。
- **技能干啥**：不建任何文件，当你的思考搭档，帮你在写提案前理清需求、边界、非目标。
- **幕后**：无 openspec 命令，纯对话。
- **怎么看**：一段对话式分析，没有副作用。

### Step 2 立提案 —— `/opsx:propose`
- **你说**：`/opsx:propose 加 agent loop：把 step2 tool-system 的单轮闭环改成多轮工具循环，模型拿工具结果后可继续调用，直到给出最终答复或达循环上限。change 名叫 agent-loop，修改 tool-system capability。`
- **技能干啥**：**一次性**建 change 文件夹并生成全部 4 个文档（proposal + specs + design + tasks），全部按第 3 节规矩写好。
- **幕后**（技能替你跑，你不用敲）：
  ```
  openspec new change agent-loop                          → 建 changes/agent-loop/
  openspec status --change agent-loop --json              → 看该写哪个文档
  openspec instructions proposal/specs/design/tasks ...   → 拿每个文档的模板+规则
  （技能按模板写出 4 个文件）
  ```
- **怎么看**：`changes/agent-loop/` 下出现 4 个文件。技能会回报"写了哪些文件、Requirement/Scenario 数量"。这时 change 处于"等审"状态。

### Step 2.5 review（别跳过）
- **你说**：`把 agent-loop 的 proposal 和 spec 念给我听，我审一下。`
- **技能/Claude 干啥**：读 change 里的文档贴给你。你重点审：
  - `## MODIFIED Requirements` 下"单轮闭环"那条是否**整条**更新成"多轮循环"（不能只写"改成多轮"）。
  - 每条 Requirement 有没有 `#### Scenario`（4 个 #）。
  - 循环上限、终止条件这些新需求在不在 `## ADDED Requirements`。
- 不满意就说"把第 X 条改成 ……",让它改完再往下。

### Step 3 实施 —— `/opsx:apply`
- **你说**：`/opsx:apply agent-loop`（或"实施 agent-loop 这个 change"）。
- **技能干啥**：按 `tasks.md` 逐条写代码，每做完一条把 `- [ ]` 改成 `- [x]`，遇阻塞暂停问你。
- **幕后**：`openspec instructions apply --change agent-loop`（拿到 apply 指令，然后改代码 + 勾 tasks）。
- **怎么看**：`tasks.md` 里勾越来越多，全 `[x]` 即实施完成。代码改动你照常看 diff。

### Step 4 验证 + 归档 —— `/opsx:archive`
- **你说**：`/opsx:archive agent-loop`（或"validate 一下 agent-loop 然后归档"）。
- **技能干啥**：先校验格式，再把 change 挪进 `archive/`，并把 delta spec **合并进 `specs/` 主规格库**。
- **幕后**：
  ```
  openspec validate agent-loop --strict    → 校验 spec 格式
  openspec archive agent-loop --yes        → 归档 + 同步主 spec
  ```
- **怎么看**：归档输出一段 JSON，重点是这几行：
  ```json
  { "archive": { "change": "agent-loop", "archivedAs": "2026-06-29-agent-loop",
    "specsUpdated": true,
    "totals": { "added": 3, "modified": 1, "removed": 0, "renamed": 0 } } }
  ```
  - `specsUpdated: true` = 主 spec 被更新了。
  - `added/modified/removed/renamed` = 主 spec 这次被加/改/删/改名了几条需求。
  - `modified: 1` 就是"单轮→多轮"那条被改了，`added: 3` 是新增的循环上限等。

> 走完这 4 步，主 spec `specs/tool-system/spec.md` 已是"多轮循环"版本，change 躺进 `archive/`，结束。

---

## 5. 实战：用 openspec 加「agent loop」（完整走一遍）

> 背景：step2 的 tool-system spec 里 F6 写的是"单轮闭环……不做连环调用，Agent Loop 留待下一章"。agent loop 就是把这条改成"多轮循环"。这是个**修改既有 capability** 的例子，用到 `MODIFIED Requirements`，比之前全 `ADDED` 的 step1/step2 更进一步。

### 5.1 决定 capability 归属
agent loop 改的是 tool-system 的编排行为（单轮→多轮），所以：
- **Modified Capabilities**：`tool-system`（改它的 F6 那条，可能再加几条新需求如"循环上限""终止条件"）。
- 不是新 capability（不建 `specs/agent-loop/`），而是改 `specs/tool-system/spec.md`。

### 5.2 你对 Claude 说的话（按顺序）

**① 立提案**
> `/opsx:propose 加 agent loop：把 step2 tool-system 的单轮闭环改成多轮工具循环，模型拿工具结果后可继续调用工具，直到给出最终答复或达到循环上限。change 名叫 agent-loop，修改 tool-system capability。`

技能一次性建 `changes/agent-loop/` 并写出 proposal / specs/tool-system/spec.md / design / tasks 四件套。

**② review**
> `把 agent-loop 的 proposal 和 spec 念给我听，我审一下。`

重点看 `## MODIFIED Requirements` 那条是否**整条**更新、`#### Scenario` 有没有写漏、新需求（循环上限/终止）在不在 `## ADDED Requirements`。不满意让它改。

**③ 实施**
> `/opsx:apply agent-loop`

技能按 tasks 改代码（主要改 `src/furflycode/agent/__init__.py` 的 `run`：把"请求#2 后停"改成"循环到无 tool_calls 或达上限"），边做边勾 `[x]`。

**④ 验证 + 归档**
> `/opsx:archive agent-loop`

技能跑 validate + archive。你看到的归档输出：
```json
{ "archive": { "change": "agent-loop", "archivedAs": "2026-06-29-agent-loop",
  "specsUpdated": true, "totals": { "added": 3, "modified": 1, "removed": 0 } } }
```
`modified: 1` = 单轮→多轮那条；`added: 3` = 新增的循环上限等。

### 5.3 事后核对（想看就让你看）
跟 Claude 说"看下 tool-system 现在的规格"，背后跑 `openspec show tool-system`，主 spec 里那条已是"多轮循环"。

---

## 6. 幕后命令参考（你不用敲，看得懂输出就行）

`/opsx:` 技能在背后替你跑这些。列出来是为了某天技能输出里冒出某个命令名时，你知道它在干嘛。

| 幕后命令 | 干什么 | 技能什么时候调 |
|---|---|---|
| `openspec new change <名>` | 建一个 change 文件夹 | propose 开头 |
| `openspec status --change <名> --json` | 看 artifact 完成状态 | propose 每写完一个文档后 |
| `openspec instructions <文档> --change <名>` | 拿该文档的模板+规则 | propose 写每个文档前 |
| `openspec validate <名> [--strict]` | 校验格式 | archive 前必跑 |
| `openspec archive <名> --yes` | 归档 + 同步主 spec | archive |
| `openspec archive <名> --yes --skip-specs --no-validate` | 归档但不动主 spec、跳过校验 | **纯重构/文档类** change（见第 7.3 坑） |
| `openspec show <名>` | 看一个**活跃** change 或 spec | review 时 |
| `openspec list` / `--specs` | 列活跃 changes / 列主 specs | 想看现状 |
| `openspec doctor` | 检查 openspec 根健康 | 排查结构问题 |

> ⚠️ 归档后的 change 用 `openspec show <名>` 查不到（只认活跃 change）；要看历史就读 `changes/archive/<日期>-<名>/` 下的文件。

---

## 7. 常见坑（本项目实测）

1. **`####` 必须 4 个 `#`**：spec 的 Scenario 写成 3 个 `#` 或 bullet，openspec **不报错但不认**，归档时那条场景就丢了。review 时当心，让技能用 `--strict` 校验。

2. **MODIFIED 要贴整条**：改既有需求时，必须把**整条 Requirement（含所有 Scenario）**更新后内容贴进 `## MODIFIED Requirements`，不能只写"把单轮改多轮"。只写局部，归档合并时丢细节。

3. **纯重构没有 spec delta 怎么归档**：`spec-driven` 要求 change 至少有一个 delta，否则校验报 `No deltas found`。行为零变化的纯重构（如 step3 类型归位）归档时跟 Claude 说"这是纯重构，归档时跳过 spec 同步和校验"，让它用：
   ```
   openspec archive <名> --yes --skip-specs --no-validate
   ```
   `--skip-specs` = 不动主 spec，`--no-validate` = 跳过强校验。这是为 infra/tooling/doc-only 变更设计的正路。

4. **主 spec 的 `## Purpose` 是 `TBD`**：归档时 openspec 自动生成一句 `Purpose: TBD - ...`。不影响校验，但有空让它补一句描述该 capability 干嘛的。

5. **归档后的 change `openspec show` 查不到**：要看历史直接读 `changes/archive/<日期>-<名>/` 下的文件。

6. **capability 名一旦归档就难改**：它变成 `specs/<名>/` 目录名，后续 change 引用它要写对。起名用 kebab-case，想清楚（如 `chat-client`、`tool-system`）。

7. **改代码 ≠ 改 spec**：只动实现、行为没变（重构、性能优化），不要碰 spec，走 step3 那种 spec-less 归档。spec 只记"系统该做什么"的**行为契约**。

---

## 8. 决策树：我现在该用哪个技能？

```
要加/改一个功能？
├─ 还没想清楚 → /opsx:explore
├─ 想清楚了，要立提案 → /opsx:propose        （一次性产出四件套）
│   └─ 提案写完，review → 让 Claude 念给你听，不满意让它改
├─ 提案过了，要写代码 → /opsx:apply          （按 tasks 实现）
├─ 代码写完，要收尾 → /opsx:archive          （校验 + 归档 + 同步主 spec）
│
只是重构/改实现，行为不变？
└─ 不写 spec delta，归档时让 Claude 用 --skip-specs --no-validate

只想看现状？
├─ 让 Claude "看下有哪些活跃 change / 有哪些 capability"
│   （背后 openspec list / openspec list --specs）
├─ 让 Claude "看下某 capability 现在的规格"
│   （背后 openspec show <cap>）
└─ 让 Claude "检查下 openspec 健康吗"
    （背后 openspec doctor）
```

---

## 9. 本项目当前状态（2026-06-29）

- 主 specs：`chat-client`（20 条 requirement）、`tool-system`（20 条）。
- 归档历史：`2026-06-29-multi-protocol-chat-client`、`2026-06-29-tool-system`、`2026-06-29-refactor-tool-types`。
- 活跃 change：无。
- 下一个功能（agent loop）照第 5 节走即可。
