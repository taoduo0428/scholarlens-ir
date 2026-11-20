# P8 本机真实语料与 Worker 验收

2026-11-20 使用经过导入与读回校验的 859 篇真实论文和 49,420 个固定 MiniLM 向量。正式 create_app 加载研究功能，临时账户库注册两个用户，真实单 worker 处理请求。请求通过进程内 FastAPI TestClient 发起。计时包含应用处理、SQLite、实际 ES 请求及客户端轮询。公网时延不在测量范围内。

## 任务与并发

同一个真实问题以指定论文和全库检索交替运行，3 项顺序执行，4 项并发提交。问题询问台湾哪些地下水集水区的砷浓度高。第一轮的核验结论只给出“这两个地区”及测量值。第一版修正给出调查地点，但遗漏砷浓度超标。最终 7 项均在同一条已核验陈述中列出浊水溪冲积扇南部（southern Choushui river alluvial fan）和嘉南平原（Chianan plain），并写出前者约 70%、后者超过 95% 的监测井超过 WHO 指南值 0.01 mg/L。每项都对结论本身执行名称和超标关系的断言。[初始报告](evidence/p8-native/859-r2/seq-0.json) · [中间报告](evidence/p8-native/859-r3/seq-0.json) · [最终指定论文报告](evidence/p8-native/859-r4/seq-0.json) · [最终全库报告](evidence/p8-native/859-r4/seq-1.json)

每项任务完成，返回两个来源和一个已核验陈述，执行六次工具调用。独立读回 ES 核对所有来源的字符区间及 SHA-256。事件序号连续，跨账户读取报告返回 404。模型调用数为零。[七项记录](evidence/p8-native/859-r4/summary.json)

| 负载 | 样本 | 提交至客户端观察终态的 P50 | P95 |
|---|---:|---:|---:|
| 顺序执行 | 3 | 422 ms | 437 ms |
| 四线程并发提交、单 worker 执行 | 4 | 1,352 ms | 1,875 ms |

P50 按中位数计算，P95 采用 nearest-rank。客户端轮询间隔为 75 ms，全程耗时 3.235 秒。Python 进程采样 RSS 为 116.75–121.10 MiB，ES 堆在批次开始与结束时分别使用 374.56 与 146.82 MiB。本次小样本的 P95 等于各组最大观测值。七次请求使用同一道题，其他问题的准确率仍待人工评估。

## 依赖切换与恢复

故障试验为正常应用创建一次性本地 ES alias。两个证据的事务提交后，将此 alias 切换到空索引。任务检测到语料代变化，进入 paused，报告接口返回 409。通过原用户凭据读取已保存证据并核对原文哈希。恢复 alias 后调用 resume，任务达到 completed，两个来源均重新验证。事件中可以看到 pause、resume、completed 的完整过程。临时 alias 和临时索引已清理，基准库仍为 859 篇。[本轮故障复测](evidence/p8-native/drift-r4.json)

## 复现

在本机专用 859 篇测试集群启动后，将下列 UUID 替换为该集群经 GET / 核对的 UUID。输出采用全新路径。

```powershell
.venv/Scripts/python.exe -m tools.research_eval.native_acceptance --cluster-uuid <本机测试UUID> --output docs/agent-v2/evidence/p8-native/rerun --runtime-root .venv/p8-test-dbs
.venv/Scripts/python.exe -m tools.research_eval.native_fault --cluster-uuid <本机测试UUID> --output docs/agent-v2/evidence/p8-native/rerun-fault.json --runtime-root .venv/p8-test-dbs
```

两项命令实际退出码均为 0。初版内存采样在 Windows 上出现 ctypes 句柄类型错误，改为 HANDLE 后重新完成测量。测试账户数据和 ES 调用均位于本机。

## 多篇范围修复后的复测

沿用同一问题、账户隔离校验和语料版本。3 次顺序执行 P50/P95 为 515/656 ms，4 次并发提交为 906/1,453 ms，全程 3.297 秒。Python 进程采样 RSS 为 116.43–120.52 MiB。七份报告的已核验陈述都列出了两个地区与超标关系，每项模型调用数为零。故障复测在两个来源保存后切换语料代，暂停状态恢复后完成，两份来源哈希均保持一致，清理后基础索引仍有 859 篇。[最终七项记录](evidence/p8-native/859-final/summary.json) · [最终故障切换](evidence/p8-native/drift-final.json)

## 结论核验发布版复测

结论核验更新后，同一道题的 7 次请求均完成，并在已核验陈述中给出两个地区及超过 WHO 指南值的关系。顺序执行 P50/P95 为 328/500 ms，四次并发提交为 1,070/2,016 ms。采样 RSS 为 116.95–120.63 MiB，全程 3.344 秒。故障试验恢复了中断的任务，复核两个来源的哈希，清理了临时索引和别名。两项复测的模型调用数均为零。[发布版七项记录](evidence/p8-native/859-release/summary.json) · [发布版故障恢复](evidence/p8-native/drift-release.json)
