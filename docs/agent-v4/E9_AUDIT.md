# E9 第一轮仓库审计与 V3 复现

2026-11-21 从用户 fork 读取分支和 PR 状态。集成分支 `zjl` 指向 `b81a435`，PR #1 已合并。两条 EvoResearch 远端开发分支均指向 `c1638cb`，相对 zjl 各落后一个合并提交。`main` 为 `ec3ef9f`，与 zjl 各自独有 4 和 84 个提交。`feat/pdf-parser` 为 `82a3a08`，相对计数同为 4 和 84。`jwj` 为 `1660f60`，落后 zjl 18 个提交。

main 多出 859 行正式论文 JSONL、860 行来源清单及配套说明。两个分支均含 Kaggle 论文数据的 LFS 管理记录。后续主分支集成应先保留上述三个文件，核对来源、LFS 对象和 ID，再通过单独 PR 评审。此次同步目的分支是独立的 `codex/evoresearch-next`。创建时本地 zjl 和 V4 工作树干净，另一个 EvoResearch 工作树的 porcelain 状态有 54 条，保留旧工作现场。新分支先检出 zjl 复现，再快进纳入五个既有 V4 提交，最后开发 E9。

## 模块和运行边界

- React/TypeScript 客户端在 frontend，FastAPI、账户和研究运行时在 backend。infra 保存服务配置，agent/benchmarks 与 tools/research_eval 负责离线数据和重放。前端锁定 npm 依赖，后端依赖锁和研究 constraints 分别位于 backend 和 backend/research。
- graph、worker、store 和 api 管理账户任务、调度、检查点、幂等及报告。questions、planner 和 plan_history 维护 DAG。critic 中测量候选与兼容对原本在题目循环外计算，允许另一个问题的测量满足本题。evidence_graph、claim_verifier、premises 和 synthesis 已具备原文、条件和语义检查。reports 发布前再通过工具核对来源，现有 EvidenceRef 使用字符定位。E9 承接这些入口和来源校验。
- 工具注册表、corpus、passages 和受控 external_sources 负责来源范围、检索、原文及来源权限。provider_adapter 和 harness 负责有限模型调用和期限。skills 与 Lab 保留候选实验记录。默认 V1。SQLite 分开存放账户、研究业务状态、LangGraph 检查点和实验记录。本地演示数据库存在，Git 无受跟踪的 SQLite 文件。
- 线上既有站点的公开 `/api/stats` 本次返回 HTTP 503。只做了只读连通核对，线上版本和故障原因待服务端证据。本机 ES 8.19.23 校验通过，原生验收按别名读取 859 篇论文和 49,420 个向量。
- Review v2 有 34 篇、102 题，均为 pending_human_review。种子集 36 条，smoke 6 条。冻结文件摘要、技能来源、实际配置和输出见 [基线回执](e9/v3-baseline.json)。

## 可复现基线

在 `b81a435` 上，使用独立临时目录和现有隔离 Python 环境重新执行如下模块。

| 命令或入口 | 实际结果 |
| --- | --- |
| `EVO_TEST_LOOPBACK_ES=1 python -m pytest backend/tests/research -q` | 189 passed，含本机 ES 只读集成 |
| `python -m tools.research_eval.run --suite smoke --mode research-v2 --offline` | 6 题，2 completed，4 partial，28 次工具，0 次模型 |
| `python -m tools.research_eval.agent_ablation --configs V1,V5 --split unseen`，传入上次冻结的 policy.json 及新输出目录 | 18 题，V1 和 V5 均命中 6/6 锚点，工具 136 和 152 次，三道缺失题均误发已核验命题 |
| `python -m tools.research_eval.native_acceptance`，传入预先核对的本机 cluster UUID 和独立 runtime/output | 顺序 3 题、突发 4 题，经实际 FastAPI、单 Worker 和本机 ES 完成，退出 0 |

缺失题误发与来源核验同时出现。下一阶段通过答案字段及问题级来源绑定处理这一缺陷。详细设计与验收门槛见 [E9 设计](E9_DESIGN.md)。
