---
title: 实践出真知：为什么要采用openspec？
date: '2026-06-30 10:20:06'
tags:
- AI Coding
- Agent
- SDD
- 实践
mood: ''
cover: ''
description: 我在使用TDD in AI Coding的过程中，遇到了旧文档腐蚀上下文的情况。Agent的推理过程反复出现旧的design，其中包含过时的约束，等等。于是我开始思考怎么避免这个？

---

写这篇文章之前，我先承认一件事。

我曾经用 furfly-spec (我自己创建的skill)写过一份"完美"的 plan.md，详细到把函数名、文件路径、数据结构全都画了进去。当时觉得自己很专业。

然后过几天我重构了代码，忘了改文档。

然后 AI 的推理拿着这份旧文档来"参考"，固执地要把旧函数名塞回新代码里，又或是反复确认不敢改动 理由是——"spec 里写的就是这样"。

那一刻我才意识到：**一个写得"太完整"的 spec，本身就是一种上下文污染**。

这篇文章就是那次被旧文档反噬之后，我沉下心做的对比研究。技术内容比较多，我尽量写得人话一点。希望对正在研究SDD的你有帮助。

> 基于 Furfly Code（<https://github.com/ILoveFurina/Furfly-Code>）的实战对比。写于 2026-06-30。

* **furfly-spec** 是一份「四份文档顺序流水线 + 强审批闸门」：spec → plan → task → checklist，文档写完都堆在 `docs/features/<主题>/`，代码与文档长期共存，是我自己创建的SKILL
* **openspec** 是一份「变更包 + 主规格库」：每次改动产出一份 `proposal / spec-delta / design / tasks` 的变更，归档（archive）后**把 spec 的增量合入** `specs/<capability>/spec.md`，历史变更冻在 `changes/archive/`。
* **真正解你痛点的差异**：openspec 把「行为规格」和「实现设计」**物理隔离**到两个目录——`specs/` 永远只写 SHALL/MUST + Scenario 的行为，**没有函数名、没有文件路径、没有数据结构**；旧的设计、旧的代码细节归档后不再污染当前 AI 的上下文。
* **代价**：openspec 的格式规则更硬（`####` 必须四个井号、SHALL/MUST 关键词、delta 必须贴整条），心智成本比 furfly-spec 高一点。

> **赶时间的读者**：看完上面 4 条就够做决策了。想看论证可以跳到「三、七个维度的对比」看全景；想直接抄答案跳到「八、什么时候用哪个」。

---

## **一、你的痛点是什么**

> 原文：「再推进新功能的时候，比如重构代码，AI 的推理受到了这几个旧的 design 文档的影响。」

把这句话拆开看，里面其实有四件事搅在一起：

1. 旧的设计文档还**留**在仓库里（没归档、没冻结、没标记为「历史」）。
2. 这些旧设计里**带着实现细节**——函数签名、文件路径、数据结构名、模块名。
3. 重构之后代码已经变了，**文档没跟着变**。
4. AI 在读代码上下文时把旧文档**当成了当前事实**，于是把旧实现模式当成约束照搬，或者在每次重构时都先纠结「要不要回退到旧设计」。

这是一个**文档与代码双向漂移**问题。furfly-spec 的写法很容易触发它——后面会展开。openspec 的设计直接把这层耦合切断了。

> 如果你只遇到过一次类似问题，先别急着换工具——把旧 plan.md 删掉就能解决。但如果是反复出现的"老毛病"，那是 spec 工具的设计问题，得换。

---

## **二、两套规范的全貌**

### **2.1 furfly-spec：四份文档 + HARD GATE**

furfly-spec 把「想法 → 可运行代码」切成 4 份递进文档：

```
spec.md（做什么）→ plan.md（怎么做）→ task.md（按什么顺序做）→ checklist.md（做对了没）
```

每一份都要用户审批后才能进下一份，并且有一条强制闸门：

> **HARD GATE**：四份文档全部生成并获得用户批准之前，禁止编写任何实现代码。无论项目看起来多简单，一律走完流程。

四份文档都放在 `docs/features/<这次任务的中文概括主题>/` 下，跟代码并列存在。

