# Antigravity Gemini 启动提示词

请接管 Scholarlens EvoResearch 的研究质量改进。先读取同目录的 [技术交接](GEMINI_RESEARCH_HANDOFF.md)、[复现手册](EXPERIMENT_REPRODUCIBILITY.md)、[机器清单](EXPERIMENT_MANIFEST.json) 和 [失败索引](FAILURE_CASE_INDEX.md)，并核对 `AGENTS.md`、当前 Git SHA、未提交修改及 PR #42/#43 的实际状态。工程基线为 `e5bda5f33bb52bcd3c15cc1bf37efb4791423ef4`。从交接分支读取文档，基线升级需核对文件树和测试。

第一条复现命令为 `python -m tools.research_eval.pra_scorecard --out gemini-scorecard.json`。先比较生成结果与仓库验收表，再取得冻结语料和外部资料复现 E11 A、PRA G。缺少语料、环境或凭证时记录 BLOCKED、缺项和已执行结果，继续可独立完成的验证。保持冻结题目、标签、语料、引用核验和发布阈值。

按实际执行链逐题检查失败，记录原始字段、来源切片、可答性、归属、首次可见损失和可证实根因。先提出可证伪的算法假设，建立最小的正负对照，按模块消融。覆盖意图、规划、作者事实提取、多论文关系、补读和答案编译。保持 E11 默认和 PRA 实验开关，沿用 FastAPI、LangGraph、SQLite、Elasticsearch、ONNX、React、Compose、OTel 与现有权限隔离。

同预算配对报告完整原题、逐字段覆盖、来源回读、逐题误发、工具/模型用量、时延和成本。用独立 Holdout 判定泛化，把开发题及同题回归分别报告。真实 Provider、受控 HTTP、纯离线应注明各自环境与限制。任一负例新误发须单列。交付分支、实际命令与退出码、前后逐题结果、变更范围及仍待验证的问题。首个候选只处理一个可复现的字段级故障。
