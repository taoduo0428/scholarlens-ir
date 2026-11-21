# ScholarLens 工程交付记录

本轮从 `f4733a2` 开发。首次工程集成与追加交付的改动分别见 [PR #7](https://github.com/taoduo0428/scholarlens-ir/pull/7/files) 和 [PR #9](https://github.com/taoduo0428/scholarlens-ir/pull/9/files)。个人公开仓库的默认分支已包含这些提交及原有论文资产。[默认分支整合记录](https://github.com/taoduo0428/scholarlens-ir/pull/8)

|阶段|交付及依据|
|---|---|
|E11 研究核心|研究意图、按问题规划、逐篇档案、原文位置校验、部分回答和项目证据记忆接入报告。具名对象、研究目标及指定指标有独立回归。|
|E12 版面证据|受授权的 PDF 页读取返回来源哈希、边界框、行列位置和内容。6 张出版社表格逐格复核通过。|
|E13 运行|复用 SQLite 和现有队列。完成多用户负载、备份恢复、报告哈希检查及服务探针。|
|E14 工具治理|新增服务端工具目录、输入输出限制和超时，修复超大响应错误分类及 PDF 依赖安全公告。|
|E15 技能|沿用现有版本化技能注册表、离线试验和独立审批。生产技能变更仍由授权审批。|
|E16 协作|在 111 条任务轨迹上增加只读的独立来源核验角色，8 条直接结论均通过，直接回答数仍为 5。多模型协作的收益待真实供应方对照。|
|E17 工作台|报告能显示实际任务的逐篇档案、引文、费用可用性和缺证原因。新增项目标识、存活就绪探针、容器配置和 SBOM。|

## 使用及开发

在隔离安装中启用 `SCHOLARLENS_RESEARCH_ENABLED=true` 和 `SCHOLARLENS_E11_ENABLED=true`，前端使用 `VITE_RESEARCH_ENABLED=true` 构建。登录后进入研究页面，填写目标、选填项目标识，在“本库论文范围”选择论文并开始研究。完成后可展开“逐篇研究档案”查看原句和位置、核对“字段核验”、下载 Markdown。其他账号访问同一任务受服务端限制。

本地工作台浏览器试验以专用合成语料打通真实账号、任务、报告和页面。两篇论文的 6 条引文及位置均与服务端一致，刷新后仍显示两个档案，另一账号读该报告为 404。复核命令为 `python -m tools.research_eval.v6_browser --e11 --fixture-lab <隔离实验库> --dist <已启用研究页的构建目录> --output <输出目录>`。

前端在 frontend 目录运行 `npm test`、`npm run typecheck`、`npm run verify:structure`、`npm run build:production`，45 项测试通过，类型、结构和生产构建均通过。后端使用 `python -m tools.research_eval.v6_vector_fixture --es-home <ES安装目录> --offline-fixture infra/.runtime/elasticsearch-8.19.23/data --full-suite`。该命令在随机回环端口启动原索引的隔离副本，保护源数据并检查退出后端口已关闭。

受控 HTTP 模型完成规划、决策、工具、来源核验、分析、综合及发布检查，4 次模型调用。真实供应方缺少项目端点、凭证、模型名和费用上限，实际调用为 0，账单未知。复核入口为 `python -m tools.research_eval.v6_model --policy E11`。具体参数见命令的 `--help`。

升级 PDF 依赖后再次运行全量后端。698 项中 681 通过、0 失败、17 跳过，pytest 用时 466.11 秒，退出码 0。隔离实例有 859 篇论文和 49,420 条向量，源文件清单保持一致，结束时测试端口均已释放。17 项跳过中，16 项要求显式指定交付数据与服务，1 项要求特定名称的本地 ES 集群。随后对现存交付目录单独运行其中 4 项只读文件验收，4 项通过，用时 32.67 秒。机器记录保存了原始分母。[工程验收数据](engineering-results.json)

## 2026-11-22 追加验收

在提交 `4656d2a` 对应的后端与交付测试上，完整套件 **706 项通过，0 失败，0 跳过**，用时 482.93 秒，退出码 0。命令为 `python -m tools.research_eval.v6_vector_fixture --es-home <ES安装目录> --offline-fixture infra/.runtime/elasticsearch-8.19.23/data --full-suite --delivery backend/.runtime/p0-delivery`。用例使用 859 篇论文、49,420 条向量及隔离的启动和停止脚本。运行前后原索引文件清单一致，测试端口已关闭。

浏览器从限定论文中读取一页、选中合成表格的数值 87，在任务报告中核对位置，下载的 Markdown 与报告原文相同。刷新后两篇论文的档案仍可读，同名项目在另一账号下的任务数为 0。前端 45 项测试、结构校验、TypeScript 和启用研究页面的生产构建通过。另在真实出版社 PDF 的物理单元格上复核了数值 23,133。[本次机器验收记录](delivery-acceptance.json)

GitHub 拒绝写入工作流，返回当前 OAuth 授权缺少 `workflow` 权限。复核用工作流存于 `infra/ci/agent-ci.yml`。公开稳定版仍待真实模型、容器和托管 CI 验收。

研究质量、PDF 结果、运行情况、安全审计与公开发布门槛分别见下列记录。

- [研究质量](RESEARCH_QUALITY_REPORT.md)
- [PDF 与出版社核对](PDF_MULTIMODAL_REPORT.md)
- [并发和恢复](RUNTIME_REPORT.md)
- [安全审计](SECURITY_AUDIT.md)
- [发布就绪与 main 整合](RELEASE_READINESS.md)
- [部署与恢复手册](OPERATIONS.md)
