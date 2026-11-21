# ScholarLens 研究工作台独立审查

2026-11-20，在隔离工作树内审查了来源权限、个人模型恢复、队列故障和评测记录。两项运行检查分别使用临时 SQLite、哨兵配置和内存语料。

## 1. 满队列和账号停用时的个人凭据

审查时将队列容量设为 1 并提交两项任务，观察到 1 个排队项持有 2 份配置。首个任务因账户停用进入 `failed` 后，Worker 缓存仍持有其配置，直到关闭进程。测试配置只含普通 Python 对象。

修复后的 Worker 只为已入队任务缓存配置，并在执行任务时先从缓存取出。独立回归验证了满队列的第二项任务仍保存在 SQLite，补位时进入 `awaiting_credentials`。账户在提交后停用时，任务进入 `failed / blocked`，缓存同步释放。两项测试和 Ruff 检查通过。[回归测试](../../backend/tests/research/test_worker_admission.py)

## 2. 报告发布前的来源回查超时

审查时，最后一次 `verify_source_quote` 同步占用唯一 Worker，只在调用返回后检查截止时间。一次独立局部检查给报告留下 50 ms，并让测试语料调用耗时 200 ms。报告约 250 ms 后返回 `partial / budget`，公开来源为 0。超时引文已被过滤，排在后面的任务仍须等调用结束。

修复后，最终回查与常规工具调用使用同一超时处理。相同的 50 ms 预算和 200 ms 模拟等待下，报告在 109 ms 内完成 SQLite 写入并返回 `partial / budget`，发布来源为 0。这个观测包含预算结算后生成、序列化和保存报告的时间。[发布超时回归](../../backend/tests/research/test_publication_deadline.py) · [任务预算规范（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-ffd26c59d51c)

## 来源、模型和评测证据的范围

- 来源工具从当前已认证账户构造权限范围，私有上传经过所有者可见清单过滤。报告在发布时回查来源并核对切片和 SHA-256。原生验收记录包括另一账户读取报告得到 404，以及切换语料版本后暂停并恢复的事件。[权限实现](../../backend/research/tools/sources.py) · [原生验收](P8_NATIVE.md)
- 任务首次提供个人模型时可从 `personal-pending` 绑定具体模型，随后恢复会校验模型名称。该名称可用来复核任务配置，跨供应商的模型身份和可复现性仍需要供应商版本信息。[任务恢复](../../backend/research/api.py) · [持久化约束](../../backend/research/store.py)
- 冻结回放 B1–B5 运行研究图并评估证据块命中、原文哈希及工具轨迹。完整报告另在 859 篇真实语料上针对同一事实问题执行了 7 次。两组实验分别支持检索和系统执行验证。跨题报告质量、人工支持率仍待独立标注。本次审查只读取既有 holdout 结果。[回放实现](../../tools/research_evolution/replay.py) · [实验记录](P8_NATIVE.md) · [人工标注方案](ANNOTATION_GUIDE.md)
