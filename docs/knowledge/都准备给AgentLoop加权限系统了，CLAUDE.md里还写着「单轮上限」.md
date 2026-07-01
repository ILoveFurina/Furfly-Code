---
title: 都准备给 AgentLoop 加权限系统了，CLAUDE.md 里还写着「单轮上限」
date: '2026-07-01 20:30:00'
tags:
- AI Coding
- Agent
- CLAUDE.md
- 实践
mood: ''
cover: ''
description: 准备给 FurflyCode 的 AgentLoop 加权限系统时，在 CLAUDE.md 里撞见一条已经被自己推翻的「单轮上限」。追 git log 发现：写入、推翻、归档发生在同一天，三件事都做对了，唯独没人回头同步 CLAUDE.md。这件小事指向一个结构性问题——CLAUDE.md 是 spec 流程照不到的孤岛。
---

都准备给 AgentLoop 加权限系统了，结果在 CLAUDE.md 里发现了一条「单轮上限」。

`agent/__init__.py` 早已是 `while iteration < self._max_iterations` 的 ReAct 循环，`max_iterations` 默认 20。这条「单轮上限」是 2026-06-30 写进 CLAUDE.md 的，当天就被 `add-agent-loop` 推翻——proposal 里还顺手写了句「不做权限系统，留后续」。我要做的权限系统，正是那张欠条的兑现。

这篇想讲的不是权限系统，而是这件小事里藏着一个结构性问题：**spec 归档流程为什么没回头同步 CLAUDE.md？**

> 基于 Furfly Code（<https://github.com/ILoveFurina/Furfly-Code>）的实战。写于 2026-07-01。

---

## **一、那行字长这样**

我打开 CLAUDE.md，想确认现有的工具约束怎么写的，好接着往上加权限系统。然后我在「关键设计」节看见了这一行：

> **单轮上限**：续答请求#2 忽略其返回的工具调用，不再发起新一轮工具执行。

我愣了一下。我的 Agent 现在跑的是一个最多 20 轮的 ReAct 循环。这行字描述的那个「调一次工具就停」的旧世界，早就被我自己亲手删掉了——只是删在代码和 spec 里，忘在了 CLAUDE.md 里。

更讽刺的是，我翻出当时的变更提案，里面清清楚楚写着：「本次变更**不做**权限系统、上下文压缩、用户交互式确认——留给后续。」我现在做的权限系统，就是兑现这张欠条。结果欠条还没还，旧世界的墓志铭还挂在墙上。

---

## **二、2026-06-30，同一天里的三件事**

我去翻 git log，想把这件事看清楚。时间是 2026-06-30，同一天里发生了三件事：

**早上** —— `4c21324 docs: 重建 CLAUDE.md 反映当前架构`。

我把当时还是真的「单轮上限」郑重写进 CLAUDE.md 的「关键设计」节。注意：**此刻这个描述是属实的**。当时的 `agent/` 就是两段硬编码串联——请求#1 带工具 → 执行 → 回灌 → 请求#2 续答，然后停。续答里就算模型又请求了工具，也忽略。这个「单轮上限」是对当时架构的如实记录，不是拍脑袋写的约束。

**下午** —— `add-agent-loop` 变更提案登场（`d2306af`）。

proposal 的 Why 段写着：

> tool-system 让模型能调用工具，但编排层是硬编码的「单轮闭环」……结果是模型每做一步就得用户重新催一次，无法自主完成需要多步工具协作的任务。本次变更给 FurflyCode 装上 ReAct 式 Agent Loop……

What Changes 里有一条把架构从两段串联重构成 `while` 循环的 ReAct 编排。然后是那句要命的话：

> 本次变更**不做**权限系统、上下文压缩、用户交互式确认——留给后续。

**晚上** —— `572d42a feat: Agent ReAct 自主循环编排` 落地，接着 `d3a166c docs(spec): 归档 add-agent-loop 并同步主 spec`。

归档时，主规格库 `openspec/specs/tool-system/spec.md` 里那条 Requirement 从「结果回灌与单轮闭环」改名成「结果回灌与 ReAct 循环」，措辞反转干净利落：

> 当模型在续答中仍请求工具时，SHALL 继续执行并回灌、进入下一轮，形成 ReAct 自主循环，直到模型不再请求工具或触达停止条件……循环 MUST 受可配的迭代上限约束作为兜底安全网；到达上限时 SHALL 以明确文本提示非静默收尾，**不再强制单轮停机**。

