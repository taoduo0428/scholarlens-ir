# ScholarLens EvoResearch 本地交接

在 Windows 用 Codex 或编辑器打开 `C:/Users/lenovo/Desktop/ScholarLens-EvoResearch` 即可继续修改。该工作树在 `feat/evoresearch-agent`，基线为 `zjl` 的 `3e130b0`。本轮代码及证据以本地文件交付。原工作树位于 `C:/Users/lenovo/Desktop/检索agent`，保留在 `zjl`。两个工作树共享 Git 对象和 LFS 存储。四条分支及各自材料的来源见[基线盘点](BASELINE_AUDIT.md)。

## 从本地开始

已准备的环境使用 Python 3.11.15。打开 PowerShell，执行以下两行。打开终端打印的回环网址，进入“深度研究”、注册本地演示账户，使用工作台发起任务。

```powershell
Set-Location 'C:/Users/lenovo/Desktop/ScholarLens-EvoResearch'
.venv/Scripts/python.exe -m tools.research_demo --corpus fixture --frontend output/research-demo-ui
```

可以输入 `Compare Cedar and Birch ranking trial method, dataset, metric and protocol`，将论文范围设为 `fixture:cedar,fixture:birch`。展开结论、点击引文定位原文，并导出 Markdown。本机 Chrome 实际走通这条路径，在 390px 和桌面宽度下核验了两个来源、八条成立的结论和一条因评测指标不同而不可比的结论。演示用独立数据库，按 Ctrl+C 停止。要使用真实论文摘要，启动参数改为 `--corpus seed --runtime output/research-demo-seed`。从新环境安装与构建的命令见[运行指南](USER_GUIDE.md)，端到端结果见[浏览器记录](evidence/p8-final/frontend-chrome.txt)。

## 改动位置

| 任务 | 实现入口 | 已验证的行为 |
|---|---|---|
| 提交、暂停、恢复、取消 | [研究 API](../../backend/research/api.py)、[Worker](../../backend/research/worker.py)、[SQLite 存储](../../backend/research/store.py) | 重复提交复用任务，按账户隔离，进程重启复用已提交的轮次，个人密钥丢失时等待重新绑定。 |
| 自适应检索 | [研究图](../../backend/research/graph.py)、[计划器](../../backend/research/planner.py)、[工具注册表](../../backend/research/tools/registry.py)、[执行时限](../../backend/research/harness.py) | 根据缺失信息选择搜索、逐段读取、提取或重新规划。按轮次、时间和工具额度停止，输出仍缺的论文或指标。 |
| 原文与结论 | [证据图](../../backend/research/evidence_graph.py)、[结论核验](../../backend/research/claim_verifier.py)、[报告](../../backend/research/reports.py) | 校验具体索引代次、论文、字符位置、引文与哈希，对结论保留来源、条件、冲突及缺口。 |
| 浏览器交互 | [页面](../../frontend/src/pages/ResearchPage.tsx)、[报告组件](../../frontend/src/components/ResearchReport.tsx)、[研究客户端](../../frontend/src/services/research.ts) | 持久任务列表、按序号补拉事件、逐条原文定位、账户隔离、Markdown 导出。 |
| 离线技能与策略 | [版本库](../../backend/research/skills/registry.py)、[离线实验](../../tools/research_evolution/experiment.py)、[评测题](../../agent/benchmarks) | 公开训练轨迹核验、候选比较、显式审批、原子版本发布和回滚。一个低调用候选在独立测试中退化，晋升被拒。 |
| 原站与兼容 | [接入点](../../backend/app1.py)、[旧评测执行器](../../tools/agent/run_harness.py)、[调查记录](P0_BACKEND.md) | V2 默认关闭。旧搜索、RAG、账户、上传、PDF、个人模型请求隔离和只读 MCP 走已有入口。 |

完整路径按阶段追踪，见 [P0](progress/P0.md)、[P1](progress/P1.md)、[P2](progress/P2.md)、[P3](progress/P3.md)、[P4](progress/P4.md)、[P5](progress/P5.md)、[P6](progress/P6.md)、[P7](progress/P7.md)、[P8 与 20 项验收](progress/P8.md)。在此工作树运行 `git status --short --untracked-files=all` 可列出本地修改和新增文件。项目根目录的 Git diff 只显示已跟踪文件。新增的代码、评测、证据与文档需要一并保留。

## 实验与已知限制

- 实际部署形态是 FastAPI、一个本机 Worker、LangGraph 和两个职责不同的 SQLite 数据库。每个正式任务固定语料、技能及策略版本。浏览器控制沿用账户鉴权，来源文本按需读取。标准与深入任务由服务器给出不同预算。[运行架构](ARCHITECTURE.md) · [预算和公开 API](TASK_CREATION.md)
- 本机 ES 在 859 篇、49,420 个向量上完成正式应用验收。七次提交使用同一真实问题，分别覆盖指定论文和全库搜索。每次结论均写出两个地名及超过 WHO 指南的关系，引用可从 ES 独立读回。并发测试采用四个提交者和一个执行 Worker。[逐项记录](evidence/p8-native/859-release/summary.json) · [故障恢复](evidence/p8-native/drift-release.json)
- 冻结等预算对照中，六道开发题上旧流程命中 7/7 个预置原文块，自适应流程命中 3/7 个。B0–B5 比较记录检索与执行轨迹。完整文本报告另做正式应用试验和六道开发题回查。完整发布器修复了电流问题误引模型准确率、操作名称没有直接回答的问题。最终六题均为部分完成，命中 5/7 个预置来源块，多跳题仍有缺口。[实验汇总](EXPERIMENT_RESULTS.md) · [修复后的逐题发布回查](evidence/p8-final/dev-publication-aligned.json)
- 4,000 篇对应本地核验过的项目数据。新增 3,141 篇缺原始 PDF，浏览器应使用可用的原文字符位置。102 道候选的人工审定数为 0，P@5、nDCG、MRR 和人工结论支持率保留为空。个人模型的协议、失效、超时与凭据恢复采用受控测试，收费模型的真实质量和开销待测。[数据来源](P0_SOURCE.md) · [盲评包与导入方法](ANNOTATION_GUIDE.md)
- 功能开关、依赖和预算经过 Windows 本地验证。生产容量、跨机多 Worker 和真实账号数据迁移属于单独发布范围。[安全与隐私](SECURITY_AND_PRIVACY.md) · [独立审查](INDEPENDENT_REVIEW.md)

## 恢复与回滚

终止本地演示后使用相同启动参数和 runtime 可查看原任务。恢复任务时保留原预算截止时间、账户、索引代次和审核版本，个人模型任务按界面提示重新绑定。需要备份研究任务时，在 Worker 停止后用 `ResearchStore.backup(new_path)` 生成备份，使用 `ResearchStore.restore(snapshot, fresh_runtime)` 恢复到全新运行目录。回退 V2 时关闭后端 `SCHOLARLENS_RESEARCH_ENABLED`，前端关闭 `VITE_RESEARCH_ENABLED` 后重建。离线技能按审核记录切回上一批准版本。生产部署、代码推送、合并和收费模型调用均需单独授权。[恢复操作](RECOVERY_AND_ROLLBACK.md) · [版本回滚命令与试验（历史归档索引）](../agent-v3/artifacts/LEGACY_INDEX.md#ref-b26c8d7fb009)