各文档的职责（furfly-spec 自描述）：

| **文档**     | **回答什么** | **包含什么**                                                 |
| ------------ | ------------ | ------------------------------------------------------------ |
| spec.md      | 做什么       | 背景、目标、功能需求、非功能需求、边界、验收标准             |
| plan.md      | 怎么做       | 架构概览、组件划分、**核心接口与数据结构**、模块交互、技术决策 |
| task.md      | 按什么顺序做 | **文件清单**、有序任务列表、每个任务的步骤和验证方式         |
| checklist.md | 做对了没     | 可观测的行为检查、集成检查、端到端场景                       |

注意 plan.md 和 task.md 的措辞：**「核心接口与数据结构」「文件清单」**——这里就埋下了后面让你痛的根。

### **2.2 openspec：变更包 + 主规格库**

openspec 走的是另一条路。每个改动是一个**变更包**（change），变更包里有 4 份文档，归档时把其中的「spec 增量」**合入主规格库**：

```
openspec/
├── specs/                          ← 主规格库：系统"现在"的完整规格，长期存在
│   ├── chat-client/spec.md
│   ├── tool-system/spec.md
│   └── agent-loop/spec.md
└── changes/                        ← 变更工作区
    ├── <活跃 change>/              ← 还没归档的 change
    │   ├── proposal.md
    │   ├── design.md
    │   ├── tasks.md
    │   ├── specs/<cap>/spec.md     ← spec 增量（ADDED/MODIFIED/REMOVED/RENAMED）
    │   └── .openspec.yaml
    └── archive/
        └── YYYY-MM-DD-<name>/      ← 已归档：冻结的历史提案
```

4 份文档的分工：

| **文档**              | **回答什么**     | **关键约束**                                                 |
| --------------------- | ---------------- | ------------------------------------------------------------ |
| `proposal.md`         | 为什么做、改什么 | 声明新增/修改哪个 capability（这是**契约**）                 |
| `specs/<cap>/spec.md` | 系统该做什么     | **SHALL/MUST**，每条 Requirement 至少 1 个 `#### Scenario`（4 个 `#`） |
| `design.md`           | 怎么实现         | Context / Goals-Non-Goals / Decisions / Risks                |
| `tasks.md`            | 实现任务清单     | 复选框 `[ ]`，apply 阶段按它勾                               |

