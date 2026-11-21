# ScholarLens 工程交付记录 · 2026-11-21

## A. 总体结果

E9.1 将复合问题拆成各节点负责的字段，为跨论文判断保存原文和前提。恢复任务时校验初始问题图，遇到损坏记录就隔离当前任务，工作线程可继续完成其他人的任务。任务详情和前端报告支持核对计划哈希及证据位置。E10 已提供双人评审包、裁定流程和按独立判断计算蕴含准确率的工具。

在相同预算下，E9.1 能正确摘录独立组的 6 个原句，6 个缺少版面的样本均未误发坐标。真实摘要综述成功 0/6，受控综述成功 3/4。工程改动和离线验收可在 `zjl` 复核，真实模型联调、Elasticsearch 联调和人工学术质量评估各有独立的验收条件。[逐题评测报告](EVALUATION_REPORT.md)

## B. 文件与用途

以下路径相对仓库根目录。`+` 为新增，`M` 为修改。相对本轮基线没有删除文件。

| 路径 | 用途 |
|---|---|
| `M backend/requirements-lock.txt` | 更新 PDF 解析及 OpenTelemetry API 的锁定版本。 |
| `M backend/research/accounting.py` | 在任务预算账本登记模型用量回执。 |
| `M backend/research/api.py` | 在认证后的任务详情返回计划封存、隔离、用量数据。 |
| `M backend/research/evidence_graph.py` | 关联证据图、字段判断和综述推导。 |
| `M backend/research/field_contract.py` | 将问题节点的研究要求编译为字段契约。 |
| `M backend/research/field_gate.py` | 检查字段与来源、前提及跨论文比较条件。 |
| `M backend/research/field_publication.py` | 把核验结果和综述映射到发布层。 |
| `M backend/research/graph.py` | 在研究图阶段使用版本化策略，接入封存、阶段追踪与回执。 |
| `M backend/research/harness.py` | 工具调用跨线程传递上下文，接入字段契约。 |
| `+ backend/research/node_fields.py` | 在服务端限制节点字段的归属、来源和依赖。 |
| `+ backend/research/overview.py` | 生成可回溯到两篇论文的直接观察与综合判断。 |
| `M backend/research/provider_adapter.py` | 从模型响应提取标准化用量数据。 |
| `M backend/research/questions.py` | 保存初始问题图的可验证摘要与版本。 |
| `M backend/research/reports.py` | 输出任务报告的综述、核验信息与用量。 |
| `M backend/research/schemas.py` | 描述研究状态、计划和字段的持久化模型。 |
| `M backend/research/store.py` | 验证存储记录和初始计划，保留并隔离损坏任务。 |
| `+ backend/research/telemetry.py` | 可开关的阶段 span，白名单属性，默认在本地运行。 |
| `M backend/research/worker.py` | 单任务损坏后继续处理队列。 |
| `M backend/research/workspace_controller.py` | 更新复合字段、读版面和综述的调度。 |
| `+ backend/tests/research/test_e10_review_scoring.py` | 测试独立标注、未裁定情况、指标分母和蕴含判断。 |
| `+ backend/tests/research/test_e91_hardening.py` | 覆盖节点字段、不可变计划、证据归属、综述及缺口。 |
| `+ backend/tests/research/test_runtime_receipts.py` | 测试回执、损坏任务隔离、用户归属和阶段追踪。 |
| `M frontend/src/components/ResearchReport.tsx` | 修正报告展开证据时使用的来源键。 |
| `M frontend/src/services/research.ts` | 同步前端读取的研究接口字段。 |
| `M frontend/tests/e9-field-release.mjs` | 通过实际浏览器检查复合任务、报告及刷新恢复。 |
| `M tools/research_eval/e9_confirmation.py` | 中文回归集可指定四种策略。 |
| `M tools/research_eval/e9_regression.py` | 历史任务按指定策略回放。 |
| `+ tools/research_eval/v5_holdout.py` | 按预注册规则抽取独立论文并生成受控样例。 |
| `+ tools/research_eval/v5_compare.py` | 同题对比四种策略，检查双来源前提与逐题延迟。 |
| `+ tools/research_eval/e10_pack.py` | 准备双评、裁定、原文定位和带哈希的运行材料。 |
| `+ tools/research_eval/e10_score.py` | 校验评审输入并计算有分母的人工指标。 |
| `+ tools/research_eval/v5_evaluation_report.py` | 导出逐题统计、策略摘要和论文组重采样结果。 |
| `+ docs/agent-v5/PROTOCOL.md` | 记录基线、分支及独立实验取样协议。 |
| `+ docs/agent-v5/RUNTIME_CONTRACT.md` | 定义隔离、可观测性和模型回执契约。 |
| `+ docs/agent-v5/ANNOTATION_GUIDE.md` | 说明评审者如何独立判断和交付裁定。 |
| `+ docs/agent-v5/judgment.schema.json` | 定义单题判断的输入结构。 |
| `+ docs/agent-v5/pending-review.json` | 保存待审清单和来源标识。 |
| `+ docs/agent-v5/evidence/results.json` | 保存四策略逐题值、冻结数据哈希及人工分母。 |
| `+ docs/agent-v5/EVALUATION_REPORT.md` | 解释四策略成绩、失败样本和统计限制。 |
| `+ docs/agent-v5/IMPLEMENTATION_SPECS.md` | E13–E16 的工程审计和后续实施条件。 |
| `+ docs/agent-v5/FINAL_ENGINEERING_REPORT.md` | 本轮工程交付和复核记录。 |
| `M README.md` | 增加从项目首页到本轮报告和标注说明的入口。 |

