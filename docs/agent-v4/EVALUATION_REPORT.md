# ScholarLens E9 字段核验与发布评测

2026-11-21 · 开发分支 `codex/evoresearch-next`

在两批新题中，E9 保留了有原文支持的答案，并对缺少版面或属性证据的字段停止发布。第一批 24 题包括 18 道真实摘要题和 6 道受控题。第二批 18 题来自另外 6 篇真实论文，每题给两篇论文的权限范围，全程按指定论文核对。逐题结果、语料和脚本摘要、调用量及时延保存在[机器可读回执](e9/acceptance.json)。

## 1. 阶段目标

本轮覆盖规格 A–E。核对用户 fork 的分支和数据，复现 V3，再为现有研究工作台增加字段级审核。验收同时检查正常作答、证据不足时的误发，以及复合题能否保留部分答案。[仓库审计与 V3 基线](E9_AUDIT.md) · [预注册设计](E9_DESIGN.md)

## 2. 原有问题

V3 的 V1 与 V5 在已开启的历史集均命中 6/6 个来源锚点，也均在 3/3 道明确缺失题中发布了已核验结论。旧 Critic 还可能把另一个问题读取的测量当成本问题的比较条件。两个现象都要求在发布前核对具体问题及所需字段。[V3 原始回执](e9/v3-baseline.json)

## 3. 技术设计

服务端将题目拆成有类型的字段，为每个字段登记所属问题、所需来源能力、最低证据数和比较条件。原文回读时记录问题归属。发布前按问题及显式依赖重新检查论文范围、语料版本、字符位置、内容摘要、语义关系与实验前提。模型可以给出语义意见，核验结果由服务端判定。

## 4. 修改位置

| 环节 | 从仓库根目录查看 |
| --- | --- |
| 字段、来源资格与发布判断 | [字段模型](../../backend/research/field_contract.py)、[核验规则](../../backend/research/field_gate.py)、[发布与导出](../../backend/research/field_publication.py) |
| 规划、归属、恢复与报告 | `backend/research/` 下的 `api.py`、`questions.py`、`graph.py`、`critic.py`、`evidence_graph.py`、`schemas.py`、`store.py`、`tools/registry.py`、`workspace_controller.py`、`reports.py` |
| 用户界面 | [研究报告](../../frontend/src/components/ResearchReport.tsx)、[响应类型](../../frontend/src/services/research.ts) |
| 实验与回归 | [第一批对照](../../tools/research_eval/e9_accept.py)、[第二批确认](../../tools/research_eval/e9_confirmation.py)、[历史重放](../../tools/research_eval/e9_regression.py)、[字段测试](../../backend/tests/research/test_e9_alignment.py)、[隔离测试](../../backend/tests/research/test_e9_scope_gate.py)、[浏览器验收](../../frontend/tests/e9-field-release.mjs) |

## 5. 使用方法

新任务由服务端读取 `SCHOLARLENS_E9_ENABLED=true` 开启 E9。浏览器端构建时启用 `VITE_RESEARCH_ENABLED=true`。默认研究策略仍为 V1。已有任务保留创建时绑定的策略。研究报告列出已核验原句、字符位置、未完成的字段及原因。例如，同时索取摘要首句和 PDF 页码时，有摘要即可展示首句。页码需要独立的版面证据。

## 6. 复现命令

从仓库根目录启动，先按项目说明准备后端依赖及前端锁定依赖。公开语料重放需要本地 Git LFS 中的 `data/kaggle_arxiv_papers_jsonl/arxiv_papers_final.jsonl` 对象。运行器校验 SHA-256。下面每次重放用新输出目录，避免覆盖前一次证据。ES 集成测试依赖已准备好的本机索引。

```powershell
$env:EVO_TEST_LOOPBACK_ES = '1'
python -m pytest backend/tests/research backend/tests/test_agent.py backend/tests/test_ai_responses.py backend/tests/test_agent_harness_reporting.py -q
$run = "output/e9-replay-" + (Get-Date -Format yyyyMMdd-HHmmss)
New-Item -ItemType Directory $run | Out-Null
python -m tools.research_eval.e9_accept --output "$run/en"
python -m tools.research_eval.e9_confirmation --output "$run/zh"
python -m tools.research_eval.e9_regression --output "$run/history.json"
$env:VITE_DATA_SOURCE = 'api'
$env:VITE_API_BASE_URL = '/api'
$env:VITE_RESEARCH_ENABLED = 'true'
Push-Location frontend
npm.cmd test
npm.cmd run verify:structure
npm.cmd run build
Pop-Location
$env:SCHOLARLENS_E9_ENABLED = 'true'
python -m tools.research_demo --port 0 --runtime "$run/ui" --corpus fixture
```

在第二个终端把 `SCHOLARLENS_URL` 设为上一步输出的本机来源地址（仅协议、主机、端口），执行 `node frontend/tests/e9-field-release.mjs`。该命令需要 Playwright 与 Chrome，可分别用 `SCHOLARLENS_PLAYWRIGHT` 与 `SCHOLARLENS_CHROME` 指定模块和可执行文件。

## 7. 实际测试