**关键设计**：spec 增量（`specs/<cap>/spec.md`）**只写行为**——不允许出现函数名、文件路径、类型签名。设计（`design.md`）才允许写实现细节。归档后，规范增量合并进主规格库，**design.md 跟着变更包一起冻在 archive/**，不再出现在「当前事实」里。

---

## **三、七个维度的对比**

> 全文最长的一节，但每一行都对比得比较密。如果只看一行结论也行——核心差异只有一条：**spec 和 design 在 openspec 里物理隔离，在 furfly-spec 里平级**。

| **维度**           | **furfly-spec**                                    | **openspec**                                                 |
| ------------------ | -------------------------------------------------- | ------------------------------------------------------------ |
| **文档数与流水线** | 4 份递进（spec→plan→task→checklist），每份都要过审 | 4 份并列（proposal/spec-delta/design/tasks），一次 review 整套 |
| **代码闸门**       | 强 HARD GATE，4 份全过才能写代码                   | 无强闸门，但 archive 前必跑 `openspec validate` 强制格式正确 |
| **spec 的内容**    | 写需求 + 验收标准，**不写实现**                    | 写 Requirement + Scenario（SHALL/MUST + WHEN/THEN），**绝对不写实现** |
| **实现设计放哪**   | `plan.md` 写在变更目录里，与 spec **平级**         | `design.md` 写在变更目录里，与 spec **分目录**（spec 在 `specs/`，design 在 `changes/`） |
| **文档归宿**       | 永远留在 `docs/features/<主题>/`                   | 归档时**合并** spec 增量进 `specs/<cap>/spec.md`，**冻结** design/proposal/tasks 进 `changes/archive/<日期>-<名>/` |
| **重构怎么走**     | 强制定 4 份文档（连"纯重构"也走）                  | 有后门：`openspec archive --skip-specs --no-validate`，纯重构/文档类可直接归档 |
| **组织视角**       | 以「功能/特性」为单位                              | 以「能力（capability）」为单位——一个 capability 是系统**长期存在**的一类行为，跨多个变更 |

### **3.1 spec 与 design 的关系（最关键）**

这是两者**最根本的差异**。

**furfly-spec**：spec.md 和 plan.md 摆在同一个目录里、同一层级。spec.md 写"做什么"，plan.md 写"怎么做（带函数签名、文件路径、数据结构）"。两者地位等同，没有"谁是当前事实"的区别。

**openspec**：spec 和 design 物理隔离——

* `specs/<cap>/spec.md` 是**主规格库**（当前事实），**永远只写行为**。
* `changes/<name>/design.md` 是**设计稿**（一次性提案），归档后冻结。

当你打开 openspec 项目读"系统现在该做什么"时，你只看 `specs/`。要追问"当年为什么这么实现"，你才钻进 `changes/archive/`。

这个隔离**直接对应你描述的痛点**——AI 不会把"老 design 里的函数名"当成"系统当前约束"，因为它物理上就不在 `specs/` 里。

### **3.2 文档归宿：合并 vs 堆积**

|                               | **furfly-spec**                                   | **openspec**                                                 |
| ----------------------------- | ------------------------------------------------- | ------------------------------------------------------------ |
| spec.md / specs/<cap>/spec.md | 留在 `docs/features/<主题>/spec.md` 永远不动      | 归档时**整段合并**进 `specs/<cap>/spec.md`                   |
| plan.md / design.md           | 留在 `docs/features/<主题>/plan.md` 永远不动      | 归档时**冻结**在 `changes/archive/<日期>-<名>/design.md`，不再改动 |
| task.md                       | 留在 `docs/features/<主题>/task.md` 永远不动      | 归档时**冻结**在 `changes/archive/<日期>-<名>/tasks.md`      |
| checklist.md                  | 留在 `docs/features/<主题>/checklist.md` 永远不动 | 没有对应物（验收逻辑直接来自 spec 的 Scenario）              |

后果：

* **furfly-spec** 的 `docs/features/` 越长越厚，越久越旧。半年后翻回去，谁也说不清哪些 spec 仍然有效、哪些 plan 已经过时。
* **openspec** 的 `specs/` 永远只有当前 capability 的主规格，全是合并后的最新内容；`changes/archive/` 是**只读**的历史档案。

> 这一条听起来很工程，但**直接对应了你描述的痛点**——文档"堆"着没人清理，正是 AI 被旧实现带跑的前提条件。

### **3.3 格式严格度**

|            | **furfly-spec**             | **openspec**                                                 |
| ---------- | --------------------------- | ------------------------------------------------------------ |
| 文档模板   | Markdown 模板，靠人/AI 自觉 | `openspec instructions <文档> --change <名>` 拿模板，CLI 校验 |
| 强制关键词 | 无                          | spec 必须 SHALL/MUST，Scenario 用 WHEN/THEN                  |
| 标题层级   | 没强约束                    | `#### Scenario` 必须**正好** 4 个 `#`（少了就静默失败）      |
| 校验机制   | 自检清单                    | `openspec validate --strict` 强制校验                        |
| 改既有需求 | 直接改对应小节              | `## MODIFIED Requirements` 必须**贴整条更新后内容**（不是只写 diff） |

openspec 的格式更硬，**好处是机器可读、可校验、可 diff**；**坏处是踩坑代价更高**（一个井号写错，spec 就被静默丢弃）。

> 写到这里插一句：踩过 `####` 写成 `###` 那个坑的人，才会明白"机器可校验"四个字的真实价值。

### **3.4 评审粒度**

|              | **furfly-spec**                  | **openspec**                                                 |
| ------------ | -------------------------------- | ------------------------------------------------------------ |
| 评审点       | 4 个，每份独立审批               | 1 个，整套 proposal/spec/design/tasks 一次过                 |
| 适合的场景   | 想把"做什么"和"怎么做"分两次拍板 | 想把"为什么 + 做什么 + 怎么做 + 任务清单"作为一个决策整体看  |
| 反复改的代价 | 中（改 plan 不会污染 spec）      | 改 proposal 会带动 spec 增量一起改，但只在当前 change 目录里 |

我自己的观察：**单点深度评审**（furfly-spec）vs **整包决策评审**（openspec）。前者更稳，后者更高效。

### **3.5 重构与文档-only 变更**

> 这一节是我写文章时最想分享的发现之一。openspec 给"行为不变的重构"留了一条正路，这是 furfly-spec 的 HARD GATE 永远做不到的。

这是 openspec 给我最意外的一个好设计。

* **furfly-spec** 的 HARD GATE 写着「四份文档全部生成并获得用户批准之前，禁止编写任何实现代码。无论项目看起来多简单，一律走完流程。」——纯重构也要写 4 份文档。

* **openspec** 给纯重构/文档类变更留了一个**正路后门**：

  ```
  openspec archive <名> --yes --skip-specs --no-validate
  ```

  `--skip-specs` = 不动主 spec；`--no-validate` = 跳过强校验。

看 Furfly Code 自己的 `2026-06-29-refactor-tool-types` 这个归档就是走的这条路——proposal 里直接写「**留空：纯内部重构，无新 capability**」「**留空：行为零变化，不改任何 spec 级需求**」。这说明 openspec 的设计**承认了「重构不改行为」这个事实**，而不是逼你写一份假的 spec 增量应付流程。

> 一句话：流程不应该比事实复杂。如果你的流程逼着你"为了写文档而写文档"，就该改流程，不是改事实。

### **3.6 工具与技能**

|            | **furfly-spec**             | **openspec**                                                 |
| ---------- | --------------------------- | ------------------------------------------------------------ |
| 形态       | 一份 skill（`furfly-spec`） | 多个 skill：`/opsx:explore` `/opsx:propose` `/opsx:apply` `/opsx:archive` |
| 底层 CLI   | 无                          | `openspec new / status / instructions / validate / archive / show / list / doctor` |
| 校验       | AI 自检                     | CLI 强校验 + AI 自觉                                         |
| 状态可见性 | 全靠人                      | `openspec status --change <名> --json` 报告每个文档的完成度  |

openspec 把 skill 拆成 4 个**对应生命周期阶段**的子技能，每一步背后是一个 CLI 命令。好处是流程可观测、可中断、可恢复（你关掉电脑，`openspec list` 也能告诉你还差什么）。

### **3.7 组织视角：feature vs capability**

|          | **furfly-spec**                             | **openspec**                            |
| -------- | ------------------------------------------- | --------------------------------------- |
| 单位     | 一次功能/特性                               | 一个 capability（系统能力）             |
| 生命周期 | 跟这一次变更一起存在                        | **跨多个 change 长期存在**              |
| 命名     | 中文概括主题（`docs/features/读文件工具/`） | 英文 kebab-case（`specs/tool-system/`） |

这个差异**对长期演进影响很大**：

* furfly-spec 的目录名是「**主题**」——它记录的是"这次做了什么事"，强调短期动作。
* openspec 的目录名是「**能力**」——它记录的是"系统现在能做什么"，强调长期状态。

举个例子：Furfly Code 现在有 `chat-client`、`tool-system`、`agent-loop` 三个 capability。`agent-loop` 这个能力**第一次出现**是 `add-agent-loop` 这次变更，**未来要做的事**（比如"多 agent 协作""子任务分派"）依然会**修改** `agent-loop` 这一个 spec——不是再开一个 `multi-agent` 目录。

这种「能力是长生命周期实体、变更是短生命周期事件」的设计，**让主规格保持稳定**。

---

## **四、为什么 openspec 正好解了你的痛点**

把你的痛点翻译成更结构化的版本：

> 旧的设计文档 A 写了"用 `func_name_v1(path)` 实现 X"。  
> 后来代码重构，函数改名/参数改了/换了个文件。  
> 再后来 AI 拿到任务，要做"实现 X 的相关新功能 Y"。  
> AI 读 `docs/features/A/spec.md` 和 `plan.md`，**发现 plan.md 里** `func_name_v1` **还在**，于是要么死守旧函数名、要么每次都纠结要不要改回来。

furfly-spec 这个问题的**根因**有 3 层：

1. **plan.md 与 spec.md 平级**：plan.md 写了实现细节，但没有任何机制把它标记为"实现稿"——它的"权威性"和 spec.md 一样。
2. **没有归档动作**：旧 plan.md 永远留在 `docs/features/A/`，AI 每次都看得到。
3. **没有"当前事实"概念**：仓库里没有"系统现在的 spec 是哪一份"这个单一入口。

openspec 把这 3 层**全部解掉**：

1. **design.md 不进 specs/**：设计稿物理上隔离在 `changes/`，主规格库 `specs/` 看不到实现细节。
2. **归档冻结**：旧 change 进 `changes/archive/<日期>-<名>/`，命名带日期就是强调"这是历史"。
3. `specs/<cap>/spec.md` **是单一入口**：每个 capability 一份主规格，归档时所有 delta 都已合并进这里，永远反映"系统现在该做什么"。

**结果**：AI 想了解"agent-loop 现在该做什么"，只看 `specs/agent-loop/spec.md`——里面只有「系统 SHALL 以 ReAct 模式编排对话……」「事件流 SHALL……」这种行为陈述，**没有** `agent/__init__.py` **的影子，没有** `Event`**/**`RoundEvent` **的字段名，没有** `max_iterations=20` **的具体数字以外的位置信息**。它能给出的指导是"系统要能循环到不再请求工具为止"，**不**会先入为主地说"应该把 `run` 写成两段串联"。

