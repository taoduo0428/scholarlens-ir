# P1 任务存储与结构契约验证

2026-11-20 在 Windows 10.0.26200 上使用 worktree 内的 Python 3.11.15、SQLite 3.53.1、Pydantic 2.14.1、pytest 9.1.1 执行。测试分别创建本地临时数据库。完整输出位于 [evidence/p1-store（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-650e8d7f1b0a)。

| 检查 | 退出码 | 结果 |
|---|---:|---|
| 首次运行，使用系统默认 pytest 临时目录 | 1 | 22 通过、5 失败、18 个 fixture 初始化错误。Windows 拒绝访问默认临时目录，见 before.txt |
| 指定 worktree 测试目录，重现实现缺陷 | 1 | 37 通过、8 失败，见 reproduction.txt |
| 修复后，运行下方完整回归命令 | 0 | 48 通过、0 跳过，2.18 秒，见 after.txt |
| 对两个模块及两份测试执行 compileall | 0 | 语法检查通过 |

```powershell
# 从项目根目录运行。basetemp 指向此测试独占的可清空目录
.venv/Scripts/python.exe -m pytest backend/tests/research/test_store.py backend/tests/research/test_schemas.py --basetemp=output/p1-test-temps/final -q --tb=short
.venv/Scripts/python.exe -m compileall -q backend/research/store.py backend/research/schemas.py backend/tests/research/test_store.py backend/tests/research/test_schemas.py
```

## 存储行为

- 八个同步发起的连接用同一账户和幂等键创建任务，得到一个任务和一条创建事件。同键不同请求报冲突，不同账户使用独立的幂等空间。
- 五个写入者竞争同一版本，其中一个成功提交。相同执行 ID、事件及状态可以重放并返回第一次的 revision。修改过的重放和过期写入均被拒绝。关库重开后按事件游标分页，无序号缺失或重复。
- 在事务的最后一步注入错误事件，任务状态、revision、checkpoint 和事件序列全部回滚。
- 账户与任务双重定位覆盖任务、事件、checkpoint 和 artifact。一个账户使用其他账户的 task ID 被拒绝，同一 artifact ID 不能跨任务读取。
- artifact 按内容摘要幂等保存，读取重新校验 SHA-256。新增读取历史 checkpoint 的接口，校验关联事件以及状态摘要。
- 支持 SQLite 一致性备份与恢复到新目录，恢复得到同一 revision、原始 artifact 与对应事件。已存在的目标数据库受独占创建保护，未知 schema 与缺失表的快照被拒绝。

## 修复与文件

`backend/research/schemas.py` 验证原文字段与 locator 一致、字符区间非空且正序，限制嵌套 coverage 槽位数，将证据绑定到当前 generation 和本任务证据额度。预算 deadline 要求时区。

`backend/research/store.py` 限制原始幂等键长度，拒绝已消耗预算回退、运行中放宽上限和延长截止时间，新增 `checkpoint(owner, task_id, revision)` 和 `ResearchStore.restore(snapshot, fresh_runtime)`。数据库 schema 保持版本 1。

`backend/tests/research/test_store.py` 和 `backend/tests/research/test_schemas.py` 覆盖上述行为，并逐类测试允许的动作、未知字段、版本绑定、资源限制、错误快照以及失败回滚。性能记录为本机测试套件用时。多主机吞吐、语料检索质量和真实模型费用尚待后续相应阶段测量。
