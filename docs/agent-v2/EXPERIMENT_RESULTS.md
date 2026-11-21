# EvoResearch 本地实验结果

2026-11-20 的本机正式入口验收使用 859 篇论文和 49,420 个 MiniLM 向量。单 Worker 对同一道地下水研究问题执行 7 次，指定论文与全库检索均返回可重定位的结论。冻结开发集上的新研究流程命中 3/7 个预置原文块，旧 Agent 在相同预算上限内命中 7/7 个。人工检索相关性与结论支持率尚待评审。[P8 交付批次](evidence/p8-native/859-release/summary.json) · [等预算对照](evidence/p6-p7-ablation/matched-budget-dev.json) · [评测口径](EVALUATION_PROTOCOL.md)

## P0 至 P8 验收

| 阶段 | 运行及观察结果 | 原始记录或阶段报告 |
|---|---|---|
| P0 基线 | 旧后端主套件 414 通过、5 跳过，专用环境补测 5 项通过。旧 Agent Harness 由 10/11 修复到 11/11。前端 45 项单测及桌面、390px 验收通过。源文件审计核对了 4,000 个唯一论文 ID。 | [基线总览](progress/P0.md) · [原始语料审计](P0_SOURCE.md) |
| P1 存储与种子 | 存储、契约、开关与评测 60 项通过，覆盖并发幂等、账户隔离和恢复。公开种子 12 篇、36 题，55 个原文锚点通过字符核对。 | [专项验收](progress/P1.md) · [60 项测试（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-55d330e29e90) |
| P2 检索 | 固定 100 篇论文，8 个查询各重复三轮。HNSW 与精确检索的 top 10 共重合 237/240 次。BM25、精确 MiniLM、HNSW、RRF 及 RRF 加重排的 P95 依次为 5.33、9.53、9.08、14.74、43.37 ms。 | [实验设计和环境](P2_EXPERIMENT.md) · [逐次测量（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-5284203f1dd3) |
| P3 自适应执行 | 受控材料首轮找到方法，次轮补检获得指标。中断恢复保留已提交证据和事件顺序。执行边界 14 项通过，包括限流、凭据遗失、语料变化和取消。 | [执行验收](progress/P3.md) · [测试输出（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-57fcae491728) |
| P4 结论与引文 | 27 项结论核验回归覆盖了实体识别、指标和适用条件。Cedar/Birch 的 precision at five 与 recall at ten 被标为不可比。真实地下水用例在陈述中给出地区及超标关系。 | [核验记录](progress/P4.md) · [最终真实陈述（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-9567dc069d4c) |
| P5 工作台 | Chrome 经回环 HTTP 和真实 Worker 跑两篇 fixture。4 个子任务、5 条连续事件、2 条来源、9 条结论，其中 8 条通过核验、1 条不可比。逐条归属、原文高亮、Markdown、跨账户 404 和 390px 布局均通过。另用 Mock 交互验证冲突与缺口。 | [真实浏览器输出（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-ab46c659ca98) · [冲突与缺口（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-3fefaffb45bc) |
| P6 技能 | 24 道训练题中 3 条轨迹达到门禁。技能对照的 smoke 均命中 7/7，dev 均为 3/7，dev 各调用工具 27 次。示范操作员在沙箱完成候选审批和回滚。 | [评测与门禁](progress/P6.md) · [复核回执（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-a68914481b89) |
| P7 策略 | 三种配置在 dev 的锚点覆盖均为 3/7，调用工具分别为 27、25、23 次。精简候选的独立 smoke 从 7/7 降至 6/7，审批门禁拒绝晋升。 | [策略实验](progress/P7.md) · [审核回执](evidence/p6-p7-ablation/policy-review.json) |
| P8 正常应用 | 本机 FastAPI TestClient 经单 Worker、SQLite 和真实 ES 完成 3 次顺序与 4 次并发提交。每项任务读回 2 个来源、生成 1 条已核验陈述、实际调用工具 6 次，模型调用为 0。 | [环境及命令](P8_NATIVE.md) · [r4 观测（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-89832c3c4125) |

## 等预算结果与冻结范围