而要看"当年为什么这么设计"，**显式**去翻 `changes/archive/2026-06-30-add-agent-loop/design.md`——这一刻是 AI 主动选择的、临时的、上下文有界的，不会污染默认上下文。

---

## **五、换装 openspec 的实际收益**

1. **spec 永远是行为，不被实现细节污染**。AI 读 specs/ 时拿到的是稳定的、不带代码味道的行为契约。
2. **主规格库单一来源**。`specs/<cap>/spec.md` 永远反映"系统现在该做什么"，没有"哪份 spec 是最新的"问题。
3. **格式可校验**。`openspec validate --strict` 强制 SHALL/MUST 和 4 个 `#`，写错了不会糊弄过去。
4. **Scenario 天然是测试用例**。每个 `#### Scenario` 是 WHEN/THEN 句式，直接对应一个 pytest 用例，验收环节有抓手。
5. **delta 操作显式化**。`ADDED / MODIFIED / REMOVED / RENAMED` 四种动作让"这次改动到底动了什么"一眼可见；review 成本低。
6. **纯重构有正路**。`--skip-specs --no-validate` 让"行为零变化的清理"不必伪造 spec 增量，仓库里 `refactor-tool-types` 就是范例。
7. **历史冻结可追溯**。`changes/archive/<日期>-<名>/` 命名带日期，archive 后只读；想找"X 能力是哪个 change 引入的"很容易。
8. **能力是长生命周期实体**。新功能总是修改既有 capability 而不是堆新目录，主规格保持稳定。
9. **CLI + skill 双层**。CLI 强制结构、skill 给人对话式入口；人能用 `openspec list` 一眼看现状。
10. **git diff specs/ 直接看行为变更**。需求级别的 diff 远比 plan.md 的 diff 有意义，code review 时说话的方式从"这个函数为什么这么写"变成"这个行为是不是真的需要"。