## C. 测试、命令与首轮失败

以下命令从开发工作树执行，`python` 为测试虚拟环境，`PYTHONPATH` 首项为隔离安装补丁依赖的 `output/v5/verified-deps`。离线后端设置 `EVO_TEST_LOOPBACK_ES=0`。pytest 各次使用独立 `--basetemp`，下表省略该参数。评测命令的输出路径需用新目录或新文件。

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端研究测试 | `python -m pytest backend/tests/research -q` | 退出 0，245 通过、1 跳过。 |
| 后端完整相关套件 | `python -m pytest backend/tests/research backend/tests/test_agent.py backend/tests/test_ai_responses.py backend/tests/test_agent_harness_reporting.py -q` | 退出 0，408 通过、1 跳过。包含上一行。 |
| 安全、运行时与评分复核 | `python -m pytest backend/tests/research/test_runtime_receipts.py backend/tests/research/test_e10_review_scoring.py -q` | 退出 0，14 通过。 |
| 前端、结构、类型与打包 | 在 `frontend` 执行 `npm test`、`npm run verify:structure`、`npm run build` | 45 项通过。结构检查、`tsc --noEmit` 和 Vite 生产构建均成功。 |
| Ruff 收尾检查 | `ruff check tools/research_eval/v5_evaluation_report.py backend/research/telemetry.py backend/tests/research/test_runtime_receipts.py` | 首次退出 1，报告导出器 import 排序触发 I001。修复后退出 0，重新导出的结果文件字节一致。 |
| 英文和中文四策略 | `python -m tools.research_eval.e9_accept --output output/v5/95a-en --policies V1 V5 E9 E9.1`，`python -m tools.research_eval.e9_confirmation --output output/v5/95a-zh --policies V1 V5 E9 E9.1` | 各退出 0，24 道和 18 道均保留四策略逐题结果。 |
| 历史四策略 | 对每个策略执行 `python -m tools.research_eval.e9_regression --policy POLICY --output output/v5/95a-history/POLICY.json` | 四次退出 0，均为 18 道。 |
| 新独立组与 E10 | `python -m tools.research_eval.v5_compare --output output/v5/95a-holdout`，`python -m tools.research_eval.e10_pack --output output/v5/accepted-e10 --include-run`，`python -m tools.research_eval.e10_score output/v5/accepted-e10 --output output/v5/accepted-e10/score.json` | 22 题 × 4 策略有结果。111 份待审任务可读，评分器输出人工分母 0。 |
| 汇总与重现 | `python tools/research_eval/v5_evaluation_report.py --en output/v5/95a-en --zh output/v5/95a-zh --history output/v5/95a-history --holdout output/v5/95a-holdout --review output/v5/accepted-e10 --trial-commit 95a7c0c --legacy-commit 95a7c0c --dest output/v5/fresh-export.json` | 退出 0，两次导出的 SHA-256 相同。 |
| Chrome 工作台与 Lab | 对隔离演示服务执行 `node frontend/tests/e9-field-release.mjs` 和 `node frontend/tests/workspace-v4-live.mjs` | 两条浏览器脚本输出 PASS。证据可展开，缺口可见，刷新可恢复计划。工作台和 Lab 在 1440、820、390 像素无横向溢出，覆盖跨用户与 Lab 权限。 |