「不再强制单轮停机」——spec 用了七个字把「单轮上限」正式宣判死刑。

---

## **三、三件都对，唯一漏了回头**

把这一天复盘一下：

1. **代码改对了**——`agent/__init__.py:144` 现在是 `while iteration < self._max_iterations`，迭代上限 20，停止条件覆盖正常完成 / 超上限 / 用户取消 / 未知工具 / 流出错。
2. **spec 同步对了**——tool-system 主规格从「单轮闭环」改成「ReAct 循环受迭代上限约束」，措辞反转、Scenario 更新、归档冻结。
3. **归档流程走对了**——proposal → design → tasks → 实现 → `openspec archive` 同步主 spec，一条都没落下。

唯一漏的，是没人回头问一句：**CLAUDE.md 那行字还成立吗？**

它就这么躺着。躺到我今天想做权限系统，重新翻开 CLAUDE.md 想接往上加，才被一行僵尸文字挡了一下。

---

## **四、为什么偏偏是 CLAUDE.md 漏了**

这事不能怪谁粗心。根因是结构性的：**CLAUDE.md 不在 spec 流程的同步图里。**

`add-agent-loop` 走的是完整 openspec 流程。这个流程的同步范围是 `openspec/` **内部**——归档时把变更包里的 spec 增量合进 `openspec/specs/<capability>/spec.md`，历史提案冻进 `openspec/changes/archive/`。这套机制设计得很好，我上一篇《实践出真知：为什么要采用openspec？》专门夸过它把「当前事实」和「历史提案」物理隔离。

问题在于，**CLAUDE.md 不在这个同步图里**。

它是给 Claude Code 看的项目说明，归档动作不会触发它的更新。没有任何一个步骤——proposal、design、tasks、implement、archive——会停下来问「这次改动有没有让 CLAUDE.md 的某条描述失真」。

于是 CLAUDE.md 成了一个**两个系统都不 owns 的孤岛**：

- **spec 系统认为**：CLAUDE.md 不是 spec，归档不归我管。
- **AI 上下文系统认为**：CLAUDE.md 是我每次会话加载的输入，但你改不改它是你的事。

代码改了、spec 改了、归档也走了，三套机制都各司其职地转完了。CLAUDE.md 原地不动，因为没有任何一套机制的职责边界覆盖到它。

---

## **五、而且不止这一处**

为了说服自己这不是孤例，我又翻了一遍 CLAUDE.md。结果发现 §3 Architecture 的模块清单里，**根本没有 `conversation.py`、`prompt.py`、`context/` 这三个模块**。

而它们在源码里确确实实存在：

- `src/furflycode/conversation.py` —— 进程内多轮对话历史
- `src/furflycode/prompt.py` —— 结构化系统提示七模块拼装
- `src/furflycode/context/` —— 会话上下文注入（FURFLY.md 加载器 + 环境信息）

这三个模块是 `restructure-system-prompt` 那轮变更加的。同样地，代码进去了，CLAUDE.md 没跟上。

「单轮上限」是**描述被推翻**——写的当时是对的，后来错了。模块遗漏是**新增没登记**——写的当时就漏了。两种脱节方向不同，根因相同：**没有任何机制在代码变更时回头检查 CLAUDE.md。**

这不是一条僵尸文字的问题，是 CLAUDE.md 作为孤岛的系统性问题。

---

## **六、孤岛的危害不在过去，在未来**

你可能会想：一行过时的文字而已，过去这几个月也没出什么事，至于写一篇博客吗。

危害确实不在过去。过去那行字只是过时，没人真按它办事——我自己开发时看的是代码和 spec，不会照着 CLAUDE.md 的「单轮上限」去写循环。`add-agent-loop` 之后那段时间，这行字是个安静的尸体。

危害在未来。**CLAUDE.md 进每次会话的上下文。**

这是它和普通文档的根本区别。一份过时的 README 躺在仓库里，你不读它就不影响你。但 CLAUDE.md 是 Claude Code 每次开新会话都全文加载的——Anthropic 官方文档明说「CLAUDE.md files are loaded in full regardless of length」。这意味着：

- 下一个会话的我，读到「单轮上限」时会以为这是当前约束。
- 一个 AI 协作者被派来帮我做权限系统，读到「单轮上限」会先入为主地按「单轮」来设计，或者至少要多花几轮去确认这条到底还算不算数。
- 读到遗漏的模块清单时，会以为项目就只有那几个模块，写新功能时把 `conversation`、`prompt`、`context` 当成不存在的东西绕开。

