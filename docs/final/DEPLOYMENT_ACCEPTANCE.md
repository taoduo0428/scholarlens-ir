# 部署验收与操作手册

独立部署需要 Docker Engine、Compose v2 和项目专用的运行目录。候选由 [PR #43](https://github.com/taoduo0428/scholarlens-ir/pull/43) 管理。

```sh
export SCHOLARLENS_E11_ENABLED=true
docker compose -p scholarlens-staging -f infra/product.compose.yml config -q
docker compose -p scholarlens-staging -f infra/product.compose.yml up -d --build --wait
```

配置预期的论文索引别名与可用数据，再访问 `http://127.0.0.1:18001`。健康检查 `/healthz` 表示进程存活，`/readyz` 在 SQLite 用户表和索引映射均可用时返回 200。空索引环境的 readiness 可能为 503。正式论文需按文档导入或恢复，语义检索需另行校验向量及模型。OCR 通过叠加 `infra/pdf-ocr.compose.yml` 启用。[原件交付说明](../operations/13_ORIGINAL_PDF_DELIVERY.md)

| 验收 | 结果 |
|---|---|
| Compose | Linux runner 使用独立项目与数据卷。在 8.19.23 建立标为 mock 的索引和向量，切换至 8.19.26 后在原卷通过集群 UUID、文本检索及 kNN 检查。真实 FastAPI 的首页、OpenAPI、readiness 与 API 容器重建后的登录通过。[升级作业](https://github.com/taoduo0428/scholarlens-ir/actions/runs/45350433998/job/138295215122) |
| Windows ES | 8.19.23 在回环运行 859 篇论文、49,420 个向量。使用程序副本及原索引的独立数据副本。 |
| PDF | 用公开论文 DOI 10.1371/journal.pone.0081798 的本机原件解析首屏版面并用 PDFium 渲染。另执行版面、图表和公式夹具。 |
| 浏览器 | 本机 Chrome 157 连接回环 FastAPI 和真实论文索引，完成检索、注册和登录、研究任务、引用定位与导出。报告保留证据不足状态。 |
| Provider | BLOCKED。当前环境缺少 AI_BASE_URL、AI_MODEL、AI_API_KEY，实际请求 0 次。 |
| 遥测 | 受控 OTLP 接收端验证 API 到工作进程的追踪关联、回执和关闭时导出。真实外部监控与账单缺少环境配置，为 BLOCKED。 |

## 备份、迁移与回滚

部署前记录镜像 digest、索引别名、持久化路径和 schema 版本。应用账号、研究数据、上传文件和正式论文各自按所属运行目录备份，SQLite 活跃库使用 SQLite Backup API 获取一致副本。保留上一镜像及快照，先在独立目录验证完整性与恢复。

Elasticsearch 升级使用升级前的快照或停机复制卷作为回滚点。回滚时把旧镜像与升级前的副本配对使用。Compose 升级已用测试卷验收，正式论文索引升级及快照恢复留待目标环境演练。

恢复账号库时先停对应 API，再运行 `python -m backend.db_migrations --database <账号数据库> --restore <备份文件>`。恢复会保留操作前的数据库副本。需要撤销恢复时，在 API 停止的状态下使用该副本再次执行 restore，并检查完整性及账号状态。研究库使用自身快照流程。实际回滚先将应用恢复至兼容版本，再核对账号、任务所有权、论文别名与健康探针。部署和回滚流程详见 [服务器操作说明](../operations/11_SERVER_DEPLOYMENT.md)。
