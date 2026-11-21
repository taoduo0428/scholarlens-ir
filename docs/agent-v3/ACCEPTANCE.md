# 最低验收用例与覆盖边界

下表沿用规格第 18 节的编号。Python 测试路径均以 `backend/tests/research/` 为起点。在项目根目录可用 `python -m pytest backend/tests/research/<文件> -q` 单独复测。全套最后一次执行为 188 passed、1 skipped。可选本机 ES 路由另有独立验收。实验、前端和隔离后端运行入口见[证据索引](artifacts/README.md)。

|编号|验收内容|实现或机制|可复查测试或输出|判定|
|---:|---|---|---|---|
|1|单轮与图执行逐来源核对|trace_loss 对齐论文、片段、阶段|trace-v1.json、trace-v2-union.json|PASS 开发 6 题|
|2|检索私有范围|工具注册表在发现与回读时执行 ACL|test_research_tools.py、test_scope_coverage.py|PASS|
|3|保留高排名候选|broad_recall 保存受限论文池、分论文验证|test_broad_recall.py、trace-v2-union.json|PASS 有限池|
|4|多跳前置关系|questions 构建并校验 DAG|test_questions.py、test_research_decision_regressions.py|PASS|
|5|比较所需的评测条件|条件需求节点、两篇来源、元数据对齐|test_critic.py、test_claim_report.py|PASS 受控条件|
|6|泛词与无答案|问题相关性、量纲、对象与计数绑定|test_question_alignment.py、test_research_decision_regressions.py、locked-unseen/summary.json|PARTIAL 未见缺失题 3/3 误发|
|7|非法模型计划|typed validator、一次修正、确定性回退|test_questions.py、test_plan_contract_compatibility.py|PASS 受控模型|
|8|跨语言改写保留限制|保留原问题并附加目标|test_broad_recall.py|PASS 中英夹具|
|9|缺口驱动再检索|graph 更新工作项、重新选查询|test_execution.py、test_scope_coverage.py|PASS|
|10|无增益时停止|连续空结果与预算停止|test_execution.py、test_budget_enforcement.py|PASS|
|11|未找到指定论文|按 scope 与已核验论文的差集写报告|test_scope_coverage.py、test_claim_report.py|PASS|
|12|同名测量不可比|比较数据集、协议、设置、单位|test_critic.py、test_claim_report.py|PASS|
|13|相反陈述与不同前提|premises 对显式对齐、不同、缺失条件作三种判断|test_research_decision_regressions.py、test_claim_report.py|PARTIAL 仅覆盖可解析的显式条件和同构句|
|14|改写引文、哈希篡改|原文回查和摘要比对|test_claim_report.py、test_release_judge.py|PASS|
|15|真实原文与问题回答|复核命题、量纲、所问计数对象|test_release_judge.py、test_research_decision_regressions.py、独立组拒答|PARTIAL 开放问题相关性缺人工复核|
|16|截断文本|排除字符窗首尾不完整句，要求逐字回查|test_question_alignment.py、test_claim_report.py|PASS 受控窗口|
|17|准确率与设备电流|目标量纲与原文绑定|test_question_alignment.py、test_release_judge.py|PASS|
|18|比较证据不足|输出 partial 并保留来源和缺口|test_critic.py、native-questions.json|PASS 在实跑案例中|
|19|语料代次变化|工具再次确认代次，变更时暂停|test_service_boundaries.py|PASS|
|20|暂停、取消、恢复|控制请求与确认事务、存量 checkpoint、发布前最后读取|test_execution.py、test_process_resume_v3.py、test_research_decision_regressions.py、test_publication_deadline.py|PASS|
|21|个人 Key 泄露|仅内存重新绑定，持久态作哨兵检查|test_service_boundaries.py、test_worker_admission.py|PARTIAL 已查持久态，前端仅有受控演示与构建|
|22|原文内恶意指令|固定工具表、带权限的调用契约|test_research_tools.py、test_service_boundaries.py|PASS 夹具|
|23|跨账户访问|所有者绑定、上传权限、训练只许公开轨迹|test_store.py、test_research_tools.py、test_evolution_gates.py、ui-api.log|PASS 已测路径|
|24|耗尽预算仍可交付|检索预留最后回读次数，报告列出剩余缺口|test_claim_report.py、test_broad_recall.py、trace-v2-union.json|PASS|
|25|慢工具与唯一 Worker|有界并发及 deadline|test_publication_deadline.py、test_budget_enforcement.py|PASS|
|26|技能训练与来源篡改|白名单操作、重新计算公开训练指纹|test_skill_program.py、test_evolution_gates.py|PASS|
|27|无收益拒绝晋升|gate 写版本和拒绝原因，适用策略留在沙箱|skill-decision.json、locked-unseen/summary.json|PASS 拒绝|
|28|低成本伴随安全或拒答退化|硬门槛优先于工具开销|test_skill_program.py、test_evolution_gates.py|PASS|
|29|受控与真实模型标记|执行记录与成本分项|test_plan_contract_compatibility.py、harness/summary.json、dev-ablation/summary.json|PASS 个人模型 0 次|
|30|桌面、平板和手机工作台|QuestionPlan、ResearchReport、账户隔离|frontend/tests/research-workbench-browser.mjs、ui-api.log、screens/|PASS 受控 HTTP 三尺寸，真实 Worker + Chrome 跨账户、原文、下载|
|31|旧业务协议|旧 API、上传、PDF、向量、模型协议回归|verified-isolated-backend.log、隔离集成 legacy.xml、junit.xml|PASS 已运行组 592 通过，另外 17 项的范围见最终交接|
|32|坏计划、超长上下文、429|有界规划和字节上限|test_questions.py、test_layered_context.py、test_plan_contract_compatibility.py|PASS|
|33|真实语料可定位|固定具体索引与代次、用户范围及来源|native-questions.json、read-only-es.log、隔离 ES 报告|PASS 本机 859 篇，3 种提问|
|34|无人工结果时保留空值|空表、签核验证、候评评分|test_review_pack.py、review-36/pending-scores.json|PASS 36 题未签|
|35|实际资源与错误|逐题保存工具数、模型数、时延、错误、命中和终态|dev-ablation/、locked-unseen/、EXPERIMENT_RESULTS.md|PASS 限离线|
|36|研究开关关闭|关闭状态无需 Worker 或研究任务库|test_service_boundaries.py 中 test_app_opt_in_creates_no_task_storage_when_disabled|PASS|

实验状态按证据区分。代码和本机夹具对应 implemented / tested_fixture，三类只读本地 ES 对应 tested_real_corpus。个人模型与人工结论分别为 tested_real_model = false、human_verified = false。