- V3 基线研究套件 189 项通过，包括本机 ES。实际 HTTP 服务与 ES 另完成 3 个顺序任务和 4 个突发任务。
- 最终应用代码的后端研究与 Agent 相关套件 386 项通过，用时 59.17 秒。E9 变更涉及的 Python 文件通过 Ruff。
- 前端 45 项测试通过。结构检查、TypeScript 检查及 Vite 构建通过。Chrome 在本地夹具上完成真实账号注册、任务创建、双字段展开和报告查询，1440 像素桌面与 390 像素手机视口均通过。此后前端代码相同。
- 在评测脚本完成静态检查修整后，又重放了三种策略的两批题。126 条记录除耗时外，所有记录字段与修整前相同。

## 8. 三组对照

“精确答对”要求实际发布指定原句或夹具属性。“缺失误发”统计缺失题中发布任意已核验结论的题数。“部分答对”同时要求指定原句正确、报告标记为部分可答。第二批另外检查引文来自指定论文。

| 第一批，24 题/策略 | 精确答对 | 缺失误发 ↓ | 部分答对 | 工具调用 | p50 / p95 毫秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| V1 | 4/9 | 4/9 | 0/6 | 96 | 430 / 597 |
| V5 | 4/9 | 5/9 | 0/6 | 123 | 575 / 1239 |
| E9 | 9/9 | 0/9 | 6/6 | 108 | 621 / 828 |

| 第二批，18 道中文题/策略 | 指定论文首句正确 | 坐标误发 ↓ | 部分答对 | 工具调用 | p50 / p95 毫秒 |
| --- | ---: | ---: | ---: | ---: | ---: |
| V1 | 2/6 | 4/6 | 0/6 | 132 | 697 / 1430 |
| V5 | 2/6 | 5/6 | 0/6 | 114 | 512 / 1296 |
| E9 | 6/6 | 0/6 | 6/6 | 114 | 723 / 1080 |

同题共享证据范围，每题最多 10 次工具、10 条证据、120 秒，采用零模型预算。表中耗时来自最后一次重放，p95 使用最近秩。共享主机的耗时随负荷变化。第二批源码在中文修复前冻结，论文与第一批互斥。代码明确按同一种问题结构出题，独立性主要体现在论文与内容。

**历史回归揭示的缺陷。** 首版 E9 在旧 18 题命中 6/6 个已知锚点，但在 3 道定位和 3 道干扰题中均未发布所需原句。将中文“开篇原句/摘要首句”和“解释”分开，并在多篇许可范围内核对指定标题后，这 6 道题均实际发布了可回查的原句，解释保留为缺口。3 道明确缺失题误发 0 次。另 9 道比较、实验条件和多跳题均无最终已核验结论。三类各 3 题，比较题标为不可直接比较，其余标为证据不足。其拒答是否适当仍待人工判定。

## 9. 安全与隔离核对

隔离测试覆盖兄弟问题共用证据、显式重读、无权来源、错误语料代次及原文摘要不符。模型给出的“相关”判断无法让主体不符的引文通过。第一批三种策略的范围外来源各为 0。线上检查仅取公开状态接口，审计时返回 HTTP 503。此次交付在独立开发分支和本机环境完成。

## 10. 已知局限

当前可核验来源使用字符位置。真实 PDF/OCR 的页码、坐标、表格和图号仍需相应的数据适配器。字段拆解和属性绑定依赖现有规则，自动样本集中在首句、显式属性和来源缺失。真实模型表现、开放题成功率和人工标注的检索质量尚待验证。102 道 Review 题均待人工审核。

## 11. 提交与版本记录

| Git 提交 | 记录 |
| --- | --- |
| `b81a435608bf733102ceb48d09442fb612991ea0` | fork 的 `zjl` 合并基线，[PR #1](https://github.com/taoduo0428/scholarlens-ir/pull/1) |
| `4aea8a75f50a9076ff2ee79a6d04c70b95bfcce0` | 本分支承接的 V4 工作台与实验报告 |
| `603f927010c9c69295fcf5ddb72caff7b6133c13` | E9 审计、设计、V3 回执和第一批验收脚本 |
| `0d4ac9be99b37a40595c73e601ca4585cb15db2a` | E9 后端执行链、报告与前端字段查看 |
| `ec6385085ead9d0e1299d3a205a0c296e2482d60` | 冻结第二批中文对照和历史重放，保存浏览器脚本 |
| `25d2c6c76676283a93c3994989425ed9dd78795a` | 中文复合问题与多论文原句修复 |
| `a30ebeb0927d53b1b23059affa327f762417ef6b` | 验收脚本静态检查修整，逐题结果复核一致 |

在分支的文档页打开 **History** 可查看每版内容和差异。PR 的 **Files changed** 列出相对目标分支的文档和代码变动。

## 12. 下一阶段

E10 的输入是待审 Review 数据。由独立审查者核对相关论文、原文位置、必须回答的字段、可答性和拒答是否合理，然后计算开放任务指标。优先复核本轮历史集中 9 道未发布结论的复杂题，并使用新题检验规则的泛化能力。
