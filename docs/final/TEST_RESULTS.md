# 测试结果

2026-11-24。退出码以实际进程和 Actions 作业记录为准。最终回归覆盖状态见发布准备报告。

| 运行 | 结果与退出码 |
|---|---|
| Windows npm test | 47 通过，0 |
| Windows npm run verify:structure | 通过，0 |
| Windows npm run build:production | TypeScript 与 Vite 构建通过，0 |
| 后端全量，首轮 | 真实 ES 8.19.23，859 篇和 49,420 向量，959 通过、2 失败、23 跳过，退出 1。失败均由缺少可选 PDF 解析依赖引起，原索引签名一致，隔离端口已关闭。 |
| PDF 定向复跑 | 在独立目录安装现有 PDF 锁定依赖，图表、公式、布局共 27 通过，0。补齐依赖的全量回归见下一行。 |
| 后端全量，补齐 PDF 依赖 | 974 通过、10 跳过、0 失败，退出 0。ES 8.19.23 含 859 篇和 49,420 个向量。原索引签名一致，隔离端口关闭。 |
| 最终全量后端 | 在 PDF 与 OTLP 依赖同时加载的环境验证 SQLite 修复后的版本，985 通过、0 失败、0 跳过，退出 0。原索引签名一致，隔离端口关闭。 |
| PDF 原件 | 真实论文 9 页，首屏渲染 306×396，并用应用解析器获得版面，0。SHA-256 为 ca2073de944a8ef60f5e12a9910cbba951e39785b9521c9ef130f743aa959f5c。 |
| 权限、SQLite、遥测定向回归 | 76 通过、9 跳过，0。含账号恢复、任务库快照、回滚、隔离和本地费用回执用例。可选遥测依赖的跳过项与 CI 单列。 |
| SQLite WAL 恢复专项 | 账号库旧版本迁移与备份恢复、原位恢复及反向恢复共 2 项通过，退出 0。Windows 上验证恢复返回后可立即关闭并删除测试库文件。 |
| OTLP 和回执补跑 | 加载锁定的研究依赖后，OTLP 与回执 19 通过，API 到工作进程的追踪 1 通过，两次退出 0。覆盖全量中全部 10 项跳过用例。 |
| Chrome 浏览器流程 | 初次构建缺少研究入口开关，退出 1。开启 VITE_RESEARCH_ENABLED 后重建，退出 0。真实 ES、真实 FastAPI、临时账号及真实论文，注册 201、登录 200、检索、任务、引用定位与导出通过，匿名报告 401，页面错误 0。证据模式，无 Provider 请求。 |
| GitHub verify（eff893a） | 精选后端 403 通过，另执行评价表、前端、依赖审计，0。 |
| GitHub standard / pdf-ocr（eff893a） | 构建、容器自检及扫描均成功，标准镜像另执行完整 Compose smoke，0。 |
| GitHub 镜像裁剪版（3d8b546） | verify、standard 与 pdf-ocr 三项通过，退出 0。标准镜像 Compose 复跑通过。 |
| 最终代码 CI（d4a1d8e） | verify、standard、pdf-ocr 均通过，作业退出 0。ES 初次扫描的配置 ID 比较退出 1，改为核对导出配置哈希后通过。[运行记录](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45347880238) |
| Compose 升级 CI（0461a21） | Linux runner 的 8.19.23 到 8.19.26 升级、原卷 UUID、文本搜索、kNN、前台 smoke 和账号恢复均通过，升级步骤退出 0。随后旧版镜像归档脚本找不到候选配置条目，扫描步骤退出 2。扫描流程改为从仓库按 digest 扫描，并核对实际容器镜像 ID。[运行记录](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45350433998) |
| ES 镜像对照与公告核查 | 两次同口径镜像扫描及配置校验退出 0。Ubuntu 安全公告核实 15/16，剩余一条查询退出 28。[原始结果摘要](elasticsearch-upgrade-review.json) |
| 真实 Provider | BLOCKED，退出 2，实际请求 0。 |
| 冻结材料 | v6_ci 验证 9 个冻结文件，v6_silver 核对 111 道公开题，分别退出 0。 |

命令入口为 `python -m tools.research_eval.v6_vector_fixture --es-home <ASCII-path> --offline-fixture infra/.runtime/elasticsearch-8.19.23/data --full-suite --delivery backend/.runtime/p0-delivery`，前端命令在 frontend 目录执行。Provider 检查入口为 `python -m tools.research_eval.v7_live_research --live --call-budget-only --output <文件>`。[初始托管 CI](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45343814183) · [镜像裁剪版 CI](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45345079394)
