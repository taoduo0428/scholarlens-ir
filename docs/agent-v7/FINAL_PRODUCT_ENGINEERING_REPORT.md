# ScholarLens 工程交付记录

## 2026-11-22 集中交付

|范围|用户能做什么|实测结果|
|---|---|---|
|研究回答|查看某个量的原文定义，分开检查单位、对照与实验条件；查看跨篇推理已经有依据的第一步。|111 道题里，正例直接回答 9→12/70，负例直接发布 0/41。逐条核对了 350 条来源和 16 条直接陈述。人工 Gold 为 0。[定量证据](QUANTITATIVE_EVIDENCE.md) · [多跳对照](MULTIHOP_SCOPE.md)|
|PDF|从工作台查看已登记标尺的曲线终点、原文中的公式引用与位置。|真实图的 22 个参考值读出 8 个，8 个均落在图像读数区间内。第 8 页两处公式引用与出版社正文对应，两条复杂公式仍缺转录。[曲线验收](CHART_AXES_ACCEPTANCE.md) · [公式核验](FORMULA_EVIDENCE.md)|
|任务与账号|导出带校验清单的任务 ZIP、删除已结束任务、打开追踪。运维可预览并清理停用账号的本地资料。|Chrome 双账号验证下载、删除与越权拒绝。Jaeger 读回 21 个 span。账号删除覆盖三库恢复与 ID 重用保护。[任务导出](TASK_DATA_LIFECYCLE.md) · [账号删除](ACCOUNT_ERASURE.md) · [追踪](TRACE_VIEWER.md)|
|治理与研究程序|管理员查看冻结实验、批准版本及回滚记录。旧任务按提交时的版本继续执行。|角色变更在旧会话立即生效。14 对冻结任务中，候选触发 2 次，答案变化 0 次，实验库记录为拒绝。[治理验收](GOVERNANCE_VIEW.md) · [发布收据](PROGRAM_RELEASE.md)|
|研究协作|在离线审计中独立复核每条直接陈述的来源。|111 题复核前后可直接回答的任务均为 12 道，额外模型与检索调用均为 0。[同预算比较](E16_REVIEW.md)|

真实模型试验需要部署方配置供应商地址、模型名、密钥和费用上限，本批环境探针记录了 0 次调用。开发集成、镜像安全扫描和正式版本的状态分别见[发布状态](RELEASE_READINESS.md)。

本批共收集 891 个后端用例。首轮修正一条受负载影响的限时测试。修正后的全套运行有 873 个通过，Windows 提交内存耗尽导致隔离 ES 退出。给新建的测试 ES 限定 JVM 编译资源，在新的同版索引副本重跑受影响的三个模块，24 项全部通过。按完整用例名核对，两轮覆盖 891/891，未跳过用例。两份索引副本均包含 859 篇论文和 49,420 条向量，原索引清单一致，临时端口已释放。[逐轮验收与 JUnit 摘要](batch-acceptance.json)

## 先前已合并的基线

2026-11-22，本轮加入逐篇建模关系、彩色图例读取和研究任务 OTLP 导出。隔离 Elasticsearch 回归通过 805 项，失败、错误和跳过各 0，耗时 572.50 秒。副本包含 859 篇论文和 49,420 条向量，核对原索引文件清单和测试端口通过。随后修复接收端截断回执的误判，追踪专题 15 项通过。前端 45 项通过，类型、结构与生产构建通过。Chrome 读取两页真实论文的 12 条图例，Jaeger 按任务追踪 ID 查回全部 21 个 span。对 82 个锁定依赖的 pip-audit 结果为 0 个已知漏洞。[研究关系验收](E11_RELATIONS_ACCEPTANCE.md) · [图例验收](FIGURE_SEMANTICS_ACCEPTANCE.md) · [任务追踪实测](RUNTIME_REPORT.md)

E12 已在一篇真实论文中识别从右栏换到下一页左栏的续表。52 行中 199 个非空值与出版社原表相符，另一篇论文的 6 张单页表继续通过对照。工作台可查看续表来源并从当前页选取报告引文。[PDF 多模态报告](PDF_MULTIMODAL_REPORT.md)

本轮 E11 从已读原句中识别作者提出方法时写明的用途。在 111 道冻结 AI Silver 上，可答或部分可答题中有直接回答的题数由 8/70 增至 9/70，41 道负例仍为 0 次直接发布。新增答案绑定资源受限项目调度的论文原句，13 条直接陈述通过出处复核。使用额外封存的 16 对论文再次验证标题归属，32 次运行的逐题回答条数与上次相同。[研究质量与复核记录](RESEARCH_QUALITY_REPORT.md)

应用提交 `5cdb065` 在已有运行卷中为同机模型调用分配共享名额。两个独立进程对同一模型主机的并发峰值从 4 降至 2。持锁进程异常结束后，Windows 和 Linux 均收回了全部四个名额。全量后端测试通过 756 项，失败和跳过均为 0，pytest 用时 505.03 秒。隔离 Elasticsearch 副本包含 859 篇论文和 49,420 条向量，原索引文件清单核对通过，测试端口已释放。[并发验收](RUNTIME_REPORT.md) · [发布状态](RELEASE_READINESS.md)

应用提交 `ae694c8` 在隔离 Elasticsearch 上通过 754 项后端测试，失败、错误和跳过均为 0。pytest 用时 449.07 秒。测试副本包含 859 篇论文和 49,420 条向量，结束时已核对原索引文件清单和测试端口。复测命令沿用下文的 `v6_vector_fixture` 完整后端入口，附加 `--full-suite --delivery backend/.runtime/p0-delivery`。[本轮研究质量](RESEARCH_QUALITY_REPORT.md) · [逐题数据](subject-evidence-results.json)