> 这一节读起来像产品广告——所以下一节我列代价，让你冷静一下。

---

## **六、换装 openspec 的代价**

1. **心智成本更高**。要理解 capability、delta、archive、freeze 这套词汇；要明白 MODIFIED 必须**贴整条**而不是只写 diff；要为 capability 起一个**将来很难改**的 kebab-case 名。
2. **格式容易静默失败**。`#### Scenario` 写成 `### Scenario` 或 `- Scenario`，openspec **不报错但不认这条**——必须在 archive 前跑 `--strict` 才暴露。furfly-spec 的 Markdown 模板没有这种陷阱。
3. **每个能力都要命名且稳定**。capability 一旦归档就锁死在 `specs/<名字>/` 目录名上，后续 change 引用都按这个名字写。起名草率要付长期代价。
4. **审批粒度变粗**。一整套 proposal+spec+design+tasks 一次过，没有"先把 spec 拍下来，再讨论 plan"的两段式。急着反复改 spec 时，这种粗粒度反而拖速度。
5. **多 skill 切换**。`/opsx:explore` / `propose` / `apply` / `archive` 四个技能需要记住对应阶段。furfly-spec 一个技能走完，认知负担小。
6. **小改动也走完整套**。一个 1 行的 bugfix 通常还是要建 change、立 proposal、列 tasks。对 1 行改动来说太重——furfly-spec 同样重（它连 1 行的改动也要 4 份文档），所以这点其实是**两者共有**的代价。
7. **依赖 CLI 工具**。openspec CLI 必须装好、PATH 要有。furfly-spec 是纯提示词，离线也能用。
8. **迁移旧文档要手工做**。如果之前在 `docs/features/` 写过一批 furfly-spec 文档，它们不会自动转成 capability spec——要决定是丢弃、还是手动合并进 `specs/`。
9. `TBD - created by archiving change ...` **略丑**。openspec 归档时自动给 capability spec 写一句 `Purpose: TBD - created by archiving change X. Update Purpose after archive.`，是占位符，**不影响校验**，但读着有点糙，需要后面补一句正经描述。
10. **AI 仍可能在 design.md 里写"必须用 X 函数"**。openspec 没强制 design.md 的颗粒度——它只强制 spec 干净。如果你 review design 不仔细，design 里塞实现细节的老毛病会以新形式重现。spec 干净 ≠ design 也干净。