开发集六题的 B0 与 B2 每题均设 10 次工具、10 条证据、120 秒和零模型调用上限。B0 实际调用工具 12 次、命中 7/7 个原文块。B2 实际调用 27 次、命中 3/7 个。两套流程各有一道无证据题仍返回片段。这里按命中的预置源块计数，完整回答的支持性由独立人工评审判断。[逐题记录](evidence/p6-p7-ablation/matched-budget-dev.json)

六种预登记配置在 holdout 各执行一次并已封存。已公布的原文覆盖为 B0 6/7，B1 至 B5 均为 4/7。保留集禁止重开、重跑或用于选参。后续开发验证使用 train、dev 和独立 smoke。102 道盲评候选题覆盖另外 34 篇公开论文，每题 8 篇候选，当前签核数为零。P@5、nDCG、MRR 和人工 Claim 支持率均为 `null`。[封存回执](evidence/final-holdout-receipt.json) · [已发布消融汇总（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-b26c8d7fb009) · [人工盲评指南](ANNOTATION_GUIDE.md)

## P8 的 r4 批次与故障恢复

r4 对同一道问题交替使用指定论文和全库检索。最终陈述点名浊水溪冲积扇南部和嘉南平原，并分别给出约 70%、超过 95% 的监测井高于 WHO 砷指南值 0.01 mg/L。自动断言同时核对论文中报告的地区、超标关系和来源哈希。顺序运行 3 次的 P50/P95 为 422/437 ms，四线程并发提交 4 次为 1,352/1,875 ms。客户端每 75 ms 轮询一次，两个 P95 均取该组最大观测值。计时涵盖本机应用、SQLite、ES 和轮询。[指定论文的最终报告（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-9567dc069d4c) · [全库最终报告（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-6351709c4f4f) · [样本与计时](P8_NATIVE.md)

故障复测在两条证据提交后切换临时 ES alias。任务进入暂停，报告接口返回 409。原账户可读回已有证据，恢复 alias 并继续执行后，任务完成且两个来源再次通过校验。[r4 故障记录（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-465a78a7792e)

P2 的时延对应单次检索，P8 对应一个任务从提交至客户端观察到终态的时间。P5 验证交互，P8 的七次请求覆盖同一道真实问题。不同问题上的人工正确率和付费模型成本仍待评估。[检索实验](P2_EXPERIMENT.md) · [浏览器范围](progress/P5.md) · [运行架构](ARCHITECTURE.md)

## 交付版本

最后的正常应用批次再次提交了七项真实任务。每份报告写出两个地区及超标关系，每项 6 次工具调用、0 次模型调用。顺序三次的 P50/P95 为 328/500 ms，四个并发提交的 P50/P95 为 1,070/2,016 ms。运行时内存采样 116.95–120.63 MiB。临时索引切换后任务暂停，恢复后两条来源哈希一致。[交付批次](evidence/p8-native/859-release/summary.json) · [故障记录](evidence/p8-native/drift-release.json)

六道真实开发题另接入完整报告发布器。初版把一段 GNN 的准确率当成设备电池电流问题的答案，还用被截断的背景句回答“哪种操作引入符号知识”。经通用问句、原文完整性和测量类型检查，第一题保留缺口，已核验结论数为 0。第二题逐字引用作者命名该操作为 vertex-enrichment 的原句。问能否在同一排行榜比较的任务保留 4 条背景来源和评测条件缺口。六题最终全部为部分完成，9 条公开来源通过哈希回读，命中 5/7 个预置来源块，其中多跳题没有获得有效来源。这是图默认预算下的发布诊断，冻结的等预算检索实验维持原记录。[修复前（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-a973d2e7a678) · [修复后逐题结果](evidence/p8-final/dev-publication-aligned.json) · [回归用例](../../backend/tests/research/test_question_alignment.py)

旧后端交付前复测 414 项通过，套件中跳过的 5 项在专用上传环境全部通过。新研究套件含本机 ES 共 159 项通过，前端 45 项通过，Chrome 复验了报告、原文和跨账户访问。[旧套件（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-15fa945b2a15) · [上传（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-5a9213c2130f) · [研究套件](evidence/p8-final/research-release.txt) · [Chrome](evidence/p8-final/frontend-chrome.txt)
