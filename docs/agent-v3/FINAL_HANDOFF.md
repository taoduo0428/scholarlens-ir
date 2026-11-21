# ScholarLens EvoResearch 第二阶段交接

2026-11-21。本地分支 `feat/evoresearch-quality-v2` 基于 `6779d2d23ce852ffaa233cf14f8a06d98a4e6a53`，本轮升级在独立工作树开发和验收。GitHub 公开 fork 为 [taoduo0428/scholarlens-ir](https://github.com/taoduo0428/scholarlens-ir)，两阶段代码共用[PR #1](https://github.com/taoduo0428/scholarlens-ir/pull/1)，目标是 fork 的 `zjl`。四个上游分支在交付时与 fork 逐一核对了提交 ID。本地 Git 的 `origin`、默认推送目标和 GitHub CLI 的默认仓库均指向用户 fork。`upstream` 保留原 Scarlett-web 仓库的读取地址，`fork` 别名保留给旧工作树。

## 运行工作台

环境为 Windows、Python 3.11.15、Node 24.18.0。下面的演示只用两篇内置样例、独立账户库和本机 Worker。新环境按锁文件安装依赖，运行时选择自己的新目录。PowerShell 从本仓根目录执行。

```powershell
python -m venv .venv
$py = (Resolve-Path .venv/Scripts/python.exe).Path
& $py -m pip install -r backend/requirements-lock.txt -r backend/research/requirements.txt
& $py -m tools.research_eval.check_environment
npm --prefix frontend ci --no-audit --no-fund
$env:VITE_DATA_SOURCE = 'api'
$env:VITE_API_BASE_URL = '/api'
$env:VITE_RESEARCH_ENABLED = 'true'
$env:SCHOLARLENS_RETRIEVAL_POLICY = 'V5'
Push-Location frontend
node node_modules/vite/bin/vite.js build --outDir ../output/quality-demo-ui
Pop-Location
& $py -m tools.research_demo --corpus fixture --runtime output/quality-demo-local --frontend output/quality-demo-ui --port 0
```

按终端输出的地址打开研究页，注册本地演示账户。输入 `Compare Cedar and Birch ranking trial method, dataset, metric and protocol`，论文范围填 `fixture:cedar,fixture:birch`，选择只读证据。展开三个研究子问题，进入报告点击来源并下载 Markdown。V5 仅供本地展示。正常创建任务的默认策略为 V1，V6/V7 的技能和参数实验只经离线入口运行。

最终 Chrome 实测使用实际 FastAPI、SQLite 和 Worker。该题因预算限制进入 partial，回查了 2 个来源，7 条结论中 6 条进入已核验区，1 条进入不可比区。浏览器逐字核对跳转后的高亮和导出的 Markdown，第二账户访问同一任务返回 404。另用受控 HTTP 逐一检查桌面 1440px、平板 820px、手机 390px 的布局以及暂停、恢复。真实模型调用为 0。

## 本次交付与实验

按用户许可的原文范围，研究图将任务拆为有依赖的子问题，检索论文和段落，由 Critic 根据当前缺口重新安排下一轮。在回查原文后，报告分别记录来源真实性、命题支持和实验条件。开发回放中有两个锚点被词面过滤，另两个出现在账本但缺少发布回查预算。候选并集和回查预留在相同每题 10 次工具上限下，使发布覆盖从 3/7 恢复到 7/7，实际工具调用从 44 次增至 46 次。[逐锚点审计](RETRIEVAL_LOSS_AUDIT.md)

冻结未见组的 18 题中，V1 与 V5 对 6 个可机械核对的位置都命中 6 个。缺失信息的 3 题都产生了已核验陈述。V5 共使用 152 次工具，V1 使用 136 次，增幅 11.8%。V5 的本机 p95 为 1556.8 ms，V1 为 787.6 ms。技能只在 3 道未见题触发，离线门禁记录 `no_demonstrated_gain`。默认策略继续使用 V1。[八组实验](EXPERIMENT_RESULTS.md)

冻结运行之后，用独立光学台架夹具检验了否定句的实验前提、陈述本句与所问计数量之间的关系。修订后的六道开发题重新执行 claim_eval，形成 4 条规则支持、2 条证据不足。该修订尚待另一批未见题评价。102 道候审题的材料校验通过。此次按固定规则抽取 36 题并实际执行，保存研究输出、原文位置与未填写的人工表格。人工 P@5、nDCG、结论支持率均为 null。[复核材料生成与评分](artifacts/README.md)

## 验证与审阅

|范围|运行记录和结果|
|---|---|
|旧 Agent 与 Harness|163 个旧接口断言通过，独立 Harness 11/11|
|研究后端|最终全套 188 passed、1 skipped。可选 ES 读取用例单跑通过|
|前端|45 项通过，类型检查、生产构建、受控 Chrome 及真实 Worker 工作台通过|
|原生语料|本机 ES 8.19.23 有 859 篇、49,420 条向量。事实、比较、多跳任务分别回查 4、3、3 个来源|
|上传、索引及兼容|初次扩展后端有 9 个本机依赖用例失败。在私有节点重新导入语料并核验向量后，9/9 通过，另 5 组实际上传集成含 163 个路由断言。原始 XML 在本地 `tools/audit/reports/upload-integration-20261121-020544-77d4d8a7f64c`|
|最终隔离后端整套|同一运行器分两次调用 pytest。上传组先在合成索引独立通过 5/5，随后在私有 859 篇语料上完成其余 587 passed、17 skipped，共 592 项通过。跳过项为另行验收的只读 ES 用例及需要显式原件与独立实服的 16 项历史交付检查。运行号 `upload-integration-20261121-024247-a9a3838d3b67`，临时节点已关闭，两个端口均已释放。|
|分阶段证据|[36 项验收映射](ACCEPTANCE.md)、[原始文件索引](artifacts/README.md)、[故障与定位案例](SECURITY_AND_FAILURES.md)、[历史工件哈希](artifacts/LEGACY_INDEX.md)|

常规复验使用以下命令。真实语料命令需要锁定的 LFS 对象和本机服务，实际模型调用另需用户授权。私有集成复验的参数为现有 ES 安装、MiniLM 目录及已核验的 `papers_index_ready.jsonl`，运行器只向它自行启动的临时集群导入数据。

```powershell
& $py -m pytest backend/tests/test_agent.py backend/tests/test_ai_responses.py backend/tests/test_agent_harness_reporting.py -q
& $py -m pytest backend/tests/research -q
& $py -m ruff check backend/research backend/tests/research tools/research_eval tools/research_evolution
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --check
```

## 发布、恢复与下一次验收

- 已实现并本地验证的范围包括研究问题 DAG、检索池、按问题判断、原文回查、工作台、离线候选程序及拒绝记录。架构、接口和阶段记录从[架构图](ARCHITECTURE.md)、[决策契约](DECISION_AND_CONTEXT_CONTRACT.md)、[阶段 E0](progress/E0.md)进入。
- 发布前按[验收表](ACCEPTANCE.md)复核各项 PARTIAL。真实模型、人工判定、4,000 篇端到端性能及生产部署均为 not_run。新的程序型技能的生产审批适配器为 not_implemented，在未见收益与审批门槛通过前只在离线沙箱解释。
- 下一轮以新的、按论文家族隔离的问题集检验拒答。分别统计已找到资料但问题未获回答、跨论文前提缺失、引用正确但命题过强三类错误。优先使用 36 份已准备的空表获取独立人工判断。新批次应在选择策略前冻结。
- 回退演示时退出本机服务，移除 `SCHOLARLENS_RETRIEVAL_POLICY` 后重新启动，新任务使用 V1。已创建的任务读取自己固定的版本。正式研究入口可通过 `SCHOLARLENS_RESEARCH_ENABLED=false` 关闭，前端以 `VITE_RESEARCH_ENABLED=false` 重建。持久数据恢复使用原有停机备份及新目录恢复流程。[恢复说明](../agent-v2/RECOVERY_AND_ROLLBACK.md)
- 本次公开交付包括源代码、测试、配置示例和脱敏统计回执。缓存、演示账号与原文材料保存在本地运行目录。