> 看到这里你可能累了。所以下面放几件我"翻仓库时顺手发现"的小事，当作读累了喘口气的彩蛋。

---

## **七、我额外发现的几件事**

翻 Furfly Code 仓库时顺手看到一些值得点出来的细节。

### **7.1 仓库的现状本身就是"用脚投票"**

* 仓库里**完全没有** `docs/features/` **目录**——说明 furfly-spec 在这个项目上**从未真正落地过**。
* `openspec/specs/` 里有 3 份主规格（chat-client / tool-system / agent-loop）。
* `openspec/changes/archive/` 里有 4 份归档变更（multi-protocol-chat-client / tool-system / refactor-tool-types / add-agent-loop）。
* 但 `CLAUDE.md` **第 7 节**还写着：「新功能/模块开发可用 `furfly-spec` 或 `openspec-*` skills 走 spec → plan → task → checklist 流程」——**两者并列**。从仓库实际状态看，furfly-spec 已经名存实亡，但文档没跟上，CLAUDE.md 是过时的。

如果你想让 AI 别走老路，记得把 `CLAUDE.md` 第 7 节改成「用 openspec」。

### **7.2 refactor-tool-types 是"纯重构有正路"的活样本**

它的 proposal.md 直接写：

```
### New Capabilities
<!-- 留空：纯内部重构，无新 capability -->

### Modified Capabilities
<!-- 留空：行为零变化，不改任何 spec 级需求。... -->
```

tasks.md 也清楚到「改 1.1 / 1.2 / 1.3」这种粒度。它证明了：**行为不变的重构在 openspec 里是有合法路径的，不是被流程卡死的**。这点比 furfly-spec 的"无论多简单一律走完 4 份"更贴近工程现实。

### **7.3 add-agent-loop 用了一种"双 capability"的小技巧**

它的 proposal 写：

```
### New Capabilities
- agent-loop: ReAct 自主循环编排 ...

### Modified Capabilities
- tool-system: 「结果回灌与单轮闭环」Requirement 改为「结果回灌与 ReAct 循环」 ...
```

结果归档时 `specs/` 出现了**两份**：新建的 `specs/agent-loop/spec.md`（11 条 Requirement）+ 修改后的 `specs/tool-system/spec.md`（在"结果回灌与单轮闭环"那条上 `MODIFIED`）。

这是个**正反都成立**的选择：

