# P1 离线 Evaluation Harness

## 数据和版本

真实种子集来自固定分支 `82a3a083` 的新增论文 JSONL，选择 12 篇论文的摘要编制 36 个任务。六类各 6 条，包含事实定位、跨论文比较、多跳、结构化指标、不可比条件、越界及无证据。每个主题使用一对论文，同组仅归入一个划分。推荐、语言模型、机器翻译和摘要为训练集 24 条，图学习为开发集 6 条，信息检索为保留集 6 条。训练/开发 CLI 仅评测相应划分。另有两篇合成短文、六个 smoke 工程样例。

评测运行前从本机 Git 提取 LFS 指针、校验 151,152,468 字节原件的 SHA-256，用旧版项目分块函数生成 chunk ID，再检查原文字段、块定位符、引文起止字符位置和引文哈希。实际验证了 55 个真实来源锚点。题目、完成标准与独立 rubric 可供复核。真实任务为机器辅助编制、等待人工评审的种子题。人工金标准为 0 条。冻结快照写入 SHA-256，并为 Windows checkout 固定 LF；真实原文留在原语料对象里。[任务和快照](../../agent/benchmarks/) · [验证输出](evidence/p1-eval/seed-validation.json)

## 运行与输出

在隔离 worktree 根目录使用其虚拟环境，在新建的输出目录执行。命令中的 `python` 指该虚拟环境解释器，`reports` 为可写目录。已有实验输出受到独占创建保护。

```powershell
New-Item -ItemType Directory reports
python -m tools.research_eval.validate_dataset --dataset agent/benchmarks/seed-v1.jsonl
python -m tools.research_eval.run --suite smoke --mode legacy --offline --output reports/legacy.json
python -m tools.research_eval.run --suite smoke --mode v2-placeholder --offline --output reports/p1.json
python -m tools.research_eval.compare --base reports/legacy.json --candidate reports/p1.json
python -m tools.research_eval.run --suite seed --split dev --mode legacy --offline --output reports/seed-dev.json
python -m pytest backend/tests/research/test_eval_p1.py -q --basetemp .venv/pytest-eval-<unique-id>
```

旧 Agent 实际执行 `ResearchAgent.run(operation="evidence")`，调用离线词项重合排序和逐字读回。这项测量覆盖已有 Agent 的证据流程。每个真实任务搜索其指定的两篇摘要。ES、全库发现、真实个人模型、人工相关性和结论正确性仍待后续实验。对照 runner 隔离 rubric、gold 与来源锚点。每条记录包含任务、执行轨迹、来源哈希、执行结果和耗时。比较器对齐数据、语料、输入范围及工具预算，遇到 placeholder 时质量和延迟差值均为 null。

| 执行 | 案例 | 状态 | 工具 / 模型调用 | P50 / P95 ms |
|---|---:|---|---:|---|
| 旧 Agent，smoke | 6 | 5 条有证据，1 条证据不足 | 12 / 0 | 0.7384 / 0.9931 |
| P1 V2 骨架，smoke | 6 | 6 条 not_implemented | 0 / 0 | null / null |
| 旧 Agent，真实 dev | 6 | 6 条检出证据 | 12 / 0 | 0.6315 / 1.0732 |

开发集的无证据题也命中了词面重合片段。这提供了 P3/P4 的负例，后续必须分别检查证据对问题的支持和指标可比性。上述耗时是六题单次离线执行，计时含 Agent 创建和工具处理，源文件预加载不计入。三次运行均退出 0，付费调用数 0，人工支持率、P@5、nDCG 等为 null。[smoke 原始记录](evidence/p1-eval/legacy-smoke.json) · [dev 原始记录](evidence/p1-eval/legacy-dev.json) · [占位输出](evidence/p1-eval/placeholder-smoke.json) · [比较结果](evidence/p1-eval/compare.json)

## 测试与交接

首次 pytest 使用系统临时目录，4 项通过、6 项因 Windows 拒绝访问临时目录而在 setup 报错，退出 1。改用 worktree 自有的唯一 basetemp 后通过 10 项。加入人工复核数据契约测试后复跑，最终 **11 passed（0.71 秒），退出 0**。覆盖错误引用位置、伪造 chunk/标签、越界来源、重复任务、报告不可比较、runner 隔离标注、holdout 拦截及人工评审数据验证。[初始错误](evidence/p1-eval/pytest.txt) · [最终测试输出](evidence/p1-eval/pytest-review.txt)

实现涉及 `tools/research_eval/{inputs,seed_definitions,build_seed,validate_dataset,run,compare}.py`、`agent/benchmarks/` 与 `backend/tests/research/test_eval_p1.py`。可将种子重建到新文件后比较哈希，例如 `python -m tools.research_eval.build_seed --suite seed --output reports/rebuilt.jsonl`。本阶段的可比较项为同一任务与来源身份、离线执行行为和检查结果；后续接入实际 V2 时新增 adapter，保留 P1 基线快照。
