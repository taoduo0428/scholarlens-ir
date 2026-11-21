# 离线评测协议

先冻结语料、问题、分组和程序版本，再测量。旧 Agent 用其真实的 ResearchAgent.run 入口，明确列出被固定或替换的检索与 provider。受控检索适配器的时间只说明本地工程行为。若使用 ES 记录实际 concrete index、向量模型、参数、查询数以及冷暖状态。

每条研究任务带 scope、corpus_generation、required_slots、gold 引用、claim rubric、human_labeler、annotation_status。机器可确定地检查 chunk 原文、偏移、哈希与出处。人工支持率和相关性指标仅对已独立审定的任务计算，输出同时披露有效任务数。使用本库原文准备可复核条目时，通过 Git blob 或 LFS SHA 寻源。各个 split 按论文/主题分组，holdout 仅用于最终锁定的比较。

P1 的 legacy 与 v2-placeholder 对照验证输入、计时、事件、版本与缺失指标的表示。P2 和 P3 分别引入检索策略和动态决策。后续 B0–B5 共用语料、问题与资源约束，汇报每个实际版本的耗时、调用与证据覆盖。候选技能与策略只能读训练与开发部分；缺少可支持晋升的证据时保留已批准版本。