* 好的方面：「agent loop」作为独立能力有清晰的边界，未来要扩展时有自己的 spec；同时 tool-system 的「结果回灌」仍然记录在 tool-system 下，保持责任归属。
* 微妙之处：同名概念（"单轮→多轮"）在两个 spec 里都有描述，未来读 `specs/tool-system/spec.md` 的人会看到"结果回灌与 ReAct 循环"，**但要理解 ReAct 的具体定义必须跳到** `specs/agent-loop/spec.md`。这种 cross-reference 是 openspec 没显式管理的设计——你 review spec 时要主动避免让一条 Requirement 同时属于两个 capability 的情况。

### **7.4 spec 格式的"静默失败"是最大的暗坑**

`openspec 手册` 第 7.1 节直接列了这个坑：

> `####` 必须 4 个 `#`：spec 的 Scenario 写成 3 个 `#` 或 bullet，openspec **不报错但不认**，归档时那条场景就丢了。

意味着：**如果你 review 不仔细，可能整条 Scenario 在归档时被无声丢弃**。两个缓解手段：

* archive 前必跑 `openspec validate <名> --strict`。
* 把"每条 Requirement 至少 1 个 Scenario"作为硬性 review 项，过目 `####` 数量。

### **7.5 旧 plan.md 的"实现细节"会换一种形式复活在 design.md**

openspec 解了 spec 被污染的问题，**但 design.md 仍然可能塞满函数签名和数据结构**——只不过位置从 `docs/features/A/plan.md` 搬到了 `changes/<name>/design.md`。

Furfly Code 的 `2026-06-30-add-agent-loop/design.md` 里就出现了：

> 把 `agent/__init__.py` 的两段硬编码串联重构成 `while` 循环的 ReAct 编排  
> `_collect_round(conv, defs) -> tuple[text_buf, calls, usage, err|None]`  
> `BaseTool.is_read_only()` 虚方法（默认 `False`）

这是合理的设计稿内容。但要警惕的是：如果某次变更的 design.md 里写了「**必须**用 `_collect_round` 这个私有函数」、下一轮重构又改了它，那**这份旧的 design.md 还在 archive 里**——只不过因为它物理上不在 `specs/` 里，AI 在做新功能时不会优先读到。

这是**降级风险**而不是"完全没问题"——spec 是干净的，但 design archive 仍然可能误导（如果 AI 主动翻历史的话）。要彻底干净，仍然要写 review 习惯：**新功能的 design.md 只引 spec，不引上一份 design.md 的实现细节**。

### **7.6 openspec 的"单一事实"是能力级的，不是仓库级的**

主规格是按 capability 拆分的（`specs/chat-client/`、`specs/tool-system/`、`specs/agent-loop/`），不是按仓库拆分的。每个 capability 有自己的主 spec、自己独立的修订历史。

推论：capability 拆分**本身就是一项架构决策**。拆得太粗（比如整个项目一个 `furflycode` capability），spec 变成长文档没人看；拆得太细（每个工具一个 capability），跨能力的改动要改多份 spec，archive 复杂。

Furfly Code 现在的 3 个 capability（chat-client / tool-system / agent-loop）拆得比较合理——**按"用户能感知到的功能边界"切**：能对话、能用工具、能自主循环。

---

## **八、什么时候用哪个**

把两个 skill 放回到决策树里：

```
要加/改一个功能？
│
├─ 行为会变吗？
│  ├─ 不会（纯重构 / 改名 / 性能优化）→ openspec archive --skip-specs --no-validate
│  └─ 会
│     ├─ 想要分两次拍板（先把"做什么"拍下来，再讨论"怎么做"）→ furfly-spec
│     └─ 想一次整包决策 + 归档后自动进主规格库 → openspec（推荐）
│
└─ 已经在用哪个？
   ├─ 已经在用 openspec → 沿用
   └─ 已经在用 furfly-spec → 考虑迁移到 openspec（理由见上）
```

**我的推荐**：默认用 openspec。它的设计直接对应你描述的痛点，且仓库的 4 份归档变更证明它**能落地、能跑通**。furfly-spec 适合的场景：组织里要求"先 spec 再 plan"的两段式审批，或者做**纯咨询性的需求澄清**（不写代码、不归档，只是要一份 4 份文档当合同）。

如果决定迁移，建议：

