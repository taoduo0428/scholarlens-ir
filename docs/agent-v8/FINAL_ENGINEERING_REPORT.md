# ScholarLens PRA 工程验收

2026-11-23。公开 fork 的目标分支为 `zjl`。开发从 `fd4927c` 开始，该提交的文件树与本机原分支 `c1add80` 一致。工作区已有的 E11 修订是本轮对照的一部分。复核指定的铁路调度实验后，重新运行了全部 111 道诊断题和 28 组历史任务，原文件保留。

## 可交付的答题能力

复杂任务的增益集中在逐篇阅读。按相同预算，至少直接回答一项的正例从 15/70 升至 17/70，早期已提交版本为 12/70。3 个新增系统字段分别对应资源受限项目调度目标、作业车间研究目标、时间序列研究目标。此前已答的室内温控题增加了论文明确说明的系统设计范围。候选版的 24 条直接陈述逐条通过原文、归属和位置的独立复查。来源回读通过率为 24/24。

按系统拆出的全部字段，完整发布仍是 1/70。111 道题的任务状态与 Silver 标签完全一致的数量是 42。70 道正例包含 209 项人工语言描述的 Silver 复合要求，系统拆分成 271 项核验义务。19/271 为系统字段覆盖。真实任务回答率、误拒答、全组综合和成本分别在消融记录中列出。全部模型离线运行成本为零，人工 Gold 样本为零。

历史 28 组中全组综合覆盖为 1/28。开发前独立封存的 30 篇论文组成 12 个论文组，A、B、G 均为 0/12。12 组的缺版面负对照没有直接发布坐标。B 与完整方案在诊断集上的答案增益相同。建议当前生产继续使用 E11，保留 B 作为效果对照，G 通过研究环境变量供定向验证。

## 已运行的验收

|验收|命令或入口|实际结果|
|---|---|---|
|冻结语料诊断|每组运行 `python -m tools.research_eval.v6_replay --policy E11 --pra-arm <A–G> --output <独立目录>`|每组 111 题，退出 0|
|字段和来源评分|`tools.research_eval.pra_summary` 从上述逐题回放读取正式字段与原文|7 份逐题 JSONL 及指标摘要，退出 0|
|历史与迁移|`tools.research_eval.v7_compare`、`tools.research_eval.pra_holdout`|历史每版 84 项，每个留出实验组 24 项，退出 0|
|后端全量|`tools.research_eval.v6_vector_fixture --full-suite --delivery backend/.runtime/p0-delivery`，另传本次 ASCII 路径 ES 发行版及停止的原始索引目录|921 项通过，10 项因可选追踪库跳过，0 项失败，退出 0|
|补跑追踪|`test_otlp_delivery.py`、`test_optional_sdk_private_spans`、`test_authenticated_api_to_worker_trace`，加载项目固定版本的追踪库|15 项通过，退出 0。按 JUnit 用例 ID 核对，覆盖全部 10 项跳过用例。两批合计 931 个不同后端用例通过|
|前端|`npm test`、`npm run verify:structure`、TypeScript 检查与 Vite 生产构建|47 项前端测试通过，结构、类型及启用研究表单的 API 模式构建通过|
|来源与权限浏览器旅程|`tools.research_eval.v6_browser --e11`，隔离 Chrome|2 篇论文档案、4 对原句与定位、PDF 表格单元格、报告下载、会话恢复和账号隔离通过|
|真实论文产品路径|`tools.research_eval.pra_product` 调用现有 `real-workbench-live.mjs`|Chrome 157 在回环端口 62632 完成注册 201、登录 200、检索、提问、定位与导出。索引含 859 篇真实论文。该题显示缺证，5 处原文可定位。Markdown 7,050 字节，页面错误 0，匿名读取 401。临时服务已关闭|
|真实供应商|`SCHOLARLENS_PRA_ARM=G python -m tools.research_eval.v7_live_research --live --call-budget-only`|BLOCKED。当前测试进程缺少模型地址、名称和密钥，请求 0 次，没有供应商延迟和费用回执|
|受控模型传输|相同入口使用 `--controlled`|4 次模型请求，规划、决策、分析、综合均有回执，1 个模型选中的档案字段完成原文核验，退出 0|
|安全与兼容|原文哈希回读、访问范围回归、Ruff、安全依赖检查、前端锁文件审核|83 个解析后的 Python 包和前端锁文件均无已知漏洞。Ruff 通过。保留原有 HTTP 接口、数据库结构、引用与 Markdown 导出|

第一次全量运行缺少项目已有 PDF 布局依赖，出现 2 项失败。按锁文件在隔离目录装入依赖后完成正式运行。ES 复制索引包含 49,420 条向量，结束后源索引签名一致，验收端口已关闭。最初一次受控模型测试暴露旧验收程序只读取旧字段名的问题，更新验收程序后四个阶段均通过。真实供应商状态单独记录。

## 代码、报告和复核边界

本轮沿用 FastAPI、LangGraph、SQLite、Elasticsearch、原有混合检索、React、Docker 和 OpenTelemetry。实验组只由服务端 `SCHOLARLENS_PRA_ARM` 在 E11 下指定，持久化入任务状态，默认 A。完整代码变更可由本分支相对于 `fd4927c` 的 Git 差异复核。

- [架构与实验契约](PRA_ARCHITECTURE.md)
- [论文档案](PAPER_PROFILE_REPORT.md)
- [证据图](EVIDENCE_GRAPH_REPORT.md)
- [两两关系](PAIRWISE_REASONING_REPORT.md)
- [缺口控制](GAP_CONTROLLER_REPORT.md)
- [答案编译](ANSWER_COMPILER_REPORT.md)
- [A–G 消融和失败分析](ABLATION_REPORT.md)
- [各组指标及逐题文件摘要](ablation-final/metrics.json)

真实问答的主要剩余损失仍是论文归属与问题相关性。动态术语归并、互补关系、跨来源因果和同条件矛盾都需要足够的原文前提。现有控制器在部分原文缺失的任务上保持有界运行，消融尚未显示工具节省。字段提取、工具选择、推理关系的真实语义准确率仍缺独立字段级人工标注。自动计算的来源准确率、运维恢复用例和 41 个负例的拒答结果各自只覆盖其测试范围。
