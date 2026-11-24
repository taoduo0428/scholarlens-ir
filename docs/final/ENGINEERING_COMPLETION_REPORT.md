# ScholarLens 最终工程验收

日期 2026-11-24。工程基线为 `67088d0`，候选分支为 `codex/final-delivery`。交付范围涵盖打包、CI、运行验收和文档。[PR #43](https://github.com/taoduo0428/scholarlens-ir/pull/43)

| 范围 | 本轮处理 |
|---|---|
| 模块边界 | FastAPI 负责 HTTP 与身份边界，LangGraph 管理研究流程，SQLite 保存账号及任务状态，Elasticsearch 承载论文与向量索引，React 通过同源 API 工作，OTLP 出站由运维配置。 |
| 依赖 | 生产镜像剔除 pytest、Ruff 及其专用依赖的直接安装项，保留共享锁文件。镜像内运行 pip check，并确认 pytest 和 Ruff 不可导入。 |
| CI | 标准镜像进入独立 Compose 项目，验证真实 ES 与 FastAPI 可用，并验证重建 API 容器后测试账号仍可登录。清理限于任务专用 Compose 项目。 |
| SQLite 恢复 | 备份与恢复显式关闭 SQLite 连接。WAL 回滚测试覆盖原位恢复、操作前副本和反向恢复。 |
| 技术债 | `infra/ci` 仍存历史模板，自动化以 `.github/workflows` 为准。历史模板与相关历史报告保留。Windows 下以 ASCII 路径运行 ES 程序，原索引使用隔离副本。 |
| 研究策略 | 已启用 E11 的环境继续采用 A 组。PRA G 组只用于显式定向实验。冻结材料通过字节校验。 |

已有报告与最新工程验收曾使用不同环境和提交，结果以各报告列出的命令、退出码和运行标识为准。

- [测试与退出码](TEST_RESULTS.md)
- [安全审计](SECURITY_AUDIT.md)
- [部署验收](DEPLOYMENT_ACCEPTANCE.md)
- [发布判定](RELEASE_READINESS.md)