1. 写一份映射表（哪些旧 plan.md 的实现细节在新的 capability spec 里有对应？哪些已经过期要丢掉？）。
2. 把过期的 plan.md 直接删除或挪到一个 `docs/features-archive/` 里——别留在 `docs/features/`。
3. 删 `docs/features/` 之前先 `rg` 一遍，确认没有别的地方引用。
4. 同步更新 `CLAUDE.md`，把"furfly-spec"从默认推荐里拿掉。

---

## **附录：本仓库快照（2026-06-30）**

| **项**                        | **值**                                                       |
| ----------------------------- | ------------------------------------------------------------ |
| 项目根                        | `E:\Furfly-Code`                                             |
| furfly-spec 落地证据          | **无**（无 `docs/features/` 目录）                           |
| openspec 落地证据             | `openspec/specs/` × 3，`openspec/changes/archive/` × 4       |
| 活跃 change                   | 0                                                            |
| 主 capability                 | `chat-client`（20 条 Requirement）、`tool-system`（20 条）、`agent-loop`（11 条） |
| 归档变更                      | `multi-protocol-chat-client`、`tool-system`、`refactor-tool-types`、`add-agent-loop` |
| `openspec/config.yaml` schema | `spec-driven`                                                |
| `CLAUDE.md` 第 7 节           | 仍把 `furfly-spec` 与 `openspec-*` 并列（与实际不符）        |
| `README.md`                   | 只提 openspec，不提 furfly-spec                              |

## **附录 B：迁移前后的对比**

| **关注点**                      | **furfly-spec**                     | **openspec**                                 |
| ------------------------------- | ----------------------------------- | -------------------------------------------- |
| "当前事实"在哪                  | 没明确，文档都堆在 `docs/features/` | `specs/<cap>/spec.md`（合并后的主规格）      |
| 旧设计如何退役                  | 不退役                              | 归档到 `changes/archive/<日期>-<名>/` 并冻结 |
| AI 读 spec 时会不会被旧实现带跑 | 经常会（plan.md 写实现细节）        | **不会**（spec 物理上不写实现）              |
| 纯重构要写文档吗                | 要（4 份）                          | **不要**（`--skip-specs --no-validate`）     |
| 需求 diff 怎么打                | 没法打（文档粒度不固定）            | `git diff specs/` 直接看行为变化             |
| 4 个井号的坑                    | 无                                  | 有（静默失败，必须 `--strict`）              |
| 评审粒度                        | 4 段递进审批                        | 1 段整包审批                                 |
| 工具依赖                        | 纯提示词                            | 需 `openspec` CLI + 多个 `/opsx:` skill      |

---

## **写在最后**

如果只允许我说一件事，那会是这个：

> **spec 写得"完整"不等于 spec 写得"好"。写得越完整，对未来的约束越死。**

furfly-spec 不是坏工具——它在"先想清楚再动手"这件事上比直接写代码强太多了。但它把所有"想清楚"的内容**都沉淀成长期文档**，又没法让这些文档"退休"，于是沉淀就变成了负担。

openspec 不是银弹——它的格式更硬、心智成本更高、还依赖 CLI。但它做了一个非常关键的取舍：**让 spec 只写行为，把实现细节隔离到 design 并归档冻结**。这一刀切下去，"过去"才真正属于过去。

回到开头那句被旧文档反噬的话——我后来做的就两件事：

1. 把那份写满函数名的 plan.md 删了。
2. 把 spec 重新写一遍，只写行为，不写实现。

工具可以帮你切得更干净，但**写 spec 时克制"想写完整"的冲动**这件事，没有工具能替你做。

---

> 如果你也在被旧 spec 折磨，欢迎在评论区聊聊你遇到的具体场景——我比较好奇别人的痛点是不是和我的类似。如果这篇文章帮到了你，转发给那个"还在维护三年前的 plan.md"的朋友，应该能救他一命。

---

## **参考资料**

* `docs/openspec手册.md`：Furfly Code 的 openspec 工作流手册

* `openspec/specs/{chat-client,tool-system,agent-loop}/spec.md`：当前主规格

* `openspec/changes/archive/`：历史变更（4 份提案 + 1 份纯重构）

* furfly-spec skill 全文：用户贴入会话

  