应用提交 `b978ab8` 已通过完整后端 743 项检查。API 与后台任务共享追踪标识。上一版浏览器测试库的 1 项任务和 4 份产物在迁移后逐项一致，上一版代码也可读取迁移后的库。[运行报告](RUNTIME_REPORT.md) · [验收数据](submission-trace-acceptance.json)

应用提交 `88f7781` 在隔离 Elasticsearch 上通过完整后端 731 项，失败和跳过均为 0，pytest 用时 447.038 秒。前端 45 项、结构检查、生产构建和双账号浏览器流程通过。[本轮验收](overview-acceptance.json)

本次将逐篇观察和跨论文推断分别发布。原有 28 组中，27 组可以直接回答部分问题，覆盖全组的关系为 0 组。在另外 12 对含证明陈述的论文中，系统为 1 对给出了可回查双方原句的共同研究手段，12 次缺少第二篇摘要的对照均保留了关系缺口。[研究质量](RESEARCH_QUALITY_REPORT.md) · [逐项验收](overview-acceptance.json)

2026-11-22 在独立 WSL2 环境构建并运行了 Linux 应用镜像和 Elasticsearch 8.19.23。用旧版的两个账号、一篇合成论文和一份研究报告验证了升级和回退。容器内三次恢复 SQLite 快照，报告哈希一致，另一个账号读取该报告均返回 404。更新 Python 3.11 的 Debian 运行环境后，应用镜像的 Critical 匹配从 4 降至 0，High 从 106 降至 96。[容器验收和镜像发现](container-acceptance.json) · [复核步骤](OPERATIONS.md)

上一轮研究问答验收针对提交 `7cc417d`。这次改动修正了具名论文在复合问题中的绑定和部分作答。新的 16 对论文中，7 题给出了带原文定位的目标论文陈述。原有 28 组中，2 组完整列举了各篇论文的方法与发现。[本轮研究质量](RESEARCH_QUALITY_REPORT.md) · [逐题迁移结果](study-brief/transfer-new.json)

此前对具名研究问答版本的完整后端 715 项全部通过，0 跳过，pytest 用时 437.12 秒。隔离实例含 859 篇论文、49,420 条向量，原索引文件清单一致且测试端口已释放。前端 45 项通过，类型、结构与生产构建通过。浏览器以两个账号验证了 PDF 选格、4 组引文和定位、报告下载、刷新恢复及隔离。真实出版社 PDF 第 6 页表 1 的 23,133 与 JATS 单元格一致。1、4、12 个并发用户的 17 个任务均从 SQLite 备份恢复了报告。78 个锁定 Python 包与前端 npm 审计均报告 0 条已知漏洞。[验收记录](study-brief/acceptance.json) · [运行数据](study-brief/runtime.json)

本轮从 `f4733a2` 开发。首次工程集成与追加交付的改动分别见 [PR #7](https://github.com/taoduo0428/scholarlens-ir/pull/7/files) 和 [PR #9](https://github.com/taoduo0428/scholarlens-ir/pull/9/files)。个人公开仓库的默认分支已包含这些提交及原有论文资产。[默认分支整合记录](https://github.com/taoduo0428/scholarlens-ir/pull/8)

|阶段|交付及依据|
|---|---|
|E11 研究核心|研究意图、按问题规划、逐篇档案、原文位置校验、部分回答和项目证据记忆接入报告。具名对象、研究目标及指定指标有独立回归。|
|E12 版面证据|受授权的 PDF 页读取返回来源哈希、边界框、行列位置和内容。6 张出版社表格逐格复核通过。6 幅编号图的题注标题和全部 RGB 像素与出版社素材一致。[逐图证据](figure-results.json)|
|E13 运行|真实进程意外退出后的接替试验恢复了四份报告。复用 SQLite 和现有队列。完成多用户负载、备份恢复、报告哈希检查及服务探针。|
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

GitHub 的工作流写权限已生效。2026-11-22，托管 Ubuntu 在同一次 PR 运行中通过三组 Python 测试，分别为 15、26、189 项。冻结基准、前端和 Docker 构建通过，Python 依赖审计通过。[运行日志及测试计数产物](https://github.com/taoduo0428/scholarlens-ir/actions/runs/44981973205)

2026-11-22，GitHub Actions 在 Ubuntu 上重新构建完整应用镜像，导出后计算配置 SHA-256，与 Grype 报告中的镜像 ID 一致。此次扫描共 247 条包与公告匹配，其中 Critical 0、High 80、Medium 95、Low 21、Negligible 51。上一版完整镜像为 96 条 High、27 个不同的 High 公告，本次为 80 条、24 个公告。libc6 和 libc-bin 均为 `2.41-12+deb13u5`。扫描器将剩余 High 中的 59 条列为 `wont-fix`，21 条列为 `not-fixed`。正式发布仍需评估这些包在服务中的使用及影响。[完整镜像扫描摘要](hosted-image-scan.json) · [运行与原始产物](https://github.com/taoduo0428/scholarlens-ir/actions/runs/44983031422)

研究质量、PDF 结果、运行情况、安全审计与公开发布门槛分别见下列记录。

- [研究质量](RESEARCH_QUALITY_REPORT.md)
- [PDF 与出版社核对](PDF_MULTIMODAL_REPORT.md)
- [并发和恢复](RUNTIME_REPORT.md)
- [安全审计](SECURITY_AUDIT.md)
- [发布就绪与 main 整合](RELEASE_READINESS.md)
- [部署与恢复手册](OPERATIONS.md)