僵尸文档不是静止的。它在**持续向每个新会话注射过时信息**。会话越多，注射次数越多。这才是孤岛真正的代价——不是一次性误导，是按会话计费的慢性中毒。

---

## **七、解法：文档同步不该靠人记**

想明白根因是「没有机制在变更时检查 CLAUDE.md」，解法就清楚了：**补上这个机制，而不是靠下次记得。**

我做了两件事。

### **7.1 重构 CLAUDE.md，让它更抗脱节**

第一件事是降低 CLAUDE.md 脱节的概率和代价。按 Anthropic 官方建议（根 CLAUDE.md 小而稳定当索引，细节用指针）做了几处改动：

- **§3 架构描述从「展开式」改成「指针式」**。原来每个模块写 1-3 行职责描述，现在改成「一句职责 + 源码路径指针」。比如 `message.py` 原来写「协议无关传输词汇（Message/ToolCall/ToolResult/StreamEvent/ROLE_*）。中性叶子模块，任何层可依赖而不引入方向倒置」，现在写成「协议无关传输词汇（叶子模块，零内部依赖）。详见 `src/furflycode/message.py`」。
  - 好处是：模块职责的一句话变了才算脱节，细节去源码读；CLAUDE.md 不再因为「展开得太细」而频繁过时。官方原话叫「prefer pointers to copies」——别贴副本，贴引用。
- **§7 Spec 驱动挪到 `.claude/rules/spec-workflow.md`，带 path-scoping**。原来 §7 写着「新功能/模块开发可用 furfly-spec 或 openspec-* skills……」，但这是流程指引，不是每个会话都适用的稳定信息。挪到 `.claude/rules/` 后加 frontmatter `paths: ["openspec/**"]`，只在动 `openspec/` 目录时才加载，平时不占会话上下文。
  - 顺带消除了我上一篇博客 §7.1 吐槽的那个问题——CLAUDE.md 第 7 节把已经名存实亡的 furfly-spec 和 openspec 并列。挪走时我顺手只留 openspec。
- **补齐遗漏模块**、**删掉「单轮上限」**。把 `conversation.py`/`prompt.py`/`context/` 三个模块加进 §3，把「单轮上限」从「关键设计」里删掉。

这一步是治标——让当前这具尸体入土，让结构更抗脱节。但它不能阻止下一具尸体产生。

### **7.2 加 hook，让机制替你盯着**

第二件事是治本——给那个「两个系统都不 owns 的孤岛」装一个第三方守夜人。

Claude Code 的 hooks 系统有个 `type: "prompt"` 的 hook：你写一段 prompt，Claude Code 在指定时机用 LLM 跑它，让它读 transcript 和文件、做判断、输出结果。我加了两个：

- **Stop hook（每轮回答结束时）**：让 LLM 读本轮 transcript + CLAUDE.md，判断「本轮改动是否让 CLAUDE.md 某条描述过时」。有发现就提示，没有就静默。
- **SubagentStop hook（子 agent 结束时）**：让 LLM 读子 agent 的 transcript + CLAUDE.md，判断「这轮是否踩到该记进 §6 Gotchas 的新坑」。有就提示该沉淀，没有就静默。

两个关键约束：

- **只提示，不阻断**。用 Stop/SubagentStop 输出 schema 里的顶层 `systemMessage` 字段做非阻断反馈——提示对 Claude 可见，但主流程照常结束，不会被 hook 拦截续跑。我不要 hook 替我改 CLAUDE.md，也不要它卡住正常工作。它只负责在合适的时机举起手说"这里可能要更新"。
- **钉死 JSON 形状，连枚举值一起钉**。prompt-type hook 的输出要被严格校验，LLM 稍一自由发挥就会触发 `JSON validation failed`，提示整条丢失。我在这上面连栽了两跤才把 prompt 调对（见下文），所以最后在 prompt 末尾把"输出什么形状、每个字段能取什么值、不许裹 markdown 代码围栏、JSON 外不许加文字"全钉死了。
- **按章节角色对照，不按编号**。prompt 里写"架构描述""硬约束""gotchas"这些**角色**，不写"§3""§5"编号。这样以后章节调整——比如哪天又把哪节挪走——hook 不会失效。

这套机制本质上是给 CLAUDE.md 这个孤岛补了一条 spec 流程里缺的同步边：每次代码变更结束，守夜人自动回头问一句"CLAUDE.md 还成立吗"。问的方式是 LLM 语义判断，不是 grep——因为"单轮上限被多轮循环推翻"这种事，正则匹配不出来。