计划首次封存后，旧调度器更新优先级触发 `immutable question plan`，首轮回归 230 通过、2 失败。`76614c6` 保留原始 DAG 的封存边界并兼容合法调度更新，针对性重跑 20 通过。后续完整相关套件结果见表。

本机真实 ES 检查显式启用后，相关套件 394 通过、1 失败。附加 PDF/上传组 15 通过、1 项准备错误。两处均连接 `127.0.0.1:9200` 被拒绝。真实 ES 验收状态为阻塞。供应商模型调用需在配有凭据的环境验收。隔离浏览器使用演示材料和本地库快照。

## D. 四策略结果

独立组原句正确数依次为 V1 1/6、V5 1/6、E9 6/6、E9.1 6/6。缺失版面误发数依次为 5/6、5/6、0/6、0/6。英文和中文的正确部分回答在 E9、E9.1 中均为 6/6。E9.1 平均 4.41 次工具调用，独立组 p50 为 535 毫秒、p95 为 1194 毫秒。所有策略模型调用为 0。False Refusal、Answerability Accuracy 和 Claim Support 的人工分母均为 0，指标为 N/A。[四策略完整表](EVALUATION_REPORT.md) · [逐题统计](evidence/results.json)

## E. 安全与运行边界

| 问题 | 处置优先级 | 验证与剩余条件 |
|---|---|---|
| 一个损坏任务可能中断队列，其他用户的任务会排队等待 | 高 | 按任务隔离并保留原记录。运行时测试覆盖后续任务继续执行和所有权检查。恢复损坏任务须使用一致性备份。 |
| 跨线程观测丢失上下文，模型用量可能缺测 | 中 | 跨线程传递上下文，阶段属性采用白名单。缺失计数保留为未知。真实供应商回执和计费待联调。 |
| PDF 解析、遥测两个锁定包共命中 8 条已知公告 | 高优先级修复，非统一 CVSS 评级 | `pypdf` 更新至 `6.21.4`，`opentelemetry-api` 更新至 `1.45.2`。`pip-audit` 复扫 48 个后端与 24 个研究依赖均未报已知漏洞。前端 `npm audit` 结果为 0。 |
| 公开提交可能带入秘密或研究材料 | 发布前检查 | Gitleaks 使用 `git --redact --log-opts=c698621..HEAD` 扫描本轮提交。公开结果只包含题目、来源标识和统计，评审原文、数据库、凭据留在本地。最终扫描和合并回执随 PR 留存。 |

## F. 人工评审状态

102 道 Review 题和 9 道历史优先题均已生成材料。111 题待人工标注，人工确认、双人完成、分歧裁定均为 0。标注一致性待至少两位独立评审完成重叠样本后计算。下一步可以直接使用预制评审包。[标注指南](ANNOTATION_GUIDE.md)

## G. Git 交付

集成分支为公开 fork 的 `zjl`，开发分支为 `codex/e9-hardening-e10`。起点 `c698621` 来自 PR #2。本轮所有评测的最终研究代码为 `95a7c0c`。GitHub 在下列 PR 的 Commits 和合并事件保存完整 SHA、差异及时间。报告归档提交和合并提交可在 #4 的提交记录中查询。

| 阶段 | Git 记录 |
|---|---|
| 预注册、字段与综述、调度兼容、E10 工具 | `3bbc13b`、`a82acae`、`76614c6`、`abcb356`。已通过 [PR #3](https://github.com/taoduo0428/scholarlens-ir/pull/3) 合入 `zjl`，合并 SHA `779d257`。 |
| 运行时、依赖、证据展开、独立蕴含评分及报告 | `29bb077`、`95a7c0c` 和本报告归档提交。交付与最终合并时间见 [PR #4](https://github.com/taoduo0428/scholarlens-ir/pull/4)。 |

本轮交付目标限定为 `zjl`。`main` 的核对值为 `ec3ef9f`。生产部署不在本次交付中。

## H. 下一阶段

先给 9 道复杂题做双人评审，确定现有材料可回答的字段及证据位置。再沿 6 组真实摘要的候选检索、原文定位、前提核验和发布步骤逐项排查，用同一批人工判断衡量错误拒答与支持率。最后在隔离环境验证真实 ES、授权 PDF 和模型回执，再决定是否推进生产发布。E13–E16 各项验收与回退条件见[实施规格](IMPLEMENTATION_SPECS.md)。