### **7.3 两次撞墙：prompt-type hook 的输出 schema**

这两个 hook 我落地时连栽了两跤，都是 `JSON validation failed`。写下来，免得别人重蹈。

**第一跤：`additionalContext` 在 prompt-type 下不被接受。** 我照官方 hooks 文档的"decision control"表格，看到 Stop/SubagentStop 接受 `hookSpecificOutput.additionalContext` 做"非错误反馈、继续对话"，就用了它。结果 hook 一跑就报 `JSON validation failed`。查社区 issue（anthropics/claude-code#37559、thedotmack/claude-mem#1290、trailofbits/skills#131）才明白：那张表是给 command-type hook 的，**prompt-type hook 的输出 schema 更窄**，严格只认 `{decision?, reason?, systemMessage?, ...}`，`additionalContext` 直接被校验拒绝。改用顶层 `systemMessage`。

**第二跤：`{"decision":"approve"}` 是非法值。** 改完 `systemMessage` 还报同样的错。再查官方文档，发现 Stop/SubagentStop 的 `decision` 字段**只接受 `"block"` 一个枚举值**——`"approve"` 根本不是合法值，被严格校验拒绝。"不阻断"的正确做法不是输出 `approve`，而是**省略 `decision` 字段**（省略即默认放行）。我原以为"approve"是和"block"配对的标准值，其实是 LLM 习惯性补的一个非法词。最终修复：无发现输出空对象 `{}`，有发现输出 `{"systemMessage":"..."}`，全程不碰 `decision`。

两跤同源：**钉 JSON 形状时只钉了字段名，没钉每个字段的枚举合法值。** LLM 会老老实实输出一个"形状对、值非法"的对象，照样触发校验失败。所以最后 prompt 末尾不只钉"输出什么形状"，还把"decision 只接受 block、approve 非法"也明写了进去——连枚举值一起钉死。

> 这部分的设计文档我落在了 `docs/superpowers/specs/2026-07-01-claude-md-sync-hooks-design.md`，配置写在本机的 `.claude/settings.local.json`（被 gitignore，不随仓库分享）。

---

## **八、写在最后**

回到开头那张欠条。

`add-agent-loop` 的 proposal 里那句「本次变更不做权限系统——留给后续」，今天终于要兑现了。结果我打开 CLAUDE.md 准备接着往上加，先撞见的是那条被自己推翻的「单轮上限」。

这件事给我留下两句话：

> **一、三件事都做对，不代表整体做对。** 代码对、spec 对、归档对，但只要同步图里漏了一个节点，那个节点就会慢慢长成孤岛。检查流程时别只看每个步骤对不对，要看步骤之间的**边**有没有断。

> **二、文档同步不该靠人记，该靠机制。** 「下次记得改 CLAUDE.md」是一个我每次都会说的话，也是一个我每次都会忘的话。与其相信记性，不如补一条 hook——哪怕它只是在我结束时举一下手。

那张欠条我正在还。还的过程中顺手把墙上的墓志铭摘了，还给整面墙装了个会自己报警的小装置。

至于权限系统本身——那是下一篇的事了。

---

## **参考资料**

- 变更提案：`openspec/changes/archive/2026-06-30-add-agent-loop/proposal.md`（「不做权限系统——留给后续」原话出处）
- 主规格同步：`openspec/specs/tool-system/spec.md`（「结果回灌与 ReAct 循环」Requirement，「不再强制单轮停机」）
- 循环实现：`src/furflycode/agent/__init__.py:144`（`while iteration < self._max_iterations`）
- CLAUDE.md 重构与 hook 设计：`docs/superpowers/specs/2026-07-01-claude-md-sync-hooks-design.md`
- Anthropic 官方 Memory 文档：`code.claude.com/docs/en/memory`（CLAUDE.md 全文加载、`.claude/rules/` path-scoped、pointer > copy）
- Anthropic 官方 Hooks 文档：`code.claude.com/docs/en/hooks`（Stop/SubagentStop 的 `systemMessage` 非阻断反馈、`decision` 仅接受 `block`、prompt-type hook）
- 前作：《实践出真知：为什么要采用openspec？》`docs/knowledge/实践出真知：为什么要采用openspec？.md`（§7.1 已埋下「CLAUDE.md 第 7 节过时」的伏笔，本文是它的深化）
